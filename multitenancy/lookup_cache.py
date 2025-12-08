"""
In-memory lookup cache for ETL pipeline foreign key resolution.

This module provides efficient in-memory caching for frequently queried models
like Account, Entity, Currency, etc., to avoid repeated database queries during ETL processing.
"""

from typing import Dict, Optional, List, Any, Tuple
from collections import defaultdict
import logging

logger = logging.getLogger(__name__)


class LookupCache:
    """
    In-memory cache for foreign key lookups during ETL processing.
    
    Pre-loads commonly queried models (Account, Entity, Currency, etc.) into memory
    and provides fast lookup methods by ID, code, name, and path.
    """
    
    def __init__(self, company_id: int):
        self.company_id = company_id
        self._accounts_by_id: Dict[int, Any] = {}
        self._accounts_by_code: Dict[str, int] = {}  # code -> id
        self._accounts_by_name: Dict[str, List[int]] = defaultdict(list)  # name -> [ids] (may have duplicates)
        self._accounts_by_path: Dict[str, int] = {}  # path -> id
        self._accounts_tree: Dict[Optional[int], List[Any]] = defaultdict(list)  # parent_id -> [accounts]
        self._entities_by_id: Dict[int, Any] = {}
        self._entities_by_name: Dict[str, int] = {}
        self._currencies_by_id: Dict[int, Any] = {}
        self._currencies_by_code: Dict[str, int] = {}
        self._loaded = False
        
    def load(self):
        """Pre-load all lookup data into memory."""
        if self._loaded:
            return
        
        import time
        load_start = time.time()
        logger.info(f"Loading lookup cache for company_id={self.company_id}")
        
        # Load Accounts
        account_load_start = time.time()
        from accounting.models import Account
        accounts = Account.objects.filter(company_id=self.company_id).select_related('parent', 'currency')
        account_query_time = time.time() - account_load_start
        logger.info(f"ETL DEBUG: Account query took {account_query_time:.3f}s")
        
        account_index_start = time.time()
        for account in accounts:
            # Index by ID
            self._accounts_by_id[account.id] = account
            
            # Index by code (case-insensitive)
            if account.account_code:
                code_key = str(account.account_code).strip().lower()
                self._accounts_by_code[code_key] = account.id
            
            # Index by name (case-insensitive, may have duplicates)
            if account.name:
                name_key = str(account.name).strip().lower()
                self._accounts_by_name[name_key].append(account.id)
            
            # Build tree structure for path lookups
            parent_id = account.parent_id if account.parent else None
            self._accounts_tree[parent_id].append(account)
        account_index_time = time.time() - account_index_start
        logger.info(f"ETL DEBUG: Account indexing took {account_index_time:.3f}s for {len(self._accounts_by_id)} accounts")
        
        # Build path index by traversing the tree
        path_index_start = time.time()
        self._build_path_index()
        path_index_time = time.time() - path_index_start
        logger.info(f"ETL DEBUG: Path index building took {path_index_time:.3f}s")
        
        # Load Entities
        entity_load_start = time.time()
        from multitenancy.models import Entity
        entities = Entity.objects.filter(company_id=self.company_id)
        for entity in entities:
            self._entities_by_id[entity.id] = entity
            if entity.name:
                name_key = str(entity.name).strip().lower()
                self._entities_by_name[name_key] = entity.id
        
        entity_load_time = time.time() - entity_load_start
        logger.info(f"ETL DEBUG: Entity loading took {entity_load_time:.3f}s for {len(self._entities_by_id)} entities")
        
        # Load Currencies
        currency_load_start = time.time()
        from accounting.models import Currency
        currencies = Currency.objects.all()  # Currencies are typically global
        for currency in currencies:
            self._currencies_by_id[currency.id] = currency
            if currency.code:
                code_key = str(currency.code).strip().lower()
                self._currencies_by_code[code_key] = currency.id
        currency_load_time = time.time() - currency_load_start
        logger.info(f"ETL DEBUG: Currency loading took {currency_load_time:.3f}s for {len(self._currencies_by_id)} currencies")
        
        self._loaded = True
        total_load_time = time.time() - load_start
        logger.info(f"Lookup cache loaded in {total_load_time:.3f}s: {len(self._accounts_by_id)} accounts, "
                   f"{len(self._entities_by_id)} entities, {len(self._currencies_by_id)} currencies")
    
    def _build_path_index(self):
        """Build path index by traversing the account tree."""
        def traverse(parent_id: Optional[int], path_parts: List[str], path_separator: str = ' > '):
            """Recursively traverse the tree and build path -> id mappings."""
            for account in self._accounts_tree.get(parent_id, []):
                current_path = path_separator.join(path_parts + [account.name])
                path_key = current_path.lower()
                self._accounts_by_path[path_key] = account.id
                
                # Also try with backslash separator
                if path_separator == ' > ':
                    alt_path = '\\'.join(path_parts + [account.name])
                    self._accounts_by_path[alt_path.lower()] = account.id
                
                # Recurse into children
                traverse(account.id, path_parts + [account.name], path_separator)
        
        # Start from root (parent_id=None)
        traverse(None, [])
    
    def get_account_by_id(self, account_id: int) -> Optional[Any]:
        """Get account by ID."""
        if not self._loaded:
            self.load()
        return self._accounts_by_id.get(account_id)
    
    def get_account_by_code(self, code: str) -> Optional[Any]:
        """Get account by account_code (case-insensitive)."""
        if not self._loaded:
            self.load()
        if not code:
            return None
        code_key = str(code).strip().lower()
        account_id = self._accounts_by_code.get(code_key)
        if account_id:
            return self._accounts_by_id.get(account_id)
        return None
    
    def get_account_by_name(self, name: str) -> Optional[Any]:
        """Get account by name (case-insensitive). Returns first match if duplicates exist."""
        if not self._loaded:
            self.load()
        if not name:
            return None
        name_key = str(name).strip().lower()
        account_ids = self._accounts_by_name.get(name_key, [])
        if account_ids:
            return self._accounts_by_id.get(account_ids[0])
        return None
    
    def get_account_by_path(self, path: str, path_separator: str = ' > ') -> Optional[Any]:
        """Get account by hierarchical path (case-insensitive)."""
        if not self._loaded:
            self.load()
        if not path:
            return None
        
        # Try direct path lookup first
        path_key = str(path).strip().lower()
        account_id = self._accounts_by_path.get(path_key)
        if account_id:
            return self._accounts_by_id.get(account_id)
        
        # If not found, try traversing the tree
        path_parts = [p.strip() for p in str(path).split(path_separator) if p.strip()]
        if not path_parts:
            return None
        
        # Also try with alternative separator
        if path_separator == ' > ':
            alt_path = '\\'.join(path_parts)
            path_key = alt_path.lower()
            account_id = self._accounts_by_path.get(path_key)
            if account_id:
                return self._accounts_by_id.get(account_id)
            # Try traversing with backslash
            path_parts = [p.strip() for p in str(path).split('\\') if p.strip()]
        
        # Traverse tree manually
        parent_id = None
        for part_name in path_parts:
            found = None
            for account in self._accounts_tree.get(parent_id, []):
                if account.name.lower() == part_name.lower():
                    found = account
                    break
            if not found:
                return None
            parent_id = found.id
        
        return self._accounts_by_id.get(parent_id) if parent_id else None
    
    def get_entity_by_id(self, entity_id: int) -> Optional[Any]:
        """Get entity by ID."""
        if not self._loaded:
            self.load()
        return self._entities_by_id.get(entity_id)
    
    def get_entity_by_name(self, name: str) -> Optional[Any]:
        """Get entity by name (case-insensitive)."""
        if not self._loaded:
            self.load()
        if not name:
            return None
        name_key = str(name).strip().lower()
        entity_id = self._entities_by_name.get(name_key)
        if entity_id:
            return self._entities_by_id.get(entity_id)
        return None
    
    def get_currency_by_id(self, currency_id: int) -> Optional[Any]:
        """Get currency by ID."""
        if not self._loaded:
            self.load()
        return self._currencies_by_id.get(currency_id)
    
    def get_currency_by_code(self, code: str) -> Optional[Any]:
        """Get currency by code (case-insensitive)."""
        if not self._loaded:
            self.load()
        if not code:
            return None
        code_key = str(code).strip().lower()
        currency_id = self._currencies_by_code.get(code_key)
        if currency_id:
            return self._currencies_by_id.get(currency_id)
        return None
    
    def clear(self):
        """Clear the cache (useful for testing or memory management)."""
        self._accounts_by_id.clear()
        self._accounts_by_code.clear()
        self._accounts_by_name.clear()
        self._accounts_by_path.clear()
        self._accounts_tree.clear()
        self._entities_by_id.clear()
        self._entities_by_name.clear()
        self._currencies_by_id.clear()
        self._currencies_by_code.clear()
        self._loaded = False

