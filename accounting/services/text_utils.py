"""
text_utils.py

Text normalization and similarity utilities for reconciliation matching.
Provides description normalization, vendor alias mapping, and TF-IDF fallback
similarity for cases where embeddings are not available.
"""

from __future__ import annotations

import re
import unicodedata
from collections import Counter
from decimal import Decimal
from functools import lru_cache
from typing import Dict, List, Optional, Set, Tuple

import math


# ----------------------------------------------------------------------
# Default stopwords for financial descriptions
# ----------------------------------------------------------------------
DEFAULT_STOPWORDS: Set[str] = {
    # English common words
    "the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for",
    "of", "with", "by", "from", "as", "is", "was", "are", "were", "been",
    "be", "have", "has", "had", "do", "does", "did", "will", "would",
    "could", "should", "may", "might", "must", "shall", "can", "need",
    "this", "that", "these", "those", "it", "its", "they", "them", "their",
    # Portuguese common words
    "de", "da", "do", "das", "dos", "e", "em", "no", "na", "nos", "nas",
    "para", "por", "com", "sem", "uma", "um", "uns", "umas", "o", "a",
    "os", "as", "que", "se", "ou", "foi", "ser", "estar", "ter", "haver",
    # Financial common terms
    "ref", "referencia", "reference", "pagamento", "payment", "pag", "pgt",
    "transferencia", "transfer", "transf", "deposito", "deposit", "dep",
    "credito", "credit", "cred", "debito", "debit", "deb",
    "conta", "account", "acc", "ct", "numero", "number", "num", "nr",
    "data", "date", "dt", "valor", "value", "val", "total", "tot",
}

# ----------------------------------------------------------------------
# Default vendor aliases (common variations → canonical name)
# ----------------------------------------------------------------------
DEFAULT_VENDOR_ALIASES: Dict[str, str] = {
    # Payment processors
    "paypal": "paypal",
    "pay pal": "paypal",
    "pp": "paypal",
    "stripe": "stripe",
    "strp": "stripe",
    "square": "square",
    "sq": "square",
    
    # Banks
    "itau": "itau",
    "itaú": "itau",
    "itau unibanco": "itau",
    "bradesco": "bradesco",
    "brad": "bradesco",
    "santander": "santander",
    "sant": "santander",
    "banco do brasil": "banco_do_brasil",
    "bb": "banco_do_brasil",
    "caixa": "caixa",
    "cef": "caixa",
    "caixa economica": "caixa",
    "nubank": "nubank",
    "nu": "nubank",
    "inter": "banco_inter",
    "banco inter": "banco_inter",
    
    # Common vendors
    "amazon": "amazon",
    "amzn": "amazon",
    "aws": "amazon_aws",
    "amazon web services": "amazon_aws",
    "google": "google",
    "goog": "google",
    "microsoft": "microsoft",
    "msft": "microsoft",
    "ms": "microsoft",
    "uber": "uber",
    "uber eats": "uber_eats",
    "ubereats": "uber_eats",
    "ifood": "ifood",
    "netflix": "netflix",
    "nflx": "netflix",
    "spotify": "spotify",
    
    # Utilities
    "light": "light",
    "cedae": "cedae",
    "naturgy": "naturgy",
    "gas natural": "naturgy",
    "vivo": "vivo",
    "telefonica": "vivo",
    "claro": "claro",
    "tim": "tim",
    "oi": "oi",
}


