"""
Rule extraction service for reconciliation.

Analyzes accepted reconciliation matches to propose objective regex-based rules
(description patterns, numeric patterns, entity/counterpart matching) for user
validation. Validated rules can be stored and later applied in the reconciliation
engine to improve accuracy and efficiency.
"""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from decimal import Decimal
from typing import List, Optional, Tuple

from django.utils import timezone


def _parse_descriptions_from_payload(payload: dict) -> Tuple[List[str], List[str]]:
    """
    Extract bank and book description strings from a suggestion payload.
    Payload may have bank_lines/book_lines as newline-separated lines in format:
    BANK#id | date | amount | description
    BOOK#id | date | amount | description
    """
    bank_descs: List[str] = []
    book_descs: List[str] = []

    bank_lines = payload.get("bank_lines") or ""
    book_lines = payload.get("book_lines") or ""

    for line in bank_lines.split("\n"):
        line = (line or "").strip()
        if not line or not line.upper().startswith("BANK#"):
            continue
        parts = line.split(" | ", 3)
        if len(parts) >= 4:
            bank_descs.append(parts[3].strip())

    for line in book_lines.split("\n"):
        line = (line or "").strip()
        if not line or not line.upper().startswith("BOOK#"):
            continue
        parts = line.split(" | ", 3)
        if len(parts) >= 4:
            book_descs.append(parts[3].strip())

    # Normalize to one bank desc and one book desc per suggestion (take first of each)
    bank_str = bank_descs[0] if bank_descs else ""
    book_str = book_descs[0] if book_descs else ""
    return ([bank_str] if bank_str else [], [book_str] if book_str else [])


def _get_description_pairs_from_suggestions(suggestions) -> Tuple[List[str], List[str]]:
    """From a queryset of ReconciliationSuggestion, return (bank_descs, book_descs)."""
    bank_descs: List[str] = []
    book_descs: List[str] = []
    for s in suggestions:
        banks, books = _parse_descriptions_from_payload(s.payload or {})
        if banks and books:
            bank_descs.append(banks[0])
            book_descs.append(books[0])
    return bank_descs, book_descs


def extract_description_patterns(
    bank_descs: List[str], book_descs: List[str], min_samples: int = 5
) -> List[dict]:
    """
    Extract common text patterns from matched description pairs.
    Looks for common prefixes, suffixes, and keywords (e.g. PIX, TED, BOLETO).
    """
    if len(bank_descs) != len(book_descs) or len(bank_descs) < min_samples:
        return []

    results: List[dict] = []
    # Tokenize and count common tokens on bank side that appear in many pairs
    bank_token_counts: Counter = Counter()
    token_to_book_pattern: defaultdict = defaultdict(list)

    for bank, book in zip(bank_descs, book_descs):
        bank_upper = (bank or "").upper()
        book_upper = (book or "").upper()
        # Words (alphanumeric sequences) on bank side
        bank_tokens = re.findall(r"[A-Za-z0-9]+", bank_upper)
        for t in bank_tokens:
            if len(t) >= 2:  # skip single chars
                bank_token_counts[t] += 1
                if t in book_upper or _normalize_for_compare(t) in _normalize_for_compare(book_upper):
                    token_to_book_pattern[t].append((bank, book))

    # Propose a rule per token that appears in at least min_samples pairs
    for token, count in bank_token_counts.most_common(20):
        if count < min_samples:
            break
        pairs = token_to_book_pattern.get(token, [])
        if len(pairs) < min_samples:
            continue
        # Build a simple regex: bank side starts with or contains token
        bank_pattern = re.escape(token)
        if all(b.upper().startswith(token) for b, _ in pairs[:10]):
            bank_pattern = "^" + bank_pattern + r"\s*"
        else:
            bank_pattern = r".*" + bank_pattern + r".*"
        # Book side: case-insensitive presence of same token or normalized
        book_pattern = "(?i).*" + re.escape(token) + ".*"
        results.append({
            "rule_type": "description_pattern",
            "name": f"Keyword: {token}",
            "bank_pattern": bank_pattern,
            "book_pattern": book_pattern,
            "extraction_groups": {},
            "sample_count": len(pairs),
            "accuracy_score": min(Decimal("0.99"), Decimal(count) / Decimal(len(bank_descs))),
            "samples": [{"bank_desc": b, "book_desc": k} for b, k in pairs[:5]],
        })
    return results


def _normalize_for_compare(s: str) -> str:
    """Normalize string for fuzzy comparison (lowercase, collapse spaces)."""
    return re.sub(r"\s+", " ", (s or "").lower().strip())


