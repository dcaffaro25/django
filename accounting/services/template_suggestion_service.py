"""
Template Suggestion Service

Uses an external AI to propose or improve financial statement templates
(Income Statement, Balance Sheet, Cash Flow) for a given company,
based on its chart of accounts and existing templates.

This service:
1. Reads the company's hierarchical chart of accounts
2. Reads existing financial statement templates and lines
3. Builds a structured prompt for the AI
4. Calls the external AI API
5. Validates and applies the AI's suggestions to the database
"""

import logging
import json
import os
import time
from typing import Any, Dict, List, Optional, Tuple, Set
from decimal import Decimal

from django.conf import settings
from django.db import transaction
from django.db.models import Q

from multitenancy.models import Company
from accounting.models import Account
from accounting.models_financial_statements import (
    FinancialStatementTemplate,
    FinancialStatementLineTemplate,
)
from .external_ai_client import ExternalAIClient, ExternalAIError

log = logging.getLogger(__name__)


# =============================================================================
# JSON Schema that the AI must return
# =============================================================================

AI_RESPONSE_JSON_SCHEMA = """
{
  "templates": [
    {
      "statement_type": "income_statement | balance_sheet | cash_flow",
      "template_code": "string_unique_code",
      "template_name": "Human readable name",
      "description": "Optional description",
      "is_default": true,
      "lines": [
        {
          "line_code": "string_unique_within_template",
          "label": "Line label",
          "line_type": "header | account | subtotal | total | spacer",
          "parent_line_code": null,
          "order": 10,
          "linked_accounts": [
            {
              "account_identifier": "ACCOUNT_CODE (use when account_code exists)",
              "account_path": "Assets > Current Assets (use when account_code is missing)",
              "aggregation_type": "sum | subtract"
            }
          ],
          "account_code_prefix": "optional_prefix_filter",
          "account_path_contains": "optional_path_filter (e.g., 'Assets > Current Assets')",
          "calculation": {
            "formula_type": "none | sum_of_children | formula",
            "custom_formula": "optional, using line_code references like L10 + L20"
          },
          "display_options": {
            "bold": true,
            "indent_level": 0
          }
        }
      ]
    }
  ]
}
"""


# =============================================================================
# TemplateSuggestionService
# =============================================================================