def normalize_description(
    text: str,
    *,
    stopwords: Optional[Set[str]] = None,
    vendor_aliases: Optional[Dict[str, str]] = None,
    preserve_numbers: bool = True,
    min_token_length: int = 2,
) -> str:
    """
    Normalize a financial description for comparison.
    
    Steps:
    1. Unicode normalization (NFD → strip accents → NFC)
    2. Lowercase
    3. Remove special characters (keep alphanumeric and spaces)
    4. Tokenize
    5. Remove stopwords
    6. Apply vendor alias mapping
    7. Remove short tokens
    8. Rejoin with single spaces
    
    Args:
        text: Raw description text
        stopwords: Set of words to remove (uses DEFAULT_STOPWORDS if None)
        vendor_aliases: Dict mapping variations to canonical names (uses DEFAULT_VENDOR_ALIASES if None)
        preserve_numbers: If True, keep numeric tokens; if False, remove them
        min_token_length: Minimum token length to keep
    
    Returns:
        Normalized description string
    """
    if not text:
        return ""
    
    stopwords = stopwords if stopwords is not None else DEFAULT_STOPWORDS
    vendor_aliases = vendor_aliases if vendor_aliases is not None else DEFAULT_VENDOR_ALIASES
    
    # Step 1: Unicode normalization - remove accents
    text = unicodedata.normalize("NFD", text)
    text = "".join(c for c in text if unicodedata.category(c) != "Mn")
    text = unicodedata.normalize("NFC", text)
    
    # Step 2: Lowercase
    text = text.lower()
    
    # Step 3: Remove special characters (keep alphanumeric, spaces, and hyphens)
    text = re.sub(r"[^a-z0-9\s\-]", " ", text)
    
    # Step 4: Tokenize
    tokens = text.split()
    
    # Step 5: Remove stopwords
    tokens = [t for t in tokens if t not in stopwords]
    
    # Step 6: Apply vendor alias mapping
    # Check multi-word aliases first
    text_for_alias = " ".join(tokens)
    for alias, canonical in sorted(vendor_aliases.items(), key=lambda x: -len(x[0])):
        if alias in text_for_alias:
            text_for_alias = text_for_alias.replace(alias, canonical)
    tokens = text_for_alias.split()
    
    # Step 7: Filter by length and optionally remove numbers
    result_tokens = []
    for t in tokens:
        if len(t) < min_token_length:
            continue
        if not preserve_numbers and t.isdigit():
            continue
        result_tokens.append(t)
    
    # Step 8: Rejoin
    return " ".join(result_tokens)


def extract_tokens(text: str, stopwords: Optional[Set[str]] = None) -> List[str]:
    """
    Extract normalized tokens from text for TF-IDF computation.
    
    Args:
        text: Input text
        stopwords: Set of words to exclude
    
    Returns:
        List of normalized tokens
    """
    normalized = normalize_description(text, stopwords=stopwords)
    return normalized.split() if normalized else []


@lru_cache(maxsize=10000)
def _cached_extract_tokens(text: str) -> Tuple[str, ...]:
    """Cached version of token extraction for repeated lookups."""
    return tuple(extract_tokens(text))


class TFIDFVectorizer:
    """
    Simple TF-IDF vectorizer for text similarity computation.
    
    This is a fallback for when embeddings are not available.
    Uses term frequency-inverse document frequency weighting.
    """
    
    def __init__(self, stopwords: Optional[Set[str]] = None):
        self.stopwords = stopwords if stopwords is not None else DEFAULT_STOPWORDS
        self.vocabulary: Dict[str, int] = {}
        self.idf: Dict[str, float] = {}
        self.doc_count = 0
        self._fitted = False
    
    def fit(self, documents: List[str]) -> "TFIDFVectorizer":
        """
        Fit the vectorizer on a corpus of documents.
        
        Args:
            documents: List of text documents
        
        Returns:
            self
        """
        self.doc_count = len(documents)
        if self.doc_count == 0:
            self._fitted = True
            return self
        
        # Count document frequency for each term
        doc_freq: Counter = Counter()
        
        for doc in documents:
            tokens = set(extract_tokens(doc, self.stopwords))
            doc_freq.update(tokens)
        
        # Build vocabulary and compute IDF
        self.vocabulary = {term: idx for idx, term in enumerate(sorted(doc_freq.keys()))}
        
        for term, df in doc_freq.items():
            # IDF with smoothing: log((N + 1) / (df + 1)) + 1
            self.idf[term] = math.log((self.doc_count + 1) / (df + 1)) + 1
        
        self._fitted = True
        return self
    
    def transform(self, documents: List[str]) -> List[Dict[str, float]]:
        """
        Transform documents to TF-IDF vectors.
        
        Args:
            documents: List of text documents
        
        Returns:
            List of sparse vectors (dicts mapping term to TF-IDF weight)
        """
        if not self._fitted:
            raise ValueError("Vectorizer must be fitted before transform")
        
        result = []
        for doc in documents:
            tokens = extract_tokens(doc, self.stopwords)
            if not tokens:
                result.append({})
                continue
            
            # Compute term frequency
            tf = Counter(tokens)
            total_terms = len(tokens)
            
            # Compute TF-IDF
            vector = {}
            for term, count in tf.items():
                if term in self.idf:
                    tf_norm = count / total_terms
                    vector[term] = tf_norm * self.idf[term]
            
            result.append(vector)
        
        return result
    
    def fit_transform(self, documents: List[str]) -> List[Dict[str, float]]:
        """Fit and transform in one step."""
        return self.fit(documents).transform(documents)


