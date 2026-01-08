"""
Tests for the Safe Formula Evaluator.

Tests cover:
- Basic arithmetic operations
- L-token substitution with word boundaries
- Error handling
- Edge cases
"""

from decimal import Decimal
from django.test import TestCase

from accounting.services.formula_evaluator import (
    SafeFormulaEvaluator,
    evaluate_formula,
    validate_formula,
    InvalidFormulaError,
    UndefinedLineError,
)


class SafeFormulaEvaluatorTest(TestCase):
    """Test cases for SafeFormulaEvaluator."""
    
    def setUp(self):
        self.evaluator = SafeFormulaEvaluator()
    
    # =========================================================================
    # Basic Arithmetic Tests
    # =========================================================================
    
    def test_simple_addition(self):
        """Test simple addition: L1 + L2"""
        line_values = {1: Decimal('100'), 2: Decimal('50')}
        result = self.evaluator.evaluate("L1 + L2", line_values)
        self.assertEqual(result, Decimal('150'))
    
    def test_simple_subtraction(self):
        """Test simple subtraction: L1 - L2"""
        line_values = {1: Decimal('100'), 2: Decimal('30')}
        result = self.evaluator.evaluate("L1 - L2", line_values)
        self.assertEqual(result, Decimal('70'))
    
    def test_simple_multiplication(self):
        """Test simple multiplication: L1 * L2"""
        line_values = {1: Decimal('10'), 2: Decimal('5')}
        result = self.evaluator.evaluate("L1 * L2", line_values)
        self.assertEqual(result, Decimal('50'))
    
    def test_simple_division(self):
        """Test simple division: L1 / L2"""
        line_values = {1: Decimal('100'), 2: Decimal('4')}
        result = self.evaluator.evaluate("L1 / L2", line_values)
        self.assertEqual(result, Decimal('25'))
    
    def test_complex_expression(self):
        """Test complex expression: (L1 + L2) - (L3 + L4)"""
        line_values = {
            1: Decimal('100'),
            2: Decimal('50'),
            3: Decimal('30'),
            4: Decimal('20'),
        }
        result = self.evaluator.evaluate("(L1 + L2) - (L3 + L4)", line_values)
        self.assertEqual(result, Decimal('100'))  # (100+50) - (30+20) = 100
    
    def test_operator_precedence(self):
        """Test operator precedence: L1 + L2 * L3"""
        line_values = {1: Decimal('10'), 2: Decimal('5'), 3: Decimal('2')}
        result = self.evaluator.evaluate("L1 + L2 * L3", line_values)
        self.assertEqual(result, Decimal('20'))  # 10 + (5*2) = 20
    
    # =========================================================================
    # L-Token Word Boundary Tests (Critical Bug Fix)
    # =========================================================================
    
    def test_l1_does_not_match_l10(self):
        """CRITICAL: Ensure L1 doesn't match in L10 (word boundary)."""
        line_values = {
            1: Decimal('100'),
            10: Decimal('25'),
        }
        result = self.evaluator.evaluate("L1 + L10", line_values)
        self.assertEqual(result, Decimal('125'))  # 100 + 25, NOT 100 + 10025
    
    def test_l1_does_not_match_l11_l12(self):
        """CRITICAL: Ensure L1 doesn't match in L11, L12, etc."""
        line_values = {
            1: Decimal('100'),
            11: Decimal('10'),
            12: Decimal('5'),
        }
        result = self.evaluator.evaluate("L1 + L11 + L12", line_values)
        self.assertEqual(result, Decimal('115'))  # 100 + 10 + 5
    
    def test_l2_does_not_match_l20_l21(self):
        """Ensure L2 doesn't match in L20, L21."""
        line_values = {
            2: Decimal('50'),
            20: Decimal('200'),
            21: Decimal('210'),
        }
        result = self.evaluator.evaluate("L2 + L20 + L21", line_values)
        self.assertEqual(result, Decimal('460'))  # 50 + 200 + 210
    
    # =========================================================================
    # Negative Value Tests
    # =========================================================================
    
    def test_negative_values(self):
        """Test handling of negative values in line_values."""
        line_values = {
            1: Decimal('-100'),
            2: Decimal('50'),
        }
        result = self.evaluator.evaluate("L1 + L2", line_values)
        self.assertEqual(result, Decimal('-50'))
    
    def test_unary_minus(self):
        """Test unary minus in formula."""
        line_values = {1: Decimal('100')}
        result = self.evaluator.evaluate("-L1", line_values)
        self.assertEqual(result, Decimal('-100'))
    
    def test_double_negative(self):
        """Test double negative."""
        line_values = {1: Decimal('-100')}
        result = self.evaluator.evaluate("-L1", line_values)
        self.assertEqual(result, Decimal('100'))  # -(-100) = 100
    
    # =========================================================================
    # Decimal Precision Tests
    # =========================================================================
    
    def test_decimal_precision(self):
        """Test that decimal precision is maintained."""
        line_values = {
            1: Decimal('100.50'),
            2: Decimal('33.33'),
        }
        result = self.evaluator.evaluate("L1 + L2", line_values)
        self.assertEqual(result, Decimal('133.83'))
    
    def test_division_precision(self):
        """Test division maintains precision."""
        line_values = {
            1: Decimal('100'),
            2: Decimal('3'),
        }
        result = self.evaluator.evaluate("L1 / L2", line_values)
        # Should have high precision for Decimal division
        self.assertAlmostEqual(float(result), 33.3333, places=3)
    
    # =========================================================================
    # Edge Cases
    # =========================================================================
    
    def test_empty_formula_returns_zero(self):
        """Empty formula should return 0."""
        result = self.evaluator.evaluate("", {})
        self.assertEqual(result, Decimal('0.00'))
    
    def test_whitespace_formula_returns_zero(self):
        """Whitespace-only formula should return 0."""
        result = self.evaluator.evaluate("   ", {})
        self.assertEqual(result, Decimal('0.00'))
    
    def test_division_by_zero_returns_zero(self):
        """Division by zero should return 0 (graceful handling)."""
        line_values = {1: Decimal('100'), 2: Decimal('0')}
        result = self.evaluator.evaluate("L1 / L2", line_values)
        self.assertEqual(result, Decimal('0.00'))
    
    def test_parentheses_with_spaces(self):
        """Test parentheses with spaces."""
        line_values = {1: Decimal('10'), 2: Decimal('5')}
        result = self.evaluator.evaluate("( L1 + L2 ) * 2", line_values)
        self.assertEqual(result, Decimal('30'))
    
    def test_constant_multiplication(self):
        """Test multiplication by constant."""
        line_values = {1: Decimal('100')}
        result = self.evaluator.evaluate("L1 * 0.5", line_values)
        self.assertEqual(result, Decimal('50'))
    
    # =========================================================================
    # Error Handling Tests
    # =========================================================================
    
    def test_undefined_line_raises_error(self):
        """Referencing undefined line should raise UndefinedLineError."""
        line_values = {1: Decimal('100')}
        with self.assertRaises(UndefinedLineError):
            self.evaluator.evaluate("L1 + L2", line_values)
    
    def test_invalid_characters_raises_error(self):
        """Invalid characters should raise InvalidFormulaError."""
        line_values = {1: Decimal('100')}
        with self.assertRaises(InvalidFormulaError):
            self.evaluator.evaluate("L1 + eval('evil')", line_values)
    
    def test_unbalanced_parentheses_raises_error(self):
        """Unbalanced parentheses should raise InvalidFormulaError."""
        line_values = {1: Decimal('100'), 2: Decimal('50')}
        with self.assertRaises(InvalidFormulaError):
            self.evaluator.evaluate("(L1 + L2", line_values)
    
    def test_code_injection_blocked(self):
        """Ensure code injection attempts are blocked."""
        line_values = {1: Decimal('100')}
        
        # These should all raise InvalidFormulaError
        injection_attempts = [
            "__import__('os').system('ls')",
            "exec('print(1)')",
            "open('/etc/passwd').read()",
            "lambda: 1",
            "[x for x in range(10)]",
        ]
        
        for injection in injection_attempts:
            with self.assertRaises(InvalidFormulaError):
                self.evaluator.evaluate(injection, line_values)
    
    # =========================================================================
    # Validation Tests
    # =========================================================================
    
    def test_validate_valid_formula(self):
        """Test validation of valid formula."""
        errors = validate_formula("L1 + L2 - L3", available_lines=[1, 2, 3])
        self.assertEqual(errors, [])
    
    def test_validate_invalid_characters(self):
        """Test validation catches invalid characters."""
        errors = validate_formula("L1 + eval('x')")
        self.assertTrue(any('Invalid' in e for e in errors))
    
    def test_validate_undefined_line(self):
        """Test validation catches undefined lines."""
        errors = validate_formula("L1 + L5", available_lines=[1, 2, 3])
        self.assertTrue(any('L5' in e for e in errors))
    
    def test_validate_unbalanced_parentheses(self):
        """Test validation catches unbalanced parentheses."""
        errors = validate_formula("(L1 + L2")
        self.assertTrue(any('parentheses' in e.lower() for e in errors))


class ConvenienceFunctionTest(TestCase):
    """Test convenience functions."""
    
    def test_evaluate_formula_function(self):
        """Test the evaluate_formula convenience function."""
        line_values = {1: Decimal('100'), 2: Decimal('50')}
        result = evaluate_formula("L1 + L2", line_values)
        self.assertEqual(result, Decimal('150'))
    
    def test_validate_formula_function(self):
        """Test the validate_formula convenience function."""
        errors = validate_formula("L1 + L2", available_lines=[1, 2])
        self.assertEqual(errors, [])

