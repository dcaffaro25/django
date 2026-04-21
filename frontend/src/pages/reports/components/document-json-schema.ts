// JSON Schema for the canonical template document — fed to Monaco's JSON
// diagnostics so users get live validation + autocomplete while editing.
// Hand-kept in sync with:
//   - accounting/reports/services/document_schema.py  (pydantic)
//   - frontend/src/features/reports/types.ts          (TS)
// Kept intentionally loose where pydantic does the real heavy lifting —
// Monaco is here for developer ergonomics, not authoritative validation
// (the backend pydantic pass runs on every save).

export const TEMPLATE_DOCUMENT_JSON_SCHEMA = {
  $schema: "http://json-schema.org/draft-07/schema#",
  title: "Template Document",
  type: "object",
  required: ["name", "report_type", "blocks"],
  additionalProperties: false,
  properties: {
    version: { type: "integer", minimum: 1 },
    name: { type: "string", minLength: 1, maxLength: 200 },
    report_type: {
      type: "string",
      enum: [
        "balance_sheet",
        "income_statement",
        "cash_flow",
        "trial_balance",
        "general_ledger",
        "custom",
      ],
    },
    description: { type: ["string", "null"], maxLength: 1000 },
    defaults: { $ref: "#/definitions/BlockDefaults" },
    blocks: {
      type: "array",
      items: { $ref: "#/definitions/Block" },
    },
  },
  definitions: {
    BlockDefaults: {
      type: "object",
      additionalProperties: false,
      properties: {
        calculation_method: {
          type: ["string", "null"],
          enum: [
            "ending_balance", "opening_balance", "net_movement",
            "debit_total", "credit_total", "change_in_balance",
            "rollup_children", "formula", "manual_input", null,
          ],
        },
        sign_policy: {
          type: ["string", "null"],
          enum: ["natural", "invert", "absolute", null],
        },
        scale: {
          type: ["string", "null"],
          enum: ["none", "K", "M", "B", null],
        },
        decimal_places: { type: ["integer", "null"], minimum: 0, maximum: 8 },
        show_zero: { type: ["boolean", "null"] },
        bold: { type: ["boolean", "null"] },
      },
    },
    AccountsSelector: {
      type: "object",
      additionalProperties: false,
      properties: {
        account_ids: { type: "array", items: { type: "integer" } },
        code_prefix: { type: ["string", "null"] },
        path_contains: { type: ["string", "null"] },
        include_descendants: { type: "boolean" },
      },
    },
    IdString: {
      type: "string",
      pattern: "^[A-Za-z_][A-Za-z0-9_]*$",
      minLength: 1,
      maxLength: 64,
    },
    Block: {
      oneOf: [
        {
          type: "object",
          additionalProperties: false,
          required: ["type", "id"],
          properties: {
            type: { const: "section" },
            id: { $ref: "#/definitions/IdString" },
            label: { type: ["string", "null"], maxLength: 200 },
            bold: { type: ["boolean", "null"] },
            indent: { type: ["integer", "null"], minimum: 0, maximum: 8 },
            ai_explanation: { type: ["string", "null"], maxLength: 2000 },
            defaults: { $ref: "#/definitions/BlockDefaults" },
            children: { type: "array", items: { $ref: "#/definitions/Block" } },
          },
        },
        {
          type: "object",
          additionalProperties: false,
          required: ["type", "id"],
          properties: {
            type: { const: "header" },
            id: { $ref: "#/definitions/IdString" },
            label: { type: ["string", "null"], maxLength: 200 },
            bold: { type: ["boolean", "null"] },
            indent: { type: ["integer", "null"], minimum: 0, maximum: 8 },
            ai_explanation: { type: ["string", "null"], maxLength: 2000 },
          },
        },
        {
          type: "object",
          additionalProperties: false,
          required: ["type", "id"],
          properties: {
            type: { const: "spacer" },
            id: { $ref: "#/definitions/IdString" },
          },
        },
        {
          type: "object",
          additionalProperties: false,
          required: ["type", "id"],
          properties: {
            type: { const: "line" },
            id: { $ref: "#/definitions/IdString" },
            label: { type: ["string", "null"], maxLength: 200 },
            bold: { type: ["boolean", "null"] },
            indent: { type: ["integer", "null"], minimum: 0, maximum: 8 },
            ai_explanation: { type: ["string", "null"], maxLength: 2000 },
            accounts: { $ref: "#/definitions/AccountsSelector" },
            calculation_method: {
              type: ["string", "null"],
              enum: [
                "ending_balance", "opening_balance", "net_movement",
                "debit_total", "credit_total", "change_in_balance",
                "rollup_children", "formula", "manual_input", null,
              ],
            },
            sign_policy: { type: ["string", "null"], enum: ["natural", "invert", "absolute", null] },
            scale: { type: ["string", "null"], enum: ["none", "K", "M", "B", null] },
            decimal_places: { type: ["integer", "null"], minimum: 0, maximum: 8 },
            manual_value: { type: ["string", "null"] },
            show_zero: { type: ["boolean", "null"] },
          },
        },
        {
          type: "object",
          additionalProperties: false,
          required: ["type", "id"],
          properties: {
            type: { const: "subtotal" },
            id: { $ref: "#/definitions/IdString" },
            label: { type: ["string", "null"], maxLength: 200 },
            bold: { type: ["boolean", "null"] },
            indent: { type: ["integer", "null"], minimum: 0, maximum: 8 },
            ai_explanation: { type: ["string", "null"], maxLength: 2000 },
            accounts: { $ref: "#/definitions/AccountsSelector" },
            calculation_method: {
              type: ["string", "null"],
              enum: [
                "ending_balance", "opening_balance", "net_movement",
                "debit_total", "credit_total", "change_in_balance",
                "rollup_children", "formula", "manual_input", null,
              ],
            },
            sign_policy: { type: ["string", "null"], enum: ["natural", "invert", "absolute", null] },
            scale: { type: ["string", "null"], enum: ["none", "K", "M", "B", null] },
            decimal_places: { type: ["integer", "null"], minimum: 0, maximum: 8 },
            formula: { type: ["string", "null"], maxLength: 500 },
          },
        },
        {
          type: "object",
          additionalProperties: false,
          required: ["type", "id"],
          properties: {
            type: { const: "total" },
            id: { $ref: "#/definitions/IdString" },
            label: { type: ["string", "null"], maxLength: 200 },
            bold: { type: ["boolean", "null"] },
            indent: { type: ["integer", "null"], minimum: 0, maximum: 8 },
            ai_explanation: { type: ["string", "null"], maxLength: 2000 },
            sign_policy: { type: ["string", "null"], enum: ["natural", "invert", "absolute", null] },
            scale: { type: ["string", "null"], enum: ["none", "K", "M", "B", null] },
            decimal_places: { type: ["integer", "null"], minimum: 0, maximum: 8 },
            formula: { type: ["string", "null"], maxLength: 500 },
          },
        },
      ],
    },
  },
} as const