def cosine_similarity_sparse(
    vec1: Dict[str, float],
    vec2: Dict[str, float],
) -> float:
    """
    Compute cosine similarity between two sparse vectors.
    
    Args:
        vec1: First sparse vector (dict mapping term to weight)
        vec2: Second sparse vector
    
    Returns:
        Cosine similarity in [0, 1]
    """
    if not vec1 or not vec2:
        return 0.0
    
    # Find common terms
    common_terms = set(vec1.keys()) & set(vec2.keys())
    if not common_terms:
        return 0.0
    
    # Compute dot product
    dot_product = sum(vec1[t] * vec2[t] for t in common_terms)
    
    # Compute magnitudes
    mag1 = math.sqrt(sum(v * v for v in vec1.values()))
    mag2 = math.sqrt(sum(v * v for v in vec2.values()))
    
    if mag1 == 0 or mag2 == 0:
        return 0.0
    
    return dot_product / (mag1 * mag2)


def compute_text_similarity(
    text1: str,
    text2: str,
    method: str = "jaccard",
) -> float:
    """
    Compute text similarity between two descriptions.
    
    Args:
        text1: First text
        text2: Second text
        method: Similarity method - "jaccard", "overlap", or "tfidf"
    
    Returns:
        Similarity score in [0, 1]
    """
    tokens1 = set(extract_tokens(text1))
    tokens2 = set(extract_tokens(text2))
    
    if not tokens1 or not tokens2:
        return 0.0
    
    if method == "jaccard":
        # Jaccard similarity: |A ∩ B| / |A ∪ B|
        intersection = len(tokens1 & tokens2)
        union = len(tokens1 | tokens2)
        return intersection / union if union > 0 else 0.0
    
    elif method == "overlap":
        # Overlap coefficient: |A ∩ B| / min(|A|, |B|)
        intersection = len(tokens1 & tokens2)
        min_size = min(len(tokens1), len(tokens2))
        return intersection / min_size if min_size > 0 else 0.0
    
    elif method == "tfidf":
        # Use TF-IDF vectorization
        vectorizer = TFIDFVectorizer()
        vectors = vectorizer.fit_transform([text1, text2])
        return cosine_similarity_sparse(vectors[0], vectors[1])
    
    else:
        raise ValueError(f"Unknown similarity method: {method}")


def extract_reference_numbers(text: str) -> List[str]:
    """
    Extract potential reference numbers from text.
    
    Looks for patterns like:
    - Invoice numbers: INV-12345, NF-12345
    - Order numbers: ORD-12345, PED-12345
    - Transaction IDs: TXN-12345, ID-12345
    - Pure numeric sequences: 123456789
    
    Args:
        text: Input text
    
    Returns:
        List of extracted reference numbers
    """
    if not text:
        return []
    
    patterns = [
        r'\b(?:INV|NF|NFE|NFSE|NOTA|INVOICE)[-\s]?(\d{4,})\b',
        r'\b(?:ORD|PED|PEDIDO|ORDER)[-\s]?(\d{4,})\b',
        r'\b(?:TXN|TX|ID|REF)[-\s]?(\d{4,})\b',
        r'\b(?:DOC|DOCUMENTO)[-\s]?(\d{4,})\b',
        r'\b(\d{6,})\b',  # Pure numeric sequences (6+ digits)
    ]
    
    results = []
    text_upper = text.upper()
    
    for pattern in patterns:
        matches = re.findall(pattern, text_upper, re.IGNORECASE)
        results.extend(matches)
    
    # Deduplicate while preserving order
    seen = set()
    unique_results = []
    for ref in results:
        if ref not in seen:
            seen.add(ref)
            unique_results.append(ref)
    
    return unique_results


