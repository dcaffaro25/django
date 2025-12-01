"""
Service for suggesting book transactions based on historical matched bank transactions.
Uses embeddings to find similar historical matches and suggests journal entries.
"""

import logging
from decimal import Decimal
from typing import List, Dict, Any, Optional, Tuple
from django.db.models import Q, Count, F
from django.db import transaction as db_transaction
from django.contrib.postgres.search import CosineDistance

from accounting.models import (
    BankTransaction,
    Transaction,
    JournalEntry,
    Reconciliation,
    Account,
    Currency,
)
from accounting.services.embedding_client import EmbeddingClient, clean_description_for_embedding

log = logging.getLogger(__name__)


class BankTransactionSuggestionService:
    """Service for generating book transaction suggestions from bank transactions."""
    
    def __init__(self, company_id: int):
        self.company_id = company_id
        self.embedding_client = EmbeddingClient()
    
    def suggest_book_transactions(
        self,
        bank_transaction_ids: List[int],
        max_suggestions_per_bank: int = 5,
        min_confidence: float = 0.3,
        min_match_count: int = 1,
    ) -> Dict[str, Any]:
        """
        Suggest book transactions for unmatched bank transactions based on historical matches.
        
        Parameters
        ----------
        bank_transaction_ids: List[int]
            List of unmatched bank transaction IDs
        max_suggestions_per_bank: int
            Maximum number of suggestions per bank transaction
        min_confidence: float
            Minimum confidence score (0-1)
        min_match_count: int
            Minimum number of historical matches required
        
        Returns
        -------
        Dict[str, Any]
            Dictionary with suggestions for each bank transaction
        """
        bank_transactions = BankTransaction.objects.filter(
            id__in=bank_transaction_ids,
            company_id=self.company_id,
        ).select_related('bank_account', 'currency', 'bank_account__entity')
        
        if not bank_transactions.exists():
            return {
                'suggestions': [],
                'errors': ['No bank transactions found with provided IDs']
            }
        
        all_suggestions = []
        
        for bank_tx in bank_transactions:
            suggestions = self._suggest_for_bank_transaction(
                bank_tx,
                max_suggestions=max_suggestions_per_bank,
                min_confidence=min_confidence,
                min_match_count=min_match_count,
            )
            
            all_suggestions.append({
                'bank_transaction_id': bank_tx.id,
                'bank_transaction': {
                    'id': bank_tx.id,
                    'date': bank_tx.date.isoformat(),
                    'amount': str(bank_tx.amount),
                    'description': bank_tx.description,
                    'bank_account_id': bank_tx.bank_account.id,
                    'entity_id': bank_tx.bank_account.entity_id,
                    'currency_id': bank_tx.currency.id,
                },
                'suggestions': suggestions,
            })
        
        return {
            'suggestions': all_suggestions,
            'errors': [],
        }
    
    def _suggest_for_bank_transaction(
        self,
        bank_tx: BankTransaction,
        max_suggestions: int = 5,
        min_confidence: float = 0.3,
        min_match_count: int = 1,
    ) -> List[Dict[str, Any]]:
        """Generate suggestions for a single bank transaction."""
        
        # Get embedding for this bank transaction
        if not bank_tx.description_embedding:
            # Generate embedding if not present
            cleaned_desc = clean_description_for_embedding(bank_tx.description)
            try:
                embedding = self.embedding_client.embed_one(cleaned_desc)
                bank_tx.description_embedding = embedding
                bank_tx.save(update_fields=['description_embedding'])
            except Exception as e:
                log.error(f"Failed to generate embedding for bank_tx {bank_tx.id}: {e}")
                return []
        
        suggestions = []
        
        # 1. Find unmatched journal entries that could match this bank transaction
        existing_book_suggestions = self._find_existing_book_matches(
            bank_tx,
            max_suggestions=max_suggestions // 2,  # Reserve half for new transaction suggestions
            min_confidence=min_confidence,
        )
        suggestions.extend(existing_book_suggestions)
        
        # 2. Find similar historical bank transactions that were matched (for new transaction suggestions)
        historical_matches = self._find_historical_matches(
            bank_tx,
            min_match_count=min_match_count,
        )
        
        if historical_matches:
            # Group by transaction pattern (description pattern from matched transactions)
            pattern_groups = self._group_by_pattern(historical_matches)
            
            # Generate suggestions from each pattern group
            for pattern, matches in pattern_groups.items():
                if len(matches) < min_match_count:
                    continue
                
                # Calculate confidence based on embedding similarity and match count
                confidence = self._calculate_confidence(bank_tx, matches)
                
                if confidence < min_confidence:
                    continue
                
                # Get the most common journal entry pattern from matches
                suggestion = self._build_suggestion(
                    bank_tx,
                    matches,
                    pattern,
                    confidence,
                    suggestion_type='create_new',
                )
                
                if suggestion:
                    suggestions.append(suggestion)
        
        # Sort by confidence and limit
        suggestions.sort(key=lambda x: x['confidence_score'], reverse=True)
        return suggestions[:max_suggestions]
    
    def _find_historical_matches(
        self,
        bank_tx: BankTransaction,
        min_match_count: int = 1,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """
        Find historical bank transactions that were matched and are similar to this one.
        """
        # Find matched bank transactions with similar embeddings
        # Exclude the current transaction
        matched_bank_txs = BankTransaction.objects.filter(
            company_id=self.company_id,
            reconciliations__status__in=['matched', 'approved'],
        ).exclude(
            id=bank_tx.id,
        ).exclude(
            description_embedding__isnull=True,
        )
        
        # Filter by same entity if possible
        if bank_tx.bank_account.entity_id:
            matched_bank_txs = matched_bank_txs.filter(
                bank_account__entity_id=bank_tx.bank_account.entity_id,
            )
        
        # Use vector similarity search
        if bank_tx.description_embedding:
            # CosineDistance returns distance (0-2), convert to similarity (0-1)
            matched_bank_txs = matched_bank_txs.annotate(
                distance=CosineDistance('description_embedding', bank_tx.description_embedding),
                similarity=1 - (CosineDistance('description_embedding', bank_tx.description_embedding) / 2)
            ).filter(
                similarity__gte=0.5,  # Minimum similarity threshold
            ).order_by('-similarity')[:limit]
        
        # Get the matched journal entries for these bank transactions
        historical_matches = []
        for matched_bt in matched_bank_txs:
            # Get reconciliations for this matched bank transaction
            reconciliations = Reconciliation.objects.filter(
                bank_transactions=matched_bt,
                status__in=['matched', 'approved'],
            ).prefetch_related('journal_entries', 'journal_entries__transaction', 'journal_entries__account')
            
            for recon in reconciliations:
                journal_entries = list(recon.journal_entries.all())
                if journal_entries:
                    historical_matches.append({
                        'bank_transaction': matched_bt,
                        'reconciliation': recon,
                        'journal_entries': journal_entries,
                        'transaction': journal_entries[0].transaction if journal_entries else None,
                        'similarity': getattr(matched_bt, 'similarity', 0.5),
                    })
        
        return historical_matches
    
    def _group_by_pattern(
        self,
        historical_matches: List[Dict[str, Any]],
    ) -> Dict[str, List[Dict[str, Any]]]:
        """
        Group historical matches by transaction pattern.
        Pattern is based on the structure of journal entries (accounts, amounts, etc.)
        """
        pattern_groups = {}
        
        for match in historical_matches:
            journal_entries = match['journal_entries']
            if not journal_entries:
                continue
            
            # Create a pattern key based on journal entry structure
            # Sort by account to ensure consistent pattern
            sorted_entries = sorted(
                journal_entries,
                key=lambda je: (je.account_id or 0, je.debit_amount or 0, je.credit_amount or 0)
            )
            
            pattern_key = self._create_pattern_key(sorted_entries)
            
            if pattern_key not in pattern_groups:
                pattern_groups[pattern_key] = []
            pattern_groups[pattern_key].append(match)
        
        return pattern_groups
    
    def _create_pattern_key(self, journal_entries: List[JournalEntry]) -> str:
        """Create a pattern key from journal entries."""
        parts = []
        for je in journal_entries:
            account_id = je.account_id or 0
            debit = je.debit_amount or Decimal('0')
            credit = je.credit_amount or Decimal('0')
            parts.append(f"{account_id}:{debit}:{credit}")
        return "|".join(parts)
    
    def _calculate_confidence(
        self,
        bank_tx: BankTransaction,
        matches: List[Dict[str, Any]],
    ) -> float:
        """
        Calculate confidence score based on:
        1. Embedding similarity (weighted average)
        2. Number of matches (more matches = higher confidence)
        3. Amount similarity (if amounts are similar, higher confidence)
        """
        if not matches:
            return 0.0
        
        # Average embedding similarity
        avg_similarity = sum(m.get('similarity', 0.5) for m in matches) / len(matches)
        
        # Match count factor (logarithmic scale)
        match_count_factor = min(1.0, 0.3 + (len(matches) - 1) * 0.1)
        
        # Amount similarity (check if amounts are similar to historical matches)
        amount_similarity = 1.0  # Default to 1.0 if we can't determine
        if matches:
            historical_amounts = [
                sum(je.debit_amount or je.credit_amount or Decimal('0') for je in m['journal_entries'])
                for m in matches
            ]
            if historical_amounts:
                avg_historical_amount = sum(historical_amounts) / len(historical_amounts)
                if avg_historical_amount != 0:
                    amount_diff = abs(float(bank_tx.amount) - float(avg_historical_amount))
                    amount_similarity = max(0.0, 1.0 - (amount_diff / abs(float(avg_historical_amount))))
        
        # Weighted combination
        confidence = (
            0.5 * avg_similarity +
            0.3 * match_count_factor +
            0.2 * amount_similarity
        )
        
        return min(1.0, max(0.0, confidence))
    
    def _find_existing_book_matches(
        self,
        bank_tx: BankTransaction,
        max_suggestions: int = 3,
        min_confidence: float = 0.3,
    ) -> List[Dict[str, Any]]:
        """
        Find unmatched journal entries that could match this bank transaction.
        Returns suggestions to use existing journal entries + create complementing entries.
        """
        # Find unmatched journal entries with similar embeddings
        # Journal entries that are NOT reconciled (exclude those with matched/approved reconciliations)
        unmatched_journal_entries = JournalEntry.objects.filter(
            company_id=self.company_id,
            account__bank_account__isnull=False,  # Only cash/bank accounts
        ).exclude(
            reconciliations__status__in=['matched', 'approved'],
        ).select_related('transaction', 'account', 'account__bank_account')
        
        # Filter by same entity if possible
        if bank_tx.bank_account.entity_id:
            unmatched_journal_entries = unmatched_journal_entries.filter(
                transaction__entity_id=bank_tx.bank_account.entity_id,
            )
        
        # Filter by same bank account if possible
        bank_account = bank_tx.bank_account
        unmatched_journal_entries = unmatched_journal_entries.filter(
            account__bank_account=bank_account,
        )
        
        # Use vector similarity search on transaction descriptions
        if bank_tx.description_embedding:
            unmatched_journal_entries = unmatched_journal_entries.filter(
                transaction__description_embedding__isnull=False,
            ).annotate(
                distance=CosineDistance('transaction__description_embedding', bank_tx.description_embedding),
                similarity=1 - (CosineDistance('transaction__description_embedding', bank_tx.description_embedding) / 2)
            ).filter(
                similarity__gte=min_confidence,
            ).order_by('-similarity')[:max_suggestions * 2]  # Get more candidates to filter
        
        suggestions = []
        
        for journal_entry in unmatched_journal_entries:
            similarity = getattr(journal_entry, 'similarity', 0.5)
            
            # Calculate what's needed to balance with bank transaction
            je_amount = journal_entry.debit_amount or journal_entry.credit_amount or Decimal('0')
            bank_amount = abs(bank_tx.amount)
            
            # Calculate difference
            difference = bank_amount - abs(je_amount)
            
            # Only suggest if the difference is reasonable (not too large)
            if abs(difference) > bank_amount * 2:  # Don't suggest if difference is more than 2x the bank amount
                continue
            
            # Calculate confidence based on similarity and amount match
            amount_match_score = 1.0 - (abs(difference) / bank_amount) if bank_amount > 0 else 0.0
            amount_match_score = max(0.0, min(1.0, amount_match_score))
            
            confidence = (0.6 * similarity) + (0.4 * amount_match_score)
            
            if confidence < min_confidence:
                continue
            
            # Build complementing journal entries
            complementing_entries = []
            
            if abs(difference) > Decimal('0.01'):
                # Need to create complementing entry
                # Determine direction based on bank transaction and existing entry
                is_bank_debit = bank_tx.amount > 0
                is_je_debit = journal_entry.debit_amount is not None and journal_entry.debit_amount > 0
                
                # Find the account for the complementing entry
                # Look at historical patterns to find what account to use
                complement_account = self._find_complement_account(
                    bank_tx,
                    journal_entry,
                )
                
                if complement_account:
                    if difference > 0:
                        # Need additional entry in same direction as bank
                        if is_bank_debit:
                            complementing_entries.append({
                                'account_id': complement_account.id,
                                'account_code': complement_account.account_code,
                                'account_name': complement_account.name,
                                'debit_amount': str(difference),
                                'credit_amount': None,
                                'description': bank_tx.description,
                                'cost_center_id': journal_entry.cost_center_id,
                            })
                        else:
                            complementing_entries.append({
                                'account_id': complement_account.id,
                                'account_code': complement_account.account_code,
                                'account_name': complement_account.name,
                                'debit_amount': None,
                                'credit_amount': str(difference),
                                'description': bank_tx.description,
                                'cost_center_id': journal_entry.cost_center_id,
                            })
                    else:
                        # Need opposite entry
                        if is_bank_debit:
                            complementing_entries.append({
                                'account_id': complement_account.id,
                                'account_code': complement_account.account_code,
                                'account_name': complement_account.name,
                                'debit_amount': None,
                                'credit_amount': str(-difference),
                                'description': bank_tx.description,
                                'cost_center_id': journal_entry.cost_center_id,
                            })
                        else:
                            complementing_entries.append({
                                'account_id': complement_account.id,
                                'account_code': complement_account.account_code,
                                'account_name': complement_account.name,
                                'debit_amount': str(-difference),
                                'credit_amount': None,
                                'description': bank_tx.description,
                                'cost_center_id': journal_entry.cost_center_id,
                            })
            
            suggestion = {
                'suggestion_type': 'use_existing_book',
                'confidence_score': round(confidence, 4),
                'similarity': round(similarity, 4),
                'amount_match_score': round(amount_match_score, 4),
                'existing_journal_entry': {
                    'id': journal_entry.id,
                    'transaction_id': journal_entry.transaction_id,
                    'account_id': journal_entry.account_id,
                    'account_code': journal_entry.account.account_code if journal_entry.account else None,
                    'account_name': journal_entry.account.name if journal_entry.account else None,
                    'debit_amount': str(journal_entry.debit_amount) if journal_entry.debit_amount else None,
                    'credit_amount': str(journal_entry.credit_amount) if journal_entry.credit_amount else None,
                    'description': journal_entry.description or journal_entry.transaction.description,
                    'date': journal_entry.date.isoformat() if journal_entry.date else journal_entry.transaction.date.isoformat(),
                },
                'complementing_journal_entries': complementing_entries,
                'bank_transaction_id': bank_tx.id,
                'amount_difference': str(difference),
            }
            
            suggestions.append(suggestion)
        
        return suggestions
    
    def _find_complement_account(
        self,
        bank_tx: BankTransaction,
        existing_journal_entry: JournalEntry,
    ) -> Optional[Account]:
        """
        Find the account to use for complementing journal entries.
        Looks at historical patterns or uses the opposite side of the existing entry.
        """
        # Strategy 1: Use the account from the opposite side of the existing entry
        # If existing entry is debit, complement should be credit (and vice versa)
        # But we need to find what account was typically used
        
        # Strategy 2: Look at historical matches to see what account was used
        # For now, use a simple approach: find the bank account's GL account
        bank_account = bank_tx.bank_account
        gl_account = Account.objects.filter(
            company_id=self.company_id,
            bank_account=bank_account,
        ).first()
        
        if gl_account:
            return gl_account
        
        # Fallback: use the existing entry's account (for balancing)
        return existing_journal_entry.account
    
    def _build_suggestion(
        self,
        bank_tx: BankTransaction,
        matches: List[Dict[str, Any]],
        pattern: str,
        confidence: float,
        suggestion_type: str = 'create_new',
    ) -> Optional[Dict[str, Any]]:
        """
        Build a suggestion from a group of historical matches.
        Returns a suggestion with all fields needed to create transaction and journal entries.
        """
        if not matches:
            return None
        
        # Use the most common pattern from matches
        # For now, use the first match's structure (could be improved to find most common)
        reference_match = matches[0]
        reference_journal_entries = reference_match['journal_entries']
        reference_transaction = reference_match['transaction']
        
        if not reference_journal_entries or not reference_transaction:
            return None
        
        # Build journal entry suggestions
        journal_entry_suggestions = []
        total_debit = Decimal('0')
        total_credit = Decimal('0')
        
        for ref_je in reference_journal_entries:
            # Calculate proportional amounts based on bank transaction amount
            ref_amount = ref_je.debit_amount or ref_je.credit_amount or Decimal('0')
            if ref_amount == 0:
                continue
            
            # Calculate total from reference transaction
            ref_total = sum(
                (je.debit_amount or je.credit_amount or Decimal('0'))
                for je in reference_journal_entries
            )
            
            if ref_total == 0:
                continue
            
            # Scale amount proportionally
            scaled_amount = (ref_amount / ref_total) * abs(bank_tx.amount)
            
            # Determine if this should be debit or credit
            is_debit = ref_je.debit_amount is not None and ref_je.debit_amount > 0
            
            # Adjust for bank transaction direction
            # If bank transaction is negative (outflow), reverse the direction
            if bank_tx.amount < 0:
                is_debit = not is_debit
            
            journal_entry_suggestions.append({
                'account_id': ref_je.account_id,
                'account_code': ref_je.account.account_code if ref_je.account else None,
                'account_name': ref_je.account.name if ref_je.account else None,
                'debit_amount': str(scaled_amount) if is_debit else None,
                'credit_amount': None if is_debit else str(scaled_amount),
                'description': ref_je.description or bank_tx.description,
                'cost_center_id': ref_je.cost_center_id,
            })
            
            if is_debit:
                total_debit += scaled_amount
            else:
                total_credit += scaled_amount
        
        # Ensure balance (add balancing entry if needed)
        difference = total_debit - total_credit
        if abs(difference) > Decimal('0.01'):
            # Need balancing entry - use bank account
            bank_account = bank_tx.bank_account
            # Find the account linked to the bank account
            balancing_account = Account.objects.filter(
                company_id=self.company_id,
                bank_account=bank_account,
            ).first()
            
            if balancing_account:
                if difference > 0:
                    # Need credit to balance
                    journal_entry_suggestions.append({
                        'account_id': balancing_account.id,
                        'account_code': balancing_account.account_code,
                        'account_name': balancing_account.name,
                        'debit_amount': None,
                        'credit_amount': str(difference),
                        'description': bank_tx.description,
                        'cost_center_id': None,
                    })
                    total_credit += difference
                else:
                    # Need debit to balance
                    journal_entry_suggestions.append({
                        'account_id': balancing_account.id,
                        'account_code': balancing_account.account_code,
                        'account_name': balancing_account.name,
                        'debit_amount': str(-difference),
                        'credit_amount': None,
                        'description': bank_tx.description,
                        'cost_center_id': None,
                    })
                    total_debit += -difference
            else:
                log.warning(
                    f"Could not find balancing account for bank_tx {bank_tx.id}, "
                    f"suggestion may be unbalanced (diff: {difference})"
                )
        
        # Build transaction suggestion
        suggestion = {
            'suggestion_type': suggestion_type,
            'confidence_score': round(confidence, 4),
            'match_count': len(matches),
            'pattern': pattern,
            'transaction': {
                'date': bank_tx.date.isoformat(),
                'entity_id': bank_tx.bank_account.entity_id,
                'description': bank_tx.description,
                'amount': str(abs(bank_tx.amount)),
                'currency_id': bank_tx.currency.id,
                'state': 'pending',
            },
            'journal_entries': journal_entry_suggestions,
            'historical_matches': [
                {
                    'bank_transaction_id': m['bank_transaction'].id,
                    'transaction_id': m['transaction'].id if m['transaction'] else None,
                    'similarity': round(m.get('similarity', 0.5), 4),
                }
                for m in matches[:5]  # Limit to top 5 for response size
            ],
        }
        
        return suggestion

