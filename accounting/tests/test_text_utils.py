"""
test_text_utils.py

Unit tests for text normalization and similarity utilities.
"""

import pytest

from accounting.services.text_utils import (
    normalize_description,
    extract_tokens,
    TFIDFVectorizer,
    cosine_similarity_sparse,
    compute_text_similarity,
    extract_reference_numbers,
    match_reference_numbers,
    TextMatcher,
    DEFAULT_STOPWORDS,
    DEFAULT_VENDOR_ALIASES,
)


# ----------------------------------------------------------------------
# Tests: normalize_description
# ----------------------------------------------------------------------

class TestNormalizeDescription:
    """Tests for the normalize_description function."""
    
    def test_lowercase(self):
        """Test that text is lowercased."""
        result = normalize_description("HELLO WORLD")
        assert "hello" in result
        assert "world" in result
    
    def test_accent_removal(self):
        """Test that accents are removed."""
        result = normalize_description("Pagamento à Vista São Paulo")
        assert "a" in result  # à → a
        assert "sao" in result  # São → sao
    
    def test_special_char_removal(self):
        """Test that special characters are removed."""
        result = normalize_description("Test@123#456$789")
        assert "@" not in result
        assert "#" not in result
        assert "$" not in result
    
    def test_stopword_removal(self):
        """Test that stopwords are removed."""
        result = normalize_description("the quick brown fox and the lazy dog")
        assert "the" not in result.split()
        assert "and" not in result.split()
        assert "quick" in result
        assert "brown" in result
    
    def test_vendor_alias_mapping(self):
        """Test that vendor aliases are mapped to canonical names."""
        result = normalize_description("Pagamento via PayPal")
        assert "paypal" in result
        
        result = normalize_description("Transferencia ITAÚ")
        assert "itau" in result
    
    def test_min_token_length(self):
        """Test that short tokens are removed."""
        result = normalize_description("a b c test word", min_token_length=3)
        assert "a" not in result.split()
        assert "b" not in result.split()
        assert "c" not in result.split()
        assert "test" in result
        assert "word" in result
    
    def test_preserve_numbers(self):
        """Test number preservation option."""
        result_with = normalize_description("Invoice 12345 paid", preserve_numbers=True)
        assert "12345" in result_with
        
        result_without = normalize_description("Invoice 12345 paid", preserve_numbers=False)
        assert "12345" not in result_without
    
    def test_empty_string(self):
        """Test handling of empty string."""
        result = normalize_description("")
        assert result == ""
    
    def test_none_input(self):
        """Test handling of None input."""
        result = normalize_description(None)
        assert result == ""
    
    def test_custom_stopwords(self):
        """Test with custom stopwords."""
        custom_stopwords = {"test", "word"}
        result = normalize_description("test word hello", stopwords=custom_stopwords)
        assert "test" not in result.split()
        assert "word" not in result.split()
        assert "hello" in result


# ----------------------------------------------------------------------
# Tests: extract_tokens
# ----------------------------------------------------------------------

class TestExtractTokens:
    """Tests for the extract_tokens function."""
    
    def test_basic_extraction(self):
        """Test basic token extraction."""
        tokens = extract_tokens("Hello World Test")
        assert "hello" in tokens
        assert "world" in tokens
        assert "test" in tokens
    
    def test_stopword_filtered(self):
        """Test that stopwords are filtered out."""
        tokens = extract_tokens("the quick brown fox")
        assert "the" not in tokens
        assert "quick" in tokens
    
    def test_empty_string(self):
        """Test with empty string."""
        tokens = extract_tokens("")
        assert tokens == []


# ----------------------------------------------------------------------
# Tests: TFIDFVectorizer
# ----------------------------------------------------------------------