class TemplateSuggestionService:
    """
    Service to generate AI-powered financial statement template suggestions.
    
    Usage:
        service = TemplateSuggestionService(
            company_id=1,
            user_preferences="I want revenue broken down to 3 levels"
        )
        result = service.generate_suggestions(apply_changes=True)
    """
    
    # Map AI statement_type to our report_type
    STATEMENT_TYPE_MAP = {
        "income_statement": "income_statement",
        "balance_sheet": "balance_sheet", 
        "cash_flow": "cash_flow",
    }
    
    # Valid line types from our model
    VALID_LINE_TYPES = {"header", "account", "subtotal", "total", "spacer"}
    
    def __init__(
        self,
        company_id: int,
        user_preferences: str = "",
        ai_provider: Optional[str] = None,
        ai_model: Optional[str] = None,
    ):
        """
        Initialize the template suggestion service.
        
        Parameters
        ----------
        company_id : int
            The company ID to generate templates for.
        user_preferences : str
            Free-text user preferences for template customization.
        ai_provider : str
            AI provider to use ("openai" or "anthropic").
            Defaults to settings.TEMPLATE_AI_PROVIDER or "openai".
        ai_model : Optional[str]
            Specific model to use. Defaults to settings.TEMPLATE_AI_MODEL or provider default.
        """
        self.company_id = company_id
        self.user_preferences = user_preferences or ""
        
        # Resolve provider from settings/env if not provided
        if ai_provider:
            self.ai_provider = ai_provider
        else:
            self.ai_provider = (
                getattr(settings, 'TEMPLATE_AI_PROVIDER', None) or
                os.getenv('TEMPLATE_AI_PROVIDER') or
                'openai'
            )
        
        # Resolve model from settings/env if not provided
        if ai_model:
            self.ai_model = ai_model
        else:
            self.ai_model = (
                getattr(settings, 'TEMPLATE_AI_MODEL', None) or
                os.getenv('TEMPLATE_AI_MODEL') or
                None  # Let the AI client use its default
            )
        
        # Load company
        try:
            self.company = Company.objects.get(id=company_id)
        except Company.DoesNotExist:
            raise ValueError(f"Company with id={company_id} not found")
        
        # Initialize AI client
        self.ai_client = ExternalAIClient(
            provider=ai_provider,
            model=ai_model,
        )
        
        log.info(
            "TemplateSuggestionService initialized for company_id=%d (%s)",
            company_id, self.company.name
        )
    
    # -------------------------------------------------------------------------
    # Main entry point
    # -------------------------------------------------------------------------
    
    def generate_suggestions(
        self,
        apply_changes: bool = True,
    ) -> Dict[str, Any]:
        """
        Generate AI-powered template suggestions and optionally apply them.
        
        Parameters
        ----------
        apply_changes : bool
            If True, apply the suggestions to the database.
            If False, just return what would be created/updated.
        
        Returns
        -------
        Dict[str, Any]
            Result containing:
            - status: "success" or "error"
            - applied_changes: bool
            - templates_created: int
            - templates_updated: int
            - lines_created: int
            - lines_updated: int
            - ai_raw_response: dict
            - validation_errors: list (if any)
            - debug_info: dict with steps, prompt, system_prompt, etc.
        """
        debug_info = {
            "steps": [],
            "prompt": None,
            "system_prompt": None,
            "company_context": None,
            "accounts_context": None,
            "accounts_metadata": None,
            "existing_templates_context": None,
            "ai_request_details": None,
            "ordering_strategy": None,
        }
        
        log.info("=" * 80)
        log.info("[generate_suggestions] STARTING TEMPLATE SUGGESTION GENERATION")
        log.info("=" * 80)
        log.info("[generate_suggestions] Parameters: apply_changes=%s", apply_changes)
        log.info("[generate_suggestions] AI Provider: %s, Model: %s", self.ai_provider, self.ai_model)
        log.info("[generate_suggestions] Company: %s (ID: %d)", self.company.name, self.company_id)
        if self.user_preferences:
            log.info("[generate_suggestions] User preferences: %s", self.user_preferences[:200])
        
        try:
            # Step 1: Gather company context
            log.info("-" * 60)
            log.info("[Step 1] Gathering company context...")
            debug_info["steps"].append({
                "step": 1,
                "name": "Gather Company Context",
                "status": "in_progress",
            })
            company_context = self._build_company_context()
            debug_info["company_context"] = company_context
            debug_info["steps"][-1]["status"] = "completed"
            log.info("[Step 1] ✓ Company context gathered (%d chars)", len(company_context))
            
            # Step 2: Gather accounts context (with metadata)
            log.info("-" * 60)
            log.info("[Step 2] Analyzing chart of accounts...")
            debug_info["steps"].append({
                "step": 2,
                "name": "Gather Accounts Context",
                "status": "in_progress",
            })
            accounts_context, accounts_metadata = self._build_accounts_context_with_metadata()
            debug_info["accounts_context"] = accounts_context
            debug_info["accounts_metadata"] = accounts_metadata
            debug_info["ordering_strategy"] = accounts_metadata.get("ordering_strategy", "unknown")
            debug_info["steps"][-1]["status"] = "completed"
            debug_info["steps"][-1]["details"] = {
                "total_accounts": accounts_metadata["total_accounts"],
                "with_codes": accounts_metadata["accounts_with_codes"],
                "without_codes": accounts_metadata["accounts_without_codes"],
                "use_path_based": accounts_metadata["use_path_based"],
            }
            
            use_path_based = accounts_metadata["use_path_based"]
            
            log.info("[Step 2] ✓ Accounts context gathered")
            log.info("[Step 2] → Ordering Strategy Decision: %s", 
                     "PATH-BASED (no codes)" if use_path_based else "CODE-BASED")
            log.info("[Step 2] → This means: %s",
                     "AI will analyze account names/paths to determine order" if use_path_based 
                     else "AI will use account codes for ordering")
            
            # Step 3: Gather existing templates context
            log.info("-" * 60)
            log.info("[Step 3] Gathering existing templates context...")
            debug_info["steps"].append({
                "step": 3,
                "name": "Gather Existing Templates Context",
                "status": "in_progress",
            })
            existing_templates_context = self._build_existing_templates_context()
            debug_info["existing_templates_context"] = existing_templates_context
            debug_info["steps"][-1]["status"] = "completed"
            log.info("[Step 3] ✓ Existing templates context gathered (%d chars)", len(existing_templates_context))
            
            # Step 4: Build the AI prompt (with path-based flag)
            log.info("-" * 60)
            log.info("[Step 4] Building AI prompt (use_path_based=%s)...", use_path_based)
            debug_info["steps"].append({
                "step": 4,
                "name": "Build AI Prompt",
                "status": "in_progress",
                "use_path_based": use_path_based,
            })
            prompt = self.build_ai_prompt(use_path_based=use_path_based)
            system_prompt = self._get_system_prompt(use_path_based=use_path_based)
            debug_info["prompt"] = prompt
            debug_info["system_prompt"] = system_prompt
            debug_info["steps"][-1]["status"] = "completed"
            debug_info["steps"][-1]["prompt_length"] = len(prompt)
            debug_info["steps"][-1]["system_prompt_length"] = len(system_prompt)
            
            log.info("[Step 4] ✓ AI prompt built")
            log.info("[Step 4] → Prompt length: %d chars", len(prompt))
            log.info("[Step 4] → System prompt length: %d chars", len(system_prompt))
            log.info("[Step 4] → Prompt includes path-based instructions: %s", use_path_based)
            log.debug("[Step 4] System prompt preview: %s", system_prompt[:300] + "..." if len(system_prompt) > 300 else system_prompt)
            log.debug("[Step 4] User prompt preview: %s", prompt[:500] + "..." if len(prompt) > 500 else prompt)
            
            # Step 5: Call external AI
            log.info("-" * 60)
            log.info("[Step 5] Calling external AI...")
            log.info("[Step 5] → Provider: %s", self.ai_provider)
            log.info("[Step 5] → Model: %s", self.ai_model)
            log.info("[Step 5] → Prompt tokens (estimated): ~%d", len(prompt) // 4)
            debug_info["steps"].append({
                "step": 5,
                "name": "Call External AI",
                "status": "in_progress",
            })
            debug_info["ai_request_details"] = {
                "provider": self.ai_provider,
                "model": self.ai_model,
                "prompt_length": len(prompt),
                "system_prompt_length": len(system_prompt),
                "estimated_tokens": len(prompt) // 4,
                "use_path_based": use_path_based,
            }
            
            import time
            ai_start_time = time.time()
            ai_response = self.ai_client.generate_json(
                prompt=prompt,
                system_prompt=system_prompt,
            )
            ai_elapsed = time.time() - ai_start_time
            
            debug_info["steps"][-1]["status"] = "completed"
            debug_info["steps"][-1]["elapsed_seconds"] = ai_elapsed
            debug_info["ai_request_details"]["elapsed_seconds"] = ai_elapsed
            
            log.info("[Step 5] ✓ AI response received in %.2f seconds", ai_elapsed)
            
            # Log AI response summary
            if isinstance(ai_response, dict):
                templates_count = len(ai_response.get("templates", []))
                log.info("[Step 5] → Response contains %d template(s)", templates_count)
                for idx, tpl in enumerate(ai_response.get("templates", [])):
                    tpl_type = tpl.get("statement_type", "unknown")
                    tpl_name = tpl.get("template_name", "unnamed")
                    lines_count = len(tpl.get("lines", []))
                    log.info("[Step 5]   Template %d: %s (%s) with %d lines", 
                             idx + 1, tpl_name, tpl_type, lines_count)
            else:
                log.warning("[Step 5] → Unexpected response type: %s", type(ai_response))
            
            # Step 6: Validate and apply
            log.info("-" * 60)
            log.info("[Step 6] Validating and applying AI suggestions...")
            log.info("[Step 6] → Apply changes: %s", apply_changes)
            log.info("[Step 6] → Ordering strategy used: %s", 
                     "PATH-BASED" if use_path_based else "CODE-BASED")
            debug_info["steps"].append({
                "step": 6,
                "name": "Validate and Apply Suggestions",
                "status": "in_progress",
                "apply_changes": apply_changes,
            })
            result = self.apply_ai_suggestion(
                ai_response=ai_response,
                apply_changes=apply_changes,
            )
            debug_info["steps"][-1]["status"] = "completed"
            debug_info["steps"][-1]["result_summary"] = {
                "status": result.get("status"),
                "templates_created": result.get("templates_created", 0),
                "templates_updated": result.get("templates_updated", 0),
                "lines_created": result.get("lines_created", 0),
                "lines_updated": result.get("lines_updated", 0),
                "validation_warnings_count": len(result.get("validation_warnings", [])),
            }
            
            log.info("[Step 6] ✓ Suggestions processed")
            log.info("[Step 6] → Status: %s", result.get("status"))
            log.info("[Step 6] → Templates created: %d", result.get("templates_created", 0))
            log.info("[Step 6] → Templates updated: %d", result.get("templates_updated", 0))
            log.info("[Step 6] → Lines created: %d", result.get("lines_created", 0))
            log.info("[Step 6] → Lines updated: %d", result.get("lines_updated", 0))
            if result.get("validation_warnings"):
                log.warning("[Step 6] → Validation warnings (%d):", len(result["validation_warnings"]))
                for warn in result["validation_warnings"][:10]:  # Show first 10
                    log.warning("[Step 6]   - %s", warn)
            
            # Add debug info to result
            result["debug_info"] = debug_info
            
            log.info("=" * 80)
            log.info("[generate_suggestions] TEMPLATE SUGGESTION GENERATION COMPLETE")
            log.info("=" * 80)
            log.info("[generate_suggestions] Final Status: %s", result.get("status"))
            log.info("[generate_suggestions] Changes Applied: %s", result.get("applied_changes"))
            log.info("[generate_suggestions] Ordering Strategy: %s", debug_info.get("ordering_strategy"))
            
            return result
        
        except ExternalAIError as e:
            log.error("=" * 80)
            log.error("[generate_suggestions] EXTERNAL AI ERROR")
            log.error("=" * 80)
            log.exception("External AI error: %s", e)
            if debug_info["steps"]:
                debug_info["steps"][-1]["status"] = "error"
                debug_info["steps"][-1]["error"] = str(e)
            return {
                "status": "error",
                "error": str(e),
                "error_type": "ai_error",
                "applied_changes": False,
                "debug_info": debug_info,
            }
        except Exception as e:
            log.error("=" * 80)
            log.error("[generate_suggestions] UNEXPECTED ERROR")
            log.error("=" * 80)
            log.exception("Unexpected error in generate_suggestions: %s", e)
            if debug_info["steps"]:
                debug_info["steps"][-1]["status"] = "error"
                debug_info["steps"][-1]["error"] = str(e)
            return {
                "status": "error",
                "error": str(e),
                "error_type": "internal_error",
                "applied_changes": False,
                "debug_info": debug_info,
            }
    
    # -------------------------------------------------------------------------
    # Build AI Prompt
    # -------------------------------------------------------------------------
    
    def _get_system_prompt(self, use_path_based: bool = False) -> str:
        """Get the system prompt for the AI."""
        base_prompt = """You are a senior accountant and financial reporting expert with deep expertise in:
- IFRS (International Financial Reporting Standards)
- BR GAAP (Brazilian Generally Accepted Accounting Principles)
- Financial statement design and presentation
- Chart of accounts structuring

Your task is to design or improve financial statement templates that are:
- Compliant with accounting standards
- Well-structured and hierarchical
- Tailored to the company's actual chart of accounts
- Following best practices for presentation"""

        if use_path_based:
            base_prompt += """

IMPORTANT: This company's chart of accounts does NOT have standardized account codes.
You must determine the optimal order for financial statement lines by:
1. Analyzing the account NAMES and PATHS to understand their nature (Asset, Liability, Equity, Revenue, Expense)
2. Using standard financial statement presentation order:
   - Balance Sheet: Current Assets → Non-Current Assets → Current Liabilities → Non-Current Liabilities → Equity
   - Income Statement: Revenue → Cost of Sales → Gross Profit → Operating Expenses → Operating Income → Non-Operating → Net Income
   - Cash Flow: Operating → Investing → Financing
3. Inferring account classification from common accounting terms in the account names
4. Grouping related accounts logically based on their path hierarchy"""

        base_prompt += """

You must respond ONLY with valid JSON matching the specified schema. No additional text, explanations, or markdown."""
        
        return base_prompt

    def build_ai_prompt(self, use_path_based: bool = False) -> str:
        """
        Build the complete prompt to send to the external AI.
        
        Parameters
        ----------
        use_path_based : bool
            Whether to use path-based matching (when account codes are missing)
        
        Returns
        -------
        str
            The complete prompt string.
        """
        log.info("[build_ai_prompt] Starting prompt construction (use_path_based=%s)", use_path_based)
        
        # Gather all context
        company_context = self._build_company_context()
        accounts_context, accounts_metadata = self._build_accounts_context_with_metadata()
        existing_templates_context = self._build_existing_templates_context()
        
        log.info("[build_ai_prompt] Context gathered: company=%d chars, accounts=%d chars, templates=%d chars",
                 len(company_context), len(accounts_context), len(existing_templates_context))
        
        # Build ordering instructions based on whether codes are available
        if use_path_based:
            ordering_instructions = """
## CRITICAL: Account Ordering Strategy (NO ACCOUNT CODES AVAILABLE)

**This company's chart of accounts does NOT have standardized account codes.**
You must determine the optimal order for each account by analyzing:

1. **Account Name Analysis**: Look for keywords that indicate account type:
   - Assets: "Cash", "Bank", "Receivable", "Inventory", "Equipment", "Property", "Investment"
   - Liabilities: "Payable", "Loan", "Debt", "Accrued", "Deferred Revenue"
   - Equity: "Capital", "Retained Earnings", "Reserves", "Stock"
   - Revenue: "Sales", "Revenue", "Income", "Service"
   - Expenses: "Cost", "Expense", "Salary", "Rent", "Depreciation", "Interest"

2. **Path Hierarchy Analysis**: Use the account path to understand grouping:
   - Accounts under the same parent should be grouped together
   - Deeper levels indicate more specific accounts

3. **Standard Financial Statement Order**:
   
   **Balance Sheet** (order field should reflect this sequence):
   - 10-99: Current Assets (Cash first, then Receivables, Inventory, etc.)
   - 100-199: Non-Current Assets (Property, Equipment, Intangibles)
   - 200-299: Current Liabilities (Payables, Short-term debt)
   - 300-399: Non-Current Liabilities (Long-term debt, Deferred taxes)
   - 400-499: Equity (Capital, Reserves, Retained Earnings)
   
   **Income Statement** (order field should reflect this sequence):
   - 10-49: Revenue/Sales
   - 50-99: Cost of Goods Sold / Cost of Sales
   - 100: Gross Profit (subtotal)
   - 110-199: Operating Expenses
   - 200: Operating Income (subtotal)
   - 210-249: Non-Operating Income/Expenses
   - 250: Income Before Tax (subtotal)
   - 260-279: Income Tax
   - 280: Net Income (total)
   
   **Cash Flow Statement**:
   - 10-99: Operating Activities
   - 100-199: Investing Activities  
   - 200-299: Financing Activities
   - 300+: Net Change and Ending Balance

4. **Use `account_path_contains` for matching**: Since codes are not available, use the path to match accounts:
   - Example: `"account_path_contains": "Assets > Current Assets"` to match all current assets
   - Example: `"account_path_contains": "Cash"` to match cash accounts

5. **Leave `account_identifier` empty** when codes don't exist - use path matching instead."""
        else:
            ordering_instructions = """
## Account Ordering Strategy (ACCOUNT CODES AVAILABLE)

Use the account codes to determine proper ordering:
- Account codes typically follow a standard structure (e.g., 1xxx for Assets, 2xxx for Liabilities)
- Use `account_code_prefix` to group accounts by their code prefix
- Use `account_identifier` with exact account codes for specific account links"""

        prompt = f"""
# Task: Design Financial Statement Templates

{company_context}

{accounts_context}

{existing_templates_context}

## User Preferences

{self.user_preferences if self.user_preferences else "No specific preferences provided. Use best practices."}

{ordering_instructions}

## Accounting Standards and Best Practices

Please design templates following these guidelines:

### Income Statement (income_statement)
- Use multi-step format: Revenue → COGS → Gross Profit → Operating Expenses → EBIT → Financial Result → Profit Before Tax → Income Tax → Net Income
- Group operating expenses logically (Personnel, Administrative, Depreciation, etc.)
- Show meaningful subtotals (Gross Profit, Operating Income, EBIT, EBITDA if relevant)

### Balance Sheet (balance_sheet)
- Classify assets: Current Assets vs Non-Current Assets
- Classify liabilities: Current Liabilities vs Non-Current Liabilities  
- Show Equity section with Retained Earnings, Capital, Reserves
- Ensure Assets = Liabilities + Equity (conceptually)

### Cash Flow Statement (cash_flow)
- Use indirect method as baseline
- Separate into: Operating Activities, Investing Activities, Financing Activities
- Start Operating section with Net Income, then adjustments
- Show Net Change in Cash and Ending Cash Balance

## Output Format

You MUST respond with ONLY valid JSON matching this exact schema:

{AI_RESPONSE_JSON_SCHEMA}

### Important Rules:
1. **Account Identification**:
   - If accounts have `account_code`, use the exact `account_code` value as `account_identifier`
   - If accounts do NOT have `account_code` (marked as "N/A (use path)"), use `account_path_contains` instead
   - Do NOT invent account codes that don't exist in the CoA

2. **Line Structure**:
   - `line_code` must be unique within each template (e.g., "IS_REV_100", "BS_ASSET_CA_100")
   - `parent_line_code` references another line's `line_code` for hierarchy (null for top-level)
   - For subtotals/totals, use `calculation.formula_type` = "sum_of_children" or "formula"
   - When using "formula", reference other lines using L + order number (e.g., "L10 + L20 - L30")

3. **Template Settings**:
   - Set `is_default` to true for only ONE template per statement_type

Respond ONLY with the JSON. No explanations, no markdown code blocks, just pure JSON.
"""
        
        log.info("[build_ai_prompt] ✓ Prompt built successfully (length=%d chars, use_path_based=%s)", 
                 len(prompt), use_path_based)
        log.debug("[build_ai_prompt] Ordering strategy: %s", "PATH-BASED" if use_path_based else "CODE-BASED")
        
        return prompt
    
    def _build_company_context(self) -> str:
        """Build company context section of the prompt."""
        return f"""## Company Information

- **Company ID**: {self.company.id}
- **Company Name**: {self.company.name}
- **Subdomain**: {self.company.subdomain}
"""

    def _build_accounts_context(self) -> str:
        """Build chart of accounts context section of the prompt."""
        context, _ = self._build_accounts_context_with_metadata()
        return context
    
    def _build_accounts_context_with_metadata(self) -> Tuple[str, Dict[str, Any]]:
        """
        Build chart of accounts context section of the prompt with metadata.
        
        Returns
        -------
        Tuple[str, Dict[str, Any]]
            (context_string, metadata_dict)
        """
        log.info("[_build_accounts_context] Starting accounts context analysis...")
        
        accounts = Account.objects.filter(
            company_id=self.company_id,
            is_active=True,
        )
        
        total_accounts = accounts.count()
        log.info("[_build_accounts_context] Found %d total active accounts for company_id=%d", 
                 total_accounts, self.company_id)
        
        # Check if account codes are present and valid
        accounts_with_codes = accounts.exclude(account_code__isnull=True).exclude(account_code='')
        accounts_without_codes = accounts.filter(Q(account_code__isnull=True) | Q(account_code=''))
        
        with_codes_count = accounts_with_codes.count()
        without_codes_count = accounts_without_codes.count()
        
        has_valid_codes = accounts_with_codes.exists() and with_codes_count > without_codes_count
        use_path_based = not has_valid_codes
        
        # Build metadata
        metadata = {
            "total_accounts": total_accounts,
            "accounts_with_codes": with_codes_count,
            "accounts_without_codes": without_codes_count,
            "has_valid_codes": has_valid_codes,
            "use_path_based": use_path_based,
            "ordering_strategy": "account_code" if has_valid_codes else "path_hierarchy",
        }
        
        log.info("[_build_accounts_context] Account code analysis:")
        log.info("  → Total accounts: %d", total_accounts)
        log.info("  → Accounts WITH codes: %d (%.1f%%)", with_codes_count, 
                 (with_codes_count / total_accounts * 100) if total_accounts > 0 else 0)
        log.info("  → Accounts WITHOUT codes: %d (%.1f%%)", without_codes_count,
                 (without_codes_count / total_accounts * 100) if total_accounts > 0 else 0)
        log.info("  → Decision: use_path_based=%s (has_valid_codes=%s)", use_path_based, has_valid_codes)
        log.info("  → Ordering strategy: %s", metadata["ordering_strategy"])
        
        # Order accounts appropriately
        if has_valid_codes:
            accounts = accounts.order_by('account_code', 'lft')
            log.info("[_build_accounts_context] Ordering by account_code, then lft (tree position)")
        else:
            accounts = accounts.order_by('lft')
            log.info("[_build_accounts_context] Ordering by lft (tree hierarchy) - NO account codes")
        
        if not accounts.exists():
            log.warning("[_build_accounts_context] No accounts found!")
            return """## Chart of Accounts

No accounts found for this company. Please create basic templates with placeholder structure.""", metadata
        
        lines = ["## Chart of Accounts", ""]
        
        if has_valid_codes:
            lines.append("The company has the following accounts. Use `account_code` as the unique identifier when linking lines to accounts.")
            lines.append("Accounts are ordered by `account_code`.")
        else:
            lines.append("⚠️ **IMPORTANT: This company's accounts do NOT have standardized account codes.**")
            lines.append("")
            lines.append("You must:")
            lines.append("1. Analyze account NAMES to determine their type (Asset, Liability, Revenue, Expense)")
            lines.append("2. Use `account_path_contains` to match accounts (NOT `account_identifier`)")
            lines.append("3. Determine the optimal ORDER based on standard financial statement presentation")
            lines.append("4. Group related accounts based on their path hierarchy")
            lines.append("")
            lines.append("Accounts are listed in hierarchical order (parent → child relationships).")
        
        lines.append("")
        lines.append("Format: `account_code` | `name` | `path` | `is_leaf` | `hierarchy_level`")
        lines.append("---")
        
        # Limit to reasonable number of accounts to avoid token limits
        max_accounts = 500
        account_count = 0
        
        # Collect path hierarchy info for logging
        path_hierarchy = {}
        
        for account in accounts[:max_accounts]:
            is_leaf = "✓" if account.is_leaf() else ""
            path = account.get_path()
            hierarchy_level = account.level if hasattr(account, 'level') else len(path.split(' > ')) - 1
            account_code_display = account.account_code if account.account_code else "N/A (use path)"
            lines.append(f"- `{account_code_display}` | {account.name} | {path} | {is_leaf} | level:{hierarchy_level}")
            account_count += 1
            
            # Track path hierarchy for analysis
            top_level = path.split(' > ')[0] if ' > ' in path else path
            if top_level not in path_hierarchy:
                path_hierarchy[top_level] = {"count": 0, "examples": []}
            path_hierarchy[top_level]["count"] += 1
            if len(path_hierarchy[top_level]["examples"]) < 5:
                path_hierarchy[top_level]["examples"].append(account.name)
        
        # Log hierarchy analysis
        log.info("[_build_accounts_context] Path hierarchy analysis:")
        for top_level, info in sorted(path_hierarchy.items()):
            log.info("  → '%s': %d accounts (examples: %s)", 
                     top_level, info["count"], ", ".join(info["examples"][:3]))
        
        metadata["path_hierarchy"] = path_hierarchy
        
        if accounts.count() > max_accounts:
            lines.append(f"")
            lines.append(f"... and {accounts.count() - max_accounts} more accounts (truncated)")
            log.info("[_build_accounts_context] Truncated output: showing %d of %d accounts", 
                     max_accounts, accounts.count())
        
        lines.append("")
        lines.append(f"**Total accounts**: {accounts.count()}")
        lines.append(f"**Accounts with codes**: {with_codes_count}")
        lines.append(f"**Accounts without codes**: {without_codes_count}")
        
        # Add summary by first digit of account_code for context (only if codes exist)
        if has_valid_codes:
            lines.append("")
            lines.append("**Account Structure Summary** (by first digit of account_code):")
            
            code_prefixes = {}
            for account in accounts_with_codes:
                if account.account_code:
                    prefix = account.account_code[0] if account.account_code else "?"
                    if prefix not in code_prefixes:
                        code_prefixes[prefix] = []
                    if len(code_prefixes[prefix]) < 3:  # Show first 3 examples
                        code_prefixes[prefix].append(account.name)
            
            for prefix in sorted(code_prefixes.keys()):
                examples = ", ".join(code_prefixes[prefix][:3])
                lines.append(f"- `{prefix}xxx`: {examples}...")
            
            log.info("[_build_accounts_context] Code prefix summary: %s", 
                     ", ".join(f"{k}xxx ({len(v)} examples)" for k, v in code_prefixes.items()))
        else:
            # Add summary by path hierarchy when codes aren't available
            lines.append("")
            lines.append("**Account Structure Summary** (by top-level path - USE THIS FOR ORDERING):")
            lines.append("")
            lines.append("Analyze these top-level categories to determine proper financial statement order:")
            
            for top_level in sorted(path_hierarchy.keys()):
                info = path_hierarchy[top_level]
                examples = ", ".join(info["examples"][:3])
                lines.append(f"- **{top_level}** ({info['count']} accounts): {examples}...")
        
        log.info("[_build_accounts_context] ✓ Context built: %d lines, %d characters", 
                 len(lines), sum(len(l) for l in lines))
        
        return "\n".join(lines), metadata
    
    def _build_existing_templates_context(self) -> str:
        """Build existing templates context section of the prompt."""
        templates = FinancialStatementTemplate.objects.filter(
            company_id=self.company_id,
            report_type__in=['income_statement', 'balance_sheet', 'cash_flow'],
        ).prefetch_related('line_templates')
        
        if not templates.exists():
            return """## Existing Templates

No existing templates found. Please create new templates from scratch following best practices."""
        
        lines = ["## Existing Templates", ""]
        lines.append("The company already has these templates. You may improve them or create new ones.")
        lines.append("")
        
        for template in templates:
            default_marker = " (DEFAULT)" if template.is_default else ""
            active_marker = " [INACTIVE]" if not template.is_active else ""
            
            lines.append(f"### {template.name}{default_marker}{active_marker}")
            lines.append(f"- **Type**: {template.report_type}")
            lines.append(f"- **ID**: {template.id}")
            lines.append("")
            
            # Show line templates
            line_templates = template.line_templates.all().order_by('line_number')
            if line_templates.exists():
                lines.append("**Lines**:")
                for lt in line_templates[:50]:  # Limit lines shown
                    indent = "  " * lt.indent_level
                    account_info = ""
                    if lt.account:
                        account_info = f" → account:{lt.account.account_code}"
                    elif lt.account_code_prefix:
                        account_info = f" → prefix:{lt.account_code_prefix}"
                    elif lt.account_ids:
                        account_info = f" → ids:{lt.account_ids[:3]}..."
                    
                    lines.append(f"  {lt.line_number}. {indent}{lt.label} ({lt.line_type}){account_info}")
                
                if line_templates.count() > 50:
                    lines.append(f"  ... and {line_templates.count() - 50} more lines")
            else:
                lines.append("  (No lines defined)")
            
            lines.append("")
        
        return "\n".join(lines)
    
    # -------------------------------------------------------------------------
    # Validate and Apply AI Suggestions
    # -------------------------------------------------------------------------
    
    def apply_ai_suggestion(
        self,
        ai_response: Dict[str, Any],
        apply_changes: bool = True,
    ) -> Dict[str, Any]:
        """
        Validate and apply AI suggestions to the database.
        
        Parameters
        ----------
        ai_response : Dict[str, Any]
            The parsed JSON response from the AI.
        apply_changes : bool
            If True, commit changes to database.
            If False, simulate and return what would be done.
        
        Returns
        -------
        Dict[str, Any]
            Result summary.
        """
        log.info("[apply_ai_suggestion] Starting validation and application...")
        log.info("[apply_ai_suggestion] Mode: %s", "APPLY" if apply_changes else "SIMULATE")
        
        # Validation results
        validation_errors: List[str] = []
        validation_warnings: List[str] = []
        
        # Counters
        templates_created = 0
        templates_updated = 0
        lines_created = 0
        lines_updated = 0
        
        # Validate structure
        log.info("[apply_ai_suggestion] Validating AI response structure...")
        if "templates" not in ai_response:
            log.error("[apply_ai_suggestion] ✗ Response missing 'templates' key")
            validation_errors.append("Response missing 'templates' key")
            return {
                "status": "error",
                "error": "Invalid AI response structure",
                "validation_errors": validation_errors,
                "applied_changes": False,
                "ai_raw_response": ai_response,
            }
        
        templates_data = ai_response.get("templates", [])
        if not isinstance(templates_data, list):
            log.error("[apply_ai_suggestion] ✗ 'templates' is not a list")
            validation_errors.append("'templates' must be a list")
            return {
                "status": "error",
                "error": "Invalid AI response structure",
                "validation_errors": validation_errors,
                "applied_changes": False,
                "ai_raw_response": ai_response,
            }
        
        log.info("[apply_ai_suggestion] ✓ Response structure valid: %d templates found", len(templates_data))
        
        # Load valid account codes for validation
        log.info("[apply_ai_suggestion] Loading account data for validation...")
        all_accounts = Account.objects.filter(
            company_id=self.company_id,
            is_active=True,
        )
        
        valid_account_codes = set(
            all_accounts.exclude(
                account_code__isnull=True
            ).exclude(account_code='').values_list('account_code', flat=True)
        )
        
        # Build account code to ID map
        account_code_to_id = dict(
            all_accounts.exclude(
                account_code__isnull=True
            ).exclude(account_code='').values_list('account_code', 'id')
        )
        
        # Build account path to ID map for path-based matching
        account_path_to_ids = {}
        for account in all_accounts:
            path = account.get_path()
            if path not in account_path_to_ids:
                account_path_to_ids[path] = []
            account_path_to_ids[path].append(account.id)
        
        # Check if we should use path-based matching
        accounts_with_codes = all_accounts.exclude(account_code__isnull=True).exclude(account_code='')
        accounts_without_codes = all_accounts.filter(Q(account_code__isnull=True) | Q(account_code=''))
        use_path_based = accounts_without_codes.count() > accounts_with_codes.count()
        
        log.info("[apply_ai_suggestion] Account analysis complete:")
        log.info("  → Valid account codes: %d", len(valid_account_codes))
        log.info("  → Accounts without codes: %d", accounts_without_codes.count())
        log.info("  → Account paths indexed: %d", len(account_path_to_ids))
        log.info("  → Use path-based matching: %s", use_path_based)
        log.info("  → Matching strategy: %s", "PATH-BASED" if use_path_based else "CODE-BASED")
        
        # Validate each template
        validated_templates = []
        
        log.info("[apply_ai_suggestion] Validating %d templates from AI response...", len(templates_data))
        for idx, tpl_data in enumerate(templates_data):
            tpl_name = tpl_data.get("template_name", f"Template {idx}")
            tpl_type = tpl_data.get("statement_type", "unknown")
            lines_count = len(tpl_data.get("lines", []))
            
            log.info("[apply_ai_suggestion] Validating template %d: '%s' (%s) with %d lines", 
                     idx + 1, tpl_name, tpl_type, lines_count)
            
            tpl_errors, tpl_warnings, validated_tpl = self._validate_template(
                tpl_data, idx, valid_account_codes, use_path_based, account_path_to_ids
            )
            validation_errors.extend(tpl_errors)
            validation_warnings.extend(tpl_warnings)
            
            if tpl_errors:
                log.warning("[apply_ai_suggestion]   ✗ Template '%s' has %d errors:", tpl_name, len(tpl_errors))
                for err in tpl_errors[:5]:
                    log.warning("[apply_ai_suggestion]     - %s", err)
            else:
                log.info("[apply_ai_suggestion]   ✓ Template '%s' validated successfully", tpl_name)
            
            if tpl_warnings:
                log.info("[apply_ai_suggestion]   ⚠ Template '%s' has %d warnings", tpl_name, len(tpl_warnings))
            
            if validated_tpl and not tpl_errors:
                # Add metadata about ordering strategy
                validated_tpl["_ordering_strategy"] = "account_code" if not use_path_based else "account_path"
                validated_templates.append(validated_tpl)
        
        log.info("[apply_ai_suggestion] Validation summary:")
        log.info("  → Templates validated: %d of %d", len(validated_templates), len(templates_data))
        log.info("  → Total errors: %d", len(validation_errors))
        log.info("  → Total warnings: %d", len(validation_warnings))
        
        # If there are critical errors, don't apply
        if validation_errors:
            log.warning("[apply_ai_suggestion] ✗ Validation errors found - not applying changes")
            for err in validation_errors[:10]:
                log.warning("[apply_ai_suggestion]   Error: %s", err)
            return {
                "status": "error" if not validated_templates else "partial",
                "error": "Validation errors found",
                "validation_errors": validation_errors,
                "validation_warnings": validation_warnings,
                "applied_changes": False,
                "ai_raw_response": ai_response,
            }
        
        # Apply changes (or simulate)
        if apply_changes:
            log.info("[apply_ai_suggestion] Applying %d validated templates to database...", len(validated_templates))
            try:
                with transaction.atomic():
                    result = self._apply_templates(
                        validated_templates,
                        account_code_to_id,
                    )
                    templates_created = result["templates_created"]
                    templates_updated = result["templates_updated"]
                    lines_created = result["lines_created"]
                    lines_updated = result["lines_updated"]
                
                log.info("[apply_ai_suggestion] ✓ Database changes committed successfully")
                log.info("  → Templates created: %d", templates_created)
                log.info("  → Templates updated: %d", templates_updated)
                log.info("  → Lines created: %d", lines_created)
                log.info("  → Lines updated: %d", lines_updated)
                
            except Exception as e:
                log.exception("[apply_ai_suggestion] ✗ Error applying templates: %s", e)
                return {
                    "status": "error",
                    "error": f"Database error: {e}",
                    "validation_errors": validation_errors,
                    "validation_warnings": validation_warnings,
                    "applied_changes": False,
                    "ai_raw_response": ai_response,
                }
        else:
            # Simulation mode - count what would be created/updated
            log.info("[apply_ai_suggestion] Simulating changes (not applying to database)...")
            result = self._simulate_apply(validated_templates)
            templates_created = result["templates_would_create"]
            templates_updated = result["templates_would_update"]
            lines_created = result["lines_would_create"]
            lines_updated = result["lines_would_update"]
            
            log.info("[apply_ai_suggestion] ✓ Simulation complete")
            log.info("  → Templates would be created: %d", templates_created)
            log.info("  → Templates would be updated: %d", templates_updated)
            log.info("  → Lines would be created: %d", lines_created)
            log.info("  → Lines would be updated: %d", lines_updated)
        
        log.info("[apply_ai_suggestion] ✓ Apply/simulate complete")
        
        return {
            "status": "success",
            "applied_changes": apply_changes,
            "templates_created": templates_created,
            "templates_updated": templates_updated,
            "lines_created": lines_created,
            "lines_updated": lines_updated,
            "validation_warnings": validation_warnings,
            "ai_raw_response": ai_response,
        }
    
    def _validate_template(
        self,
        tpl_data: Dict[str, Any],
        index: int,
        valid_account_codes: Set[str],
        use_path_based: bool = False,
        account_path_to_ids: Dict[str, List[int]] = None,
    ) -> Tuple[List[str], List[str], Optional[Dict[str, Any]]]:
        """
        Validate a single template from AI response.
        
        Returns (errors, warnings, validated_data or None)
        """
        errors = []
        warnings = []
        
        # Required fields
        statement_type = tpl_data.get("statement_type", "")
        template_code = tpl_data.get("template_code", "")
        template_name = tpl_data.get("template_name", "")
        
        if not statement_type:
            errors.append(f"Template {index}: missing 'statement_type'")
        elif statement_type not in self.STATEMENT_TYPE_MAP:
            errors.append(f"Template {index}: invalid statement_type '{statement_type}'")
        
        if not template_code:
            errors.append(f"Template {index}: missing 'template_code'")
        
        if not template_name:
            errors.append(f"Template {index}: missing 'template_name'")
        
        # Validate lines
        lines_data = tpl_data.get("lines", [])
        if not lines_data:
            warnings.append(f"Template {index} ({template_name}): no lines defined")
        
        validated_lines = []
        line_codes_seen: Set[str] = set()
        
        for line_idx, line_data in enumerate(lines_data):
            line_errors, line_warnings, validated_line = self._validate_line(
                line_data, line_idx, template_name, valid_account_codes, line_codes_seen,
                use_path_based, account_path_to_ids or {}
            )
            errors.extend(line_errors)
            warnings.extend(line_warnings)
            
            if validated_line:
                line_codes_seen.add(validated_line["line_code"])
                validated_lines.append(validated_line)
        
        if errors:
            return errors, warnings, None
        
        return errors, warnings, {
            "statement_type": statement_type,
            "template_code": template_code,
            "template_name": template_name,
            "description": tpl_data.get("description", ""),
            "is_default": bool(tpl_data.get("is_default", False)),
            "lines": validated_lines,
        }
    
    def _validate_line(
        self,
        line_data: Dict[str, Any],
        index: int,
        template_name: str,
        valid_account_codes: Set[str],
        line_codes_seen: Set[str],
        use_path_based: bool = False,
        account_path_to_ids: Dict[str, List[int]] = None,
    ) -> Tuple[List[str], List[str], Optional[Dict[str, Any]]]:
        """
        Validate a single line from AI response.
        
        Returns (errors, warnings, validated_data or None)
        """
        errors = []
        warnings = []
        prefix = f"Template '{template_name}' Line {index}"
        
        line_code = line_data.get("line_code", "")
        label = line_data.get("label", "")
        line_type = line_data.get("line_type", "account")
        order = line_data.get("order", (index + 1) * 10)
        
        if not line_code:
            errors.append(f"{prefix}: missing 'line_code'")
        elif line_code in line_codes_seen:
            errors.append(f"{prefix}: duplicate line_code '{line_code}'")
        
        if not label:
            errors.append(f"{prefix}: missing 'label'")
        
        if line_type not in self.VALID_LINE_TYPES:
            warnings.append(f"{prefix}: invalid line_type '{line_type}', defaulting to 'account'")
            line_type = "account"
        
        # Validate linked accounts
        linked_accounts = line_data.get("linked_accounts", [])
        validated_accounts = []
        account_path_contains = None
        
        for acc_data in linked_accounts:
            acc_code = acc_data.get("account_identifier", "")
            acc_path = acc_data.get("account_path", "")  # AI can provide path when code is missing
            
            if acc_code and acc_code in valid_account_codes:
                # Valid account code
                validated_accounts.append({
                    "account_code": acc_code,
                    "aggregation_type": acc_data.get("aggregation_type", "sum"),
                })
            elif use_path_based and acc_path:
                # Use path-based matching when codes aren't available
                # Find accounts that match this path (exact or contains)
                matching_paths = [
                    path for path in (account_path_to_ids or {}).keys()
                    if acc_path in path or path in acc_path
                ]
                if matching_paths:
                    account_path_contains = acc_path
                    validated_accounts.append({
                        "account_code": None,  # No code available
                        "account_path": acc_path,
                        "aggregation_type": acc_data.get("aggregation_type", "sum"),
                    })
                else:
                    warnings.append(f"{prefix}: account_path '{acc_path}' not found in CoA")
            elif acc_code and acc_code not in valid_account_codes:
                # Invalid account code
                if use_path_based:
                    warnings.append(f"{prefix}: account_identifier '{acc_code}' not found. Consider using account_path instead.")
                else:
                    warnings.append(f"{prefix}: account_identifier '{acc_code}' not found in CoA")
        
        # Validate account_code_prefix
        account_code_prefix = line_data.get("account_code_prefix", "")
        if account_code_prefix:
            # Check if any accounts match this prefix
            matching = [c for c in valid_account_codes if c.startswith(account_code_prefix)]
            if not matching and not use_path_based:
                warnings.append(f"{prefix}: no accounts match prefix '{account_code_prefix}'")
        
        # Check for account_path_contains in line_data (AI can provide this directly)
        if not account_path_contains:
            account_path_contains = line_data.get("account_path_contains", "")
        
        # Display options
        display_opts = line_data.get("display_options", {})
        is_bold = display_opts.get("bold", False) if isinstance(display_opts, dict) else False
        indent_level = display_opts.get("indent_level", 0) if isinstance(display_opts, dict) else 0
        
        # Calculation
        calculation = line_data.get("calculation", {})
        formula_type = calculation.get("formula_type", "none") if isinstance(calculation, dict) else "none"
        custom_formula = calculation.get("custom_formula", "") if isinstance(calculation, dict) else ""
        
        if errors:
            return errors, warnings, None
        
        return errors, warnings, {
            "line_code": line_code,
            "label": label,
            "line_type": line_type,
            "order": order,
            "parent_line_code": line_data.get("parent_line_code"),
            "linked_accounts": validated_accounts,
            "account_code_prefix": account_code_prefix,
            "account_path_contains": account_path_contains or "",
            "formula_type": formula_type,
            "custom_formula": custom_formula,
            "is_bold": is_bold,
            "indent_level": indent_level,
        }
    
    def _apply_templates(
        self,
        validated_templates: List[Dict[str, Any]],
        account_code_to_id: Dict[str, int],
    ) -> Dict[str, int]:
        """
        Apply validated templates to the database.
        
        Must be called within a transaction.
        """
        templates_created = 0
        templates_updated = 0
        lines_created = 0
        lines_updated = 0
        
        # Get all accounts for path-based matching
        all_accounts_list = list(Account.objects.filter(
            company_id=self.company_id,
            is_active=True,
        ))
        account_path_map = {acc.get_path(): acc.id for acc in all_accounts_list}
        
        for tpl_data in validated_templates:
            report_type = self.STATEMENT_TYPE_MAP[tpl_data["statement_type"]]
            
            # Find or create template
            template, created = FinancialStatementTemplate.objects.get_or_create(
                company_id=self.company_id,
                name=tpl_data["template_name"],
                defaults={
                    "report_type": report_type,
                    "description": tpl_data.get("description", ""),
                    "is_active": True,
                    "is_default": tpl_data.get("is_default", False),
                }
            )
            
            if created:
                templates_created += 1
                log.info("Created template: %s", template.name)
            else:
                templates_updated += 1
                template.report_type = report_type
                template.description = tpl_data.get("description", "")
                template.save()
                log.info("Updated template: %s", template.name)
            
            # Handle is_default
            if tpl_data.get("is_default", False):
                # Unset other defaults for this report_type
                FinancialStatementTemplate.objects.filter(
                    company_id=self.company_id,
                    report_type=report_type,
                    is_default=True,
                ).exclude(id=template.id).update(is_default=False)
                
                template.is_default = True
                template.save()
            
            # Build line_code to line_number map for parent references
            line_code_to_number = {
                line["line_code"]: line["order"]
                for line in tpl_data["lines"]
            }
            
            # First pass: create/update lines without parent
            line_code_to_obj: Dict[str, FinancialStatementLineTemplate] = {}
            
            for line_data in tpl_data["lines"]:
                line_number = line_data["order"]
                
                # Get account FK if single account is linked
                account_id = None
                account_ids = []
                account_path_contains = line_data.get("account_path_contains", "")
                
                linked_accounts = line_data.get("linked_accounts", [])
                if len(linked_accounts) == 1:
                    acc_data = linked_accounts[0]
                    acc_code = acc_data.get("account_code")
                    acc_path = acc_data.get("account_path", "")
                    
                    if acc_code and acc_code in account_code_to_id:
                        # Use account code
                        account_id = account_code_to_id.get(acc_code)
                    elif acc_path:
                        # Use path to find account
                        matching_paths = [
                            path for path in account_path_map.keys()
                            if acc_path in path or path in acc_path
                        ]
                        if matching_paths:
                            # Use first matching path's account ID
                            account_id = account_path_map.get(matching_paths[0])
                            if not account_path_contains:
                                account_path_contains = acc_path
                elif len(linked_accounts) > 1:
                    # Multiple accounts - collect IDs
                    for acc_data in linked_accounts:
                        acc_code = acc_data.get("account_code")
                        acc_path = acc_data.get("account_path", "")
                        
                        if acc_code and acc_code in account_code_to_id:
                            account_ids.append(account_code_to_id[acc_code])
                        elif acc_path:
                            # Find accounts by path
                            matching_paths = [
                                path for path in account_path_map.keys()
                                if acc_path in path or path in acc_path
                            ]
                            for path in matching_paths:
                                acc_id = account_path_map.get(path)
                                if acc_id and acc_id not in account_ids:
                                    account_ids.append(acc_id)
                            if not account_path_contains and matching_paths:
                                # Use common path prefix if available
                                account_path_contains = acc_path
                
                # Determine calculation_type and formula
                formula_type = line_data.get("formula_type", "none")
                if formula_type == "formula":
                    calculation_type = "formula"
                    formula = line_data.get("custom_formula", "")
                elif formula_type == "sum_of_children":
                    calculation_type = "sum"
                    formula = ""
                else:
                    calculation_type = "balance"
                    formula = ""
                
                # Find or create line
                line, line_created = FinancialStatementLineTemplate.objects.get_or_create(
                    template=template,
                    line_number=line_number,
                    defaults={
                        "label": line_data["label"],
                        "line_type": line_data["line_type"],
                        "account_id": account_id,
                        "account_code_prefix": line_data.get("account_code_prefix", ""),
                        "account_path_contains": account_path_contains,
                        "account_ids": account_ids,
                        "calculation_type": calculation_type,
                        "formula": formula,
                        "indent_level": line_data.get("indent_level", 0),
                        "is_bold": line_data.get("is_bold", False),
                    }
                )
                
                if line_created:
                    lines_created += 1
                else:
                    lines_updated += 1
                    line.label = line_data["label"]
                    line.line_type = line_data["line_type"]
                    line.account_id = account_id
                    line.account_code_prefix = line_data.get("account_code_prefix", "")
                    line.account_path_contains = account_path_contains
                    line.account_ids = account_ids
                    line.calculation_type = calculation_type
                    line.formula = formula
                    line.indent_level = line_data.get("indent_level", 0)
                    line.is_bold = line_data.get("is_bold", False)
                    line.save()
                
                line_code_to_obj[line_data["line_code"]] = line
            
            # Second pass: set parent references
            for line_data in tpl_data["lines"]:
                parent_line_code = line_data.get("parent_line_code")
                if parent_line_code and parent_line_code in line_code_to_obj:
                    line = line_code_to_obj[line_data["line_code"]]
                    parent = line_code_to_obj[parent_line_code]
                    if line.parent_line_id != parent.id:
                        line.parent_line = parent
                        line.save()
        
        return {
            "templates_created": templates_created,
            "templates_updated": templates_updated,
            "lines_created": lines_created,
            "lines_updated": lines_updated,
        }
    
    def _simulate_apply(
        self,
        validated_templates: List[Dict[str, Any]],
    ) -> Dict[str, int]:
        """
        Simulate applying templates without committing to database.
        """
        templates_would_create = 0
        templates_would_update = 0
        lines_would_create = 0
        lines_would_update = 0
        
        for tpl_data in validated_templates:
            # Check if template exists
            exists = FinancialStatementTemplate.objects.filter(
                company_id=self.company_id,
                name=tpl_data["template_name"],
            ).exists()
            
            if exists:
                templates_would_update += 1
                template = FinancialStatementTemplate.objects.get(
                    company_id=self.company_id,
                    name=tpl_data["template_name"],
                )
            else:
                templates_would_create += 1
                template = None
            
            # Count lines
            for line_data in tpl_data["lines"]:
                if template:
                    line_exists = FinancialStatementLineTemplate.objects.filter(
                        template=template,
                        line_number=line_data["order"],
                    ).exists()
                    if line_exists:
                        lines_would_update += 1
                    else:
                        lines_would_create += 1
                else:
                    lines_would_create += 1
        
        return {
            "templates_would_create": templates_would_create,
            "templates_would_update": templates_would_update,
            "lines_would_create": lines_would_create,
            "lines_would_update": lines_would_update,
        }


# =============================================================================
# Convenience function for external use
# =============================================================================

def generate_templates_for_company(
    company_id: int,
    user_preferences_text: str = "",
    apply_changes: bool = True,
    ai_provider: str = "openai",
    ai_model: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Convenience function to generate AI-powered template suggestions.
    
    Parameters
    ----------
    company_id : int
        The company ID to generate templates for.
    user_preferences_text : str
        Free-text user preferences.
    apply_changes : bool
        If True, apply changes to database.
    ai_provider : str
        AI provider ("openai" or "anthropic").
    ai_model : Optional[str]
        Specific AI model to use.
    
    Returns
    -------
    Dict[str, Any]
        Result summary.
    
    Example
    -------
    >>> result = generate_templates_for_company(
    ...     company_id=1,
    ...     user_preferences_text="I want revenue broken down to 3 levels",
    ...     apply_changes=True
    ... )
    >>> print(result["status"])
    "success"
    """
    service = TemplateSuggestionService(
        company_id=company_id,
        user_preferences=user_preferences_text,
        ai_provider=ai_provider,
        ai_model=ai_model,
    )
    return service.generate_suggestions(apply_changes=apply_changes)