def match_reference_numbers(text1: str, text2: str) -> Tuple[bool, List[str]]:
    """
    Check if two texts share any reference numbers.
    
    Args:
        text1: First text
        text2: Second text
    
    Returns:
        Tuple of (has_match, list_of_matching_references)
    """
    refs1 = set(extract_reference_numbers(text1))
    refs2 = set(extract_reference_numbers(text2))
    
    common = refs1 & refs2
    return (len(common) > 0, list(common))


class TextMatcher:
    """
    High-level text matching utility for reconciliation.
    
    Combines multiple matching strategies:
    1. Reference number matching (exact)
    2. Vendor/entity matching (alias-aware)
    3. Description similarity (TF-IDF or Jaccard)
    """
    
    def __init__(
        self,
        stopwords: Optional[Set[str]] = None,
        vendor_aliases: Optional[Dict[str, str]] = None,
    ):
        self.stopwords = stopwords if stopwords is not None else DEFAULT_STOPWORDS
        self.vendor_aliases = vendor_aliases if vendor_aliases is not None else DEFAULT_VENDOR_ALIASES
        self.vectorizer: Optional[TFIDFVectorizer] = None
    
    def fit_corpus(self, documents: List[str]) -> "TextMatcher":
        """
        Fit the TF-IDF vectorizer on a corpus for better similarity computation.
        
        Args:
            documents: List of all descriptions (banks + books)
        
        Returns:
            self
        """
        self.vectorizer = TFIDFVectorizer(self.stopwords)
        self.vectorizer.fit(documents)
        return self
    
    def compute_match_score(
        self,
        text1: str,
        text2: str,
        *,
        ref_weight: float = 0.4,
        vendor_weight: float = 0.3,
        similarity_weight: float = 0.3,
    ) -> Dict[str, float]:
        """
        Compute a comprehensive text match score.
        
        Args:
            text1: First text (e.g., bank description)
            text2: Second text (e.g., journal entry description)
            ref_weight: Weight for reference number matching
            vendor_weight: Weight for vendor matching
            similarity_weight: Weight for text similarity
        
        Returns:
            Dict with component scores and overall score
        """
        result = {
            "ref_match": 0.0,
            "ref_numbers": [],
            "vendor_match": 0.0,
            "vendor_canonical": None,
            "similarity": 0.0,
            "overall": 0.0,
        }
        
        # 1. Reference number matching
        has_ref_match, matching_refs = match_reference_numbers(text1, text2)
        if has_ref_match:
            result["ref_match"] = 1.0
            result["ref_numbers"] = matching_refs
        
        # 2. Vendor matching
        norm1 = normalize_description(text1, vendor_aliases=self.vendor_aliases)
        norm2 = normalize_description(text2, vendor_aliases=self.vendor_aliases)
        
        tokens1 = set(norm1.split())
        tokens2 = set(norm2.split())
        
        # Check if any vendor canonical names match
        vendor_canonicals = set(self.vendor_aliases.values())
        vendors1 = tokens1 & vendor_canonicals
        vendors2 = tokens2 & vendor_canonicals
        common_vendors = vendors1 & vendors2
        
        if common_vendors:
            result["vendor_match"] = 1.0
            result["vendor_canonical"] = list(common_vendors)[0]
        
        # 3. Text similarity
        if self.vectorizer and self.vectorizer._fitted:
            # Use fitted TF-IDF
            vectors = self.vectorizer.transform([text1, text2])
            result["similarity"] = cosine_similarity_sparse(vectors[0], vectors[1])
        else:
            # Fallback to Jaccard
            result["similarity"] = compute_text_similarity(text1, text2, method="jaccard")
        
        # 4. Overall score
        result["overall"] = (
            ref_weight * result["ref_match"] +
            vendor_weight * result["vendor_match"] +
            similarity_weight * result["similarity"]
        )
        
        return result