class TestTFIDFVectorizer:
    """Tests for the TFIDFVectorizer class."""
    
    def test_fit_creates_vocabulary(self):
        """Test that fit creates vocabulary."""
        docs = ["hello world", "hello there", "world peace"]
        vectorizer = TFIDFVectorizer()
        vectorizer.fit(docs)
        
        assert "hello" in vectorizer.vocabulary
        assert "world" in vectorizer.vocabulary
        assert "there" in vectorizer.vocabulary
        assert "peace" in vectorizer.vocabulary
    
    def test_fit_computes_idf(self):
        """Test that fit computes IDF values."""
        docs = ["hello world", "hello there", "world peace"]
        vectorizer = TFIDFVectorizer()
        vectorizer.fit(docs)
        
        # "hello" appears in 2/3 docs, "peace" in 1/3
        # IDF for "peace" should be higher
        assert vectorizer.idf["peace"] > vectorizer.idf["hello"]
    
    def test_transform_creates_vectors(self):
        """Test that transform creates TF-IDF vectors."""
        docs = ["hello world", "hello there"]
        vectorizer = TFIDFVectorizer()
        vectorizer.fit(docs)
        vectors = vectorizer.transform(docs)
        
        assert len(vectors) == 2
        assert "hello" in vectors[0]
        assert "world" in vectors[0]
    
    def test_fit_transform(self):
        """Test combined fit_transform."""
        docs = ["hello world", "hello there"]
        vectorizer = TFIDFVectorizer()
        vectors = vectorizer.fit_transform(docs)
        
        assert len(vectors) == 2
        assert vectorizer._fitted
    
    def test_transform_before_fit_raises(self):
        """Test that transform before fit raises error."""
        vectorizer = TFIDFVectorizer()
        with pytest.raises(ValueError):
            vectorizer.transform(["hello"])
    
    def test_empty_document(self):
        """Test handling of empty documents."""
        docs = ["hello world", "", "test"]
        vectorizer = TFIDFVectorizer()
        vectors = vectorizer.fit_transform(docs)
        
        assert vectors[1] == {}


# ----------------------------------------------------------------------
# Tests: cosine_similarity_sparse
# ----------------------------------------------------------------------

class TestCosineSimilaritySparse:
    """Tests for sparse cosine similarity."""
    
    def test_identical_vectors(self):
        """Test that identical vectors have similarity 1.0."""
        vec = {"a": 1.0, "b": 2.0, "c": 3.0}
        sim = cosine_similarity_sparse(vec, vec)
        assert abs(sim - 1.0) < 0.0001
    
    def test_orthogonal_vectors(self):
        """Test that orthogonal vectors have similarity 0.0."""
        vec1 = {"a": 1.0, "b": 0.0}
        vec2 = {"c": 1.0, "d": 0.0}
        sim = cosine_similarity_sparse(vec1, vec2)
        assert sim == 0.0
    
    def test_partial_overlap(self):
        """Test vectors with partial overlap."""
        vec1 = {"a": 1.0, "b": 1.0}
        vec2 = {"a": 1.0, "c": 1.0}
        sim = cosine_similarity_sparse(vec1, vec2)
        assert 0.0 < sim < 1.0
    
    def test_empty_vectors(self):
        """Test with empty vectors."""
        assert cosine_similarity_sparse({}, {"a": 1.0}) == 0.0
        assert cosine_similarity_sparse({"a": 1.0}, {}) == 0.0
        assert cosine_similarity_sparse({}, {}) == 0.0


# ----------------------------------------------------------------------
# Tests: compute_text_similarity
# ----------------------------------------------------------------------

class TestComputeTextSimilarity:
    """Tests for text similarity computation."""
    
    def test_identical_texts_jaccard(self):
        """Test Jaccard similarity of identical texts."""
        sim = compute_text_similarity("hello world", "hello world", method="jaccard")
        assert sim == 1.0
    
    def test_different_texts_jaccard(self):
        """Test Jaccard similarity of different texts."""
        sim = compute_text_similarity("hello world", "goodbye moon", method="jaccard")
        assert sim == 0.0
    
    def test_partial_overlap_jaccard(self):
        """Test Jaccard similarity with partial overlap."""
        sim = compute_text_similarity("hello world", "hello moon", method="jaccard")
        assert 0.0 < sim < 1.0
    
    def test_overlap_coefficient(self):
        """Test overlap coefficient method."""
        sim = compute_text_similarity("hello", "hello world", method="overlap")
        assert sim == 1.0  # "hello" is fully contained
    
    def test_tfidf_method(self):
        """Test TF-IDF similarity method."""
        sim = compute_text_similarity("hello world", "hello world", method="tfidf")
        assert sim > 0.9  # Should be high for identical texts
    
    def test_invalid_method_raises(self):
        """Test that invalid method raises error."""
        with pytest.raises(ValueError):
            compute_text_similarity("hello", "world", method="invalid")