def extract_numeric_patterns(
    bank_descs: List[str], book_descs: List[str], min_samples: int = 5
) -> List[dict]:
    """
    Find numeric sequences that appear in both bank and book descriptions
    (invoice numbers, reference codes).
    """
    if len(bank_descs) != len(book_descs) or len(bank_descs) < min_samples:
        return []

    results: List[dict] = []
    # Find numeric sequences of 4+ digits or patterns like NF 123, INV-123
    numeric_in_both = 0
    samples_with_numeric: List[Tuple[str, str, Optional[str]]] = []

    for bank, book in zip(bank_descs, book_descs):
        bank_nums = set(re.findall(r"\d{4,}", bank or ""))
        bank_nums.update(re.findall(r"(?:NF|INV|REF|#)\s*(\d+)", (bank or ""), re.I))
        book_nums = set(re.findall(r"\d{4,}", book or ""))
        book_nums.update(re.findall(r"(?:NF|INV|REF|#|nota)\s*(\d+)", (book or ""), re.I))
        common = bank_nums & book_nums
        if common:
            numeric_in_both += 1
            samples_with_numeric.append((bank, book, next(iter(common))))

    if numeric_in_both < min_samples:
        return []

    # Propose a generic numeric rule
    bank_pattern = r"(?P<invoice>\d{4,})"
    book_pattern = r"(?P<invoice>\d{4,})"
    results.append({
        "rule_type": "numeric_pattern",
        "name": "Invoice/reference number match",
        "bank_pattern": bank_pattern,
        "book_pattern": book_pattern,
        "extraction_groups": {"invoice": "invoice or reference number"},
        "sample_count": numeric_in_both,
        "accuracy_score": min(Decimal("0.99"), Decimal(numeric_in_both) / Decimal(len(bank_descs))),
        "samples": [
            {"bank_desc": b, "book_desc": k, "matched_value": v}
            for b, k, v in samples_with_numeric[:5]
        ],
    })
    return results


def extract_entity_patterns(
    bank_descs: List[str], book_descs: List[str], min_samples: int = 5
) -> List[dict]:
    """
    Identify entity/counterpart names present in both descriptions
    (e.g. PIX FULANO SILVA <-> Recebimento Fulano Silva).
    """
    if len(bank_descs) != len(book_descs) or len(bank_descs) < min_samples:
        return []

    results: List[dict] = []
    # Words that are likely names (2+ chars, not all digits)
    def name_tokens(s: str) -> List[str]:
        return [
            w for w in re.findall(r"[A-Za-zÀ-ÿ]+", (s or ""))
            if len(w) >= 2 and not w.isdigit()
        ]

    # Count how many pairs share at least one name-like token (normalized)
    pairs_with_shared_name = 0
    sample_pairs: List[Tuple[str, str]] = []

    for bank, book in zip(bank_descs, book_descs):
        bank_tokens = set(_normalize_for_compare(t) for t in name_tokens(bank))
        book_tokens = set(_normalize_for_compare(t) for t in name_tokens(book))
        if bank_tokens & book_tokens:
            pairs_with_shared_name += 1
            sample_pairs.append((bank, book))

    if pairs_with_shared_name < min_samples:
        return []

    # Propose a generic entity-matching rule (flexible regex for names)
    bank_pattern = r"(?P<entity>[A-Za-zÀ-ÿ\s]{3,})"
    book_pattern = r"(?i)(?P<entity>[A-Za-zÀ-ÿ\s]{3,})"
    results.append({
        "rule_type": "entity_match",
        "name": "Entity/counterpart name in both descriptions",
        "bank_pattern": bank_pattern,
        "book_pattern": book_pattern,
        "extraction_groups": {"entity": "counterpart name"},
        "sample_count": pairs_with_shared_name,
        "accuracy_score": min(
            Decimal("0.99"),
            Decimal(pairs_with_shared_name) / Decimal(len(bank_descs)),
        ),
        "samples": [{"bank_desc": b, "book_desc": k} for b, k in sample_pairs[:5]],
    })
    return results


def analyze_accepted_matches(
    company_id: int,
    min_samples: int = 5,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
) -> dict:
    """
    Analyze accepted ReconciliationSuggestions for the given company to find
    patterns. Returns proposed rules with regex patterns and sample matches.

    Uses ReconciliationSuggestion and payload from accounting.models (imported
    inside to avoid circular imports).
    """
    from django.db.models import Q
    from accounting.models import ReconciliationSuggestion

    qs = ReconciliationSuggestion.objects.filter(
        company_id=company_id,
        status="accepted",
    ).select_related("task").order_by("-id")

    if date_from or date_to:
        from django.utils.dateparse import parse_date
        if date_from:
            d_from = parse_date(date_from)
            if d_from:
                qs = qs.filter(created_at__date__gte=d_from)
        if date_to:
            d_to = parse_date(date_to)
            if d_to:
                qs = qs.filter(created_at__date__lte=d_to)

    total_accepted = qs.count()
    suggestions = list(qs[:500])  # cap for performance

    bank_descs, book_descs = _get_description_pairs_from_suggestions(suggestions)
    if len(bank_descs) < min_samples:
        return {
            "proposed_rules": [],
            "stats": {
                "total_accepted_matches": total_accepted,
                "pairs_with_descriptions": len(bank_descs),
                "patterns_found": 0,
                "coverage_estimate": 0.0,
            },
        }

    proposed: List[dict] = []
    proposed.extend(
        extract_description_patterns(bank_descs, book_descs, min_samples=min_samples)
    )
    proposed.extend(
        extract_numeric_patterns(bank_descs, book_descs, min_samples=min_samples)
    )
    proposed.extend(
        extract_entity_patterns(bank_descs, book_descs, min_samples=min_samples)
    )

    # Deduplicate by name and add temp_id for validate endpoint
    seen_names = set()
    for i, r in enumerate(proposed):
        name = r.get("name", "")
        if name in seen_names:
            r["temp_id"] = f"rule_{i}_{hash(name) % 10000}"
        else:
            seen_names.add(name)
            r["temp_id"] = f"rule_{i}"

    coverage = len(bank_descs) / total_accepted if total_accepted else 0.0
    return {
        "proposed_rules": proposed,
        "stats": {
            "total_accepted_matches": total_accepted,
            "pairs_with_descriptions": len(bank_descs),
            "patterns_found": len(proposed),
            "coverage_estimate": round(coverage, 2),
        },
    }
