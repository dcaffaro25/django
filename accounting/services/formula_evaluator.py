"""
Safe Formula Evaluator for Financial Statement Lines

Evaluates formulas with L-token references without using eval().
Supports: + - * / ( ) and Ln tokens (n = line number)
"""

import re
import logging
from decimal import Decimal, InvalidOperation
from typing import Dict, List, Tuple, Optional

log = logging.getLogger(__name__)


class FormulaError(Exception):
    """Base exception for formula evaluation errors."""
    pass


class InvalidFormulaError(FormulaError):
    """Raised when formula syntax is invalid."""
    pass


class UndefinedLineError(FormulaError):
    """Raised when a referenced line has not been calculated yet."""
    pass


class SafeFormulaEvaluator:
    """
    Evaluates formulas with L-token references safely.
    
    Supports:
    - Line references: L1, L2, L10, L100, etc.
    - Operators: + - * /
    - Parentheses: ( )
    - Decimal numbers: 0.5, 100.00, etc.
    
    Does NOT use eval() - implements a safe expression parser.
    
    Example:
        evaluator = SafeFormulaEvaluator()
        line_values = {1: Decimal('100'), 2: Decimal('50'), 10: Decimal('25')}
        result = evaluator.evaluate("L1 + L2 - L10", line_values)
        # result = Decimal('125')
    """
    
    # Pattern to match L-tokens with word boundaries (L1 won't match L10)
    TOKEN_PATTERN = re.compile(r'\bL(\d+)\b')
    
    # Allowed characters in formula (after L-token substitution)
    ALLOWED_CHARS = re.compile(r'^[0-9\+\-\*/\(\)\.\s]+$')
    
    # Token types for the parser
    TOKEN_NUMBER = 'NUMBER'
    TOKEN_PLUS = 'PLUS'
    TOKEN_MINUS = 'MINUS'
    TOKEN_MUL = 'MUL'
    TOKEN_DIV = 'DIV'
    TOKEN_LPAREN = 'LPAREN'
    TOKEN_RPAREN = 'RPAREN'
    TOKEN_EOF = 'EOF'
    
    def evaluate(self, formula: str, line_values: Dict[int, Decimal]) -> Decimal:
        """
        Evaluate a formula with L-token references.
        
        Parameters
        ----------
        formula : str
            Formula string with L-tokens (e.g., "L1 + L2 - L3")
        line_values : Dict[int, Decimal]
            Dictionary mapping line numbers to their calculated values
            
        Returns
        -------
        Decimal
            Result of the formula evaluation
            
        Raises
        ------
        InvalidFormulaError
            If the formula contains invalid characters or syntax
        UndefinedLineError
            If a referenced line has not been calculated yet
        """
        if not formula or not formula.strip():
            return Decimal('0.00')
        
        log.debug("Evaluating formula: %s", formula)
        log.debug("Available line values: %s", line_values)
        
        # Step 1: Substitute L-tokens with their values
        expression = self._substitute_tokens(formula, line_values)
        log.debug("After token substitution: %s", expression)
        
        # Step 2: Validate allowed characters
        if not self.ALLOWED_CHARS.match(expression):
            invalid_chars = set(c for c in expression if not re.match(r'[0-9\+\-\*/\(\)\.\s]', c))
            raise InvalidFormulaError(
                f"Formula contains invalid characters: {invalid_chars}. "
                f"Only numbers, +, -, *, /, (, ) are allowed."
            )
        
        # Step 3: Parse and evaluate safely
        try:
            result = self._parse_and_evaluate(expression)
            log.debug("Formula result: %s", result)
            return result
        except Exception as e:
            log.error("Formula evaluation failed: %s - %s", formula, e)
            raise InvalidFormulaError(f"Failed to evaluate formula: {e}") from e
    
    def _substitute_tokens(self, formula: str, line_values: Dict[int, Decimal]) -> str:
        """
        Substitute L-tokens with their numeric values.
        
        Uses word boundaries to ensure L1 doesn't match L10, L11, etc.
        """
        def replace_token(match):
            line_num = int(match.group(1))
            if line_num not in line_values:
                raise UndefinedLineError(
                    f"Line L{line_num} has not been calculated yet. "
                    f"Formula lines can only reference lines with lower line numbers. "
                    f"Available lines: {sorted(line_values.keys())}"
                )
            value = line_values[line_num]
            # Handle negative values by wrapping in parentheses
            if value < 0:
                return f"({value})"
            return str(value)
        
        return self.TOKEN_PATTERN.sub(replace_token, formula)
    
    def _parse_and_evaluate(self, expression: str) -> Decimal:
        """
        Parse and evaluate an arithmetic expression safely.
        
        Uses a recursive descent parser (no eval).
        
        Grammar:
            expr   -> term (('+' | '-') term)*
            term   -> factor (('*' | '/') factor)*
            factor -> '-' factor | '(' expr ')' | number
        """
        tokens = self._tokenize(expression)
        self._pos = 0
        self._tokens = tokens
        
        result = self._parse_expr()
        
        # Ensure we consumed all tokens
        if self._current_token()[0] != self.TOKEN_EOF:
            raise InvalidFormulaError(
                f"Unexpected token at end of expression: {self._current_token()}"
            )
        
        return result
    
    def _tokenize(self, expression: str) -> List[Tuple[str, Optional[Decimal]]]:
        """
        Tokenize the expression into a list of (token_type, value) tuples.
        """
        tokens = []
        i = 0
        expression = expression.strip()
        
        while i < len(expression):
            char = expression[i]
            
            if char.isspace():
                i += 1
                continue
            
            if char == '+':
                tokens.append((self.TOKEN_PLUS, None))
                i += 1
            elif char == '-':
                tokens.append((self.TOKEN_MINUS, None))
                i += 1
            elif char == '*':
                tokens.append((self.TOKEN_MUL, None))
                i += 1
            elif char == '/':
                tokens.append((self.TOKEN_DIV, None))
                i += 1
            elif char == '(':
                tokens.append((self.TOKEN_LPAREN, None))
                i += 1
            elif char == ')':
                tokens.append((self.TOKEN_RPAREN, None))
                i += 1
            elif char.isdigit() or char == '.':
                # Parse number
                j = i
                has_dot = False
                while j < len(expression) and (expression[j].isdigit() or expression[j] == '.'):
                    if expression[j] == '.':
                        if has_dot:
                            raise InvalidFormulaError(f"Invalid number at position {i}: multiple decimal points")
                        has_dot = True
                    j += 1
                
                num_str = expression[i:j]
                try:
                    value = Decimal(num_str)
                except InvalidOperation:
                    raise InvalidFormulaError(f"Invalid number: {num_str}")
                
                tokens.append((self.TOKEN_NUMBER, value))
                i = j
            else:
                raise InvalidFormulaError(f"Unexpected character at position {i}: '{char}'")
        
        tokens.append((self.TOKEN_EOF, None))
        return tokens
    
    def _current_token(self) -> Tuple[str, Optional[Decimal]]:
        """Get the current token."""
        if self._pos >= len(self._tokens):
            return (self.TOKEN_EOF, None)
        return self._tokens[self._pos]
    
    def _advance(self):
        """Move to the next token."""
        self._pos += 1
    
    def _parse_expr(self) -> Decimal:
        """
        Parse expression: term (('+' | '-') term)*
        """
        result = self._parse_term()
        
        while self._current_token()[0] in (self.TOKEN_PLUS, self.TOKEN_MINUS):
            op = self._current_token()[0]
            self._advance()
            right = self._parse_term()
            
            if op == self.TOKEN_PLUS:
                result = result + right
            else:
                result = result - right
        
        return result
    
    def _parse_term(self) -> Decimal:
        """
        Parse term: factor (('*' | '/') factor)*
        """
        result = self._parse_factor()
        
        while self._current_token()[0] in (self.TOKEN_MUL, self.TOKEN_DIV):
            op = self._current_token()[0]
            self._advance()
            right = self._parse_factor()
            
            if op == self.TOKEN_MUL:
                result = result * right
            else:
                if right == 0:
                    log.warning("Division by zero in formula, returning 0")
                    return Decimal('0.00')
                result = result / right
        
        return result
    
    def _parse_factor(self) -> Decimal:
        """
        Parse factor: '-' factor | '(' expr ')' | number
        """
        token_type, value = self._current_token()
        
        # Unary minus
        if token_type == self.TOKEN_MINUS:
            self._advance()
            return -self._parse_factor()
        
        # Unary plus (just consume it)
        if token_type == self.TOKEN_PLUS:
            self._advance()
            return self._parse_factor()
        
        # Parenthesized expression
        if token_type == self.TOKEN_LPAREN:
            self._advance()
            result = self._parse_expr()
            
            if self._current_token()[0] != self.TOKEN_RPAREN:
                raise InvalidFormulaError("Mismatched parentheses: expected ')'")
            self._advance()
            return result
        
        # Number
        if token_type == self.TOKEN_NUMBER:
            self._advance()
            return value
        
        raise InvalidFormulaError(f"Unexpected token: {token_type}")
    
    def validate(self, formula: str, available_lines: Optional[List[int]] = None) -> List[str]:
        """
        Validate a formula without evaluating it.
        
        Parameters
        ----------
        formula : str
            Formula string to validate
        available_lines : Optional[List[int]]
            List of line numbers that are expected to be available.
            If None, skips line availability check.
            
        Returns
        -------
        List[str]
            List of validation error messages. Empty list means valid.
        """
        errors = []
        
        if not formula or not formula.strip():
            return errors  # Empty formula is valid (returns 0)
        
        # Check for invalid characters (before L-token substitution)
        # Allow L, digits, operators, parentheses, spaces, dots
        if not re.match(r'^[L0-9\+\-\*/\(\)\.\s]+$', formula):
            invalid = set(c for c in formula if not re.match(r'[L0-9\+\-\*/\(\)\.\s]', c))
            errors.append(f"Invalid characters in formula: {invalid}")
        
        # Extract all L-tokens
        tokens = self.TOKEN_PATTERN.findall(formula)
        referenced_lines = [int(t) for t in tokens]
        
        # Check for line availability
        if available_lines is not None:
            for line_num in referenced_lines:
                if line_num not in available_lines:
                    errors.append(
                        f"Formula references L{line_num} which is not available. "
                        f"Lines must reference only lower-numbered lines."
                    )
        
        # Check for balanced parentheses
        paren_count = 0
        for char in formula:
            if char == '(':
                paren_count += 1
            elif char == ')':
                paren_count -= 1
            if paren_count < 0:
                errors.append("Unbalanced parentheses: too many closing parentheses")
                break
        if paren_count > 0:
            errors.append("Unbalanced parentheses: too many opening parentheses")
        
        return errors


# Singleton instance for convenience
_evaluator = SafeFormulaEvaluator()


def evaluate_formula(formula: str, line_values: Dict[int, Decimal]) -> Decimal:
    """
    Convenience function to evaluate a formula.
    
    See SafeFormulaEvaluator.evaluate for details.
    """
    return _evaluator.evaluate(formula, line_values)


def validate_formula(formula: str, available_lines: Optional[List[int]] = None) -> List[str]:
    """
    Convenience function to validate a formula.
    
    See SafeFormulaEvaluator.validate for details.
    """
    return _evaluator.validate(formula, available_lines)