# ----------------------------------------------------------------------
# Tests: extract_reference_numbers
# ----------------------------------------------------------------------

class TestExtractReferenceNumbers:
    """Tests for reference number extraction."""
    
    def test_invoice_numbers(self):
        """Test extraction of invoice numbers."""
        refs = extract_reference_numbers("Payment for INV-123456")
        assert "123456" in refs
        
        refs = extract_reference_numbers("NF 78901234")
        assert "78901234" in refs
    
    def test_order_numbers(self):
        """Test extraction of order numbers."""
        refs = extract_reference_numbers("Order ORD-555666")
        assert "555666" in refs
        
        refs = extract_reference_numbers("Pedido 123456789")
        assert "123456789" in refs
    
    def test_transaction_ids(self):
        """Test extraction of transaction IDs."""
        refs = extract_reference_numbers("TXN-987654321")
        assert "987654321" in refs
    
    def test_pure_numeric(self):
        """Test extraction of pure numeric sequences."""
        refs = extract_reference_numbers("Reference 1234567890")
        assert "1234567890" in refs
    
    def test_no_references(self):
        """Test text with no reference numbers."""
        refs = extract_reference_numbers("No reference here")
        assert refs == []
    
    def test_deduplication(self):
        """Test that duplicate references are removed."""
        refs = extract_reference_numbers("INV-123456 ref 123456")
        assert refs.count("123456") == 1


# ----------------------------------------------------------------------
# Tests: match_reference_numbers
# ----------------------------------------------------------------------

class TestMatchReferenceNumbers:
    """Tests for reference number matching."""
    
    def test_matching_references(self):
        """Test detection of matching references."""
        has_match, matching = match_reference_numbers(
            "Payment for INV-123456",
            "Invoice 123456 received"
        )
        assert has_match is True
        assert "123456" in matching
    
    def test_no_matching_references(self):
        """Test when references don't match."""
        has_match, matching = match_reference_numbers(
            "Payment for INV-123456",
            "Invoice 789012 received"
        )
        assert has_match is False
        assert matching == []
    
    def test_no_references_in_either(self):
        """Test when neither text has references."""
        has_match, matching = match_reference_numbers(
            "General payment",
            "General receipt"
        )
        assert has_match is False
        assert matching == []


# ----------------------------------------------------------------------
# Tests: TextMatcher
# ----------------------------------------------------------------------

class TestTextMatcher:
    """Tests for the TextMatcher class."""
    
    def test_basic_match_score(self):
        """Test basic match score computation."""
        matcher = TextMatcher()
        scores = matcher.compute_match_score(
            "Payment PayPal INV-123456",
            "Invoice 123456 PayPal"
        )
        
        # Should have high ref_match and vendor_match
        assert scores["ref_match"] == 1.0
        assert scores["vendor_match"] == 1.0
        assert scores["overall"] > 0.5
    
    def test_no_match(self):
        """Test score for non-matching texts."""
        matcher = TextMatcher()
        scores = matcher.compute_match_score(
            "Random text here",
            "Completely different content"
        )
        
        assert scores["ref_match"] == 0.0
        assert scores["vendor_match"] == 0.0
        assert scores["overall"] < 0.5
    
    def test_vendor_only_match(self):
        """Test score when only vendor matches."""
        matcher = TextMatcher()
        scores = matcher.compute_match_score(
            "Payment via PayPal",
            "Refund from PayPal"
        )
        
        assert scores["vendor_match"] == 1.0
        assert scores["ref_match"] == 0.0
        assert scores["vendor_canonical"] == "paypal"
    
    def test_fit_corpus(self):
        """Test fitting with a corpus."""
        matcher = TextMatcher()
        corpus = [
            "Payment via PayPal",
            "Invoice from Amazon",
            "Transfer to Bank"
        ]
        matcher.fit_corpus(corpus)
        
        assert matcher.vectorizer is not None
        assert matcher.vectorizer._fitted
    
    def test_custom_weights(self):
        """Test with custom scoring weights."""
        matcher = TextMatcher()
        
        # All weight on ref matching
        scores = matcher.compute_match_score(
            "INV-123456",
            "123456",
            ref_weight=1.0,
            vendor_weight=0.0,
            similarity_weight=0.0
        )
        
        assert scores["overall"] == scores["ref_match"]

