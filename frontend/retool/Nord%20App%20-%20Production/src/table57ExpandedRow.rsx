<ExpandedRow id="table57ExpandedRow">
  <Table
    id="table58"
    actionsOverflowPosition={2}
    cellSelection="none"
    clearChangesetOnSave={true}
    data="{{ currentSourceRow.suggestions }}"
    defaultSelectedRow={{ mode: "index", indexType: "display", index: 0 }}
    emptyMessage="No rows found"
    enableSaveActions={true}
    showBorder={true}
    showFooter={true}
    showHeader={true}
    toolbarPosition="bottom"
  >
    <Column
      id="8df36"
      alignment="left"
      format="tag"
      formatOptions={{ automaticColors: true }}
      groupAggregationMode="none"
      key="suggestion_type"
      label="Suggestion type"
      placeholder="Select option"
      position="center"
      size={100}
      summaryAggregationMode="none"
      valueOverride="{{ _.startCase(item) }}"
    />
    <Column
      id="2f855"
      alignment="right"
      editableOptions={{ showStepper: true }}
      format="percent"
      formatOptions={{ showSeparators: true, notation: "standard" }}
      groupAggregationMode="average"
      key="confidence_score"
      label="Confidence score"
      placeholder="Enter value"
      position="center"
      size={100}
      summaryAggregationMode="none"
    />
    <Column
      id="c4297"
      alignment="right"
      editableOptions={{ showStepper: true }}
      format="decimal"
      formatOptions={{ showSeparators: true, notation: "standard" }}
      groupAggregationMode="sum"
      key="match_count"
      label="Match count"
      placeholder="Enter value"
      position="center"
      size={100}
      summaryAggregationMode="none"
    />
    <Column
      id="38dbf"
      alignment="left"
      editableOptions={{ spellCheck: false }}
      format="string"
      groupAggregationMode="none"
      key="pattern"
      label="Pattern"
      placeholder="Enter value"
      position="center"
      size={133}
      summaryAggregationMode="none"
    />
    <Column
      id="0bc1b"
      alignment="left"
      cellTooltipMode="overflow"
      format="json"
      groupAggregationMode="none"
      key="transaction"
      label="Transaction"
      placeholder="Enter value"
      position="center"
      size={100}
      summaryAggregationMode="none"
    />
    <Column
      id="1017e"
      alignment="left"
      cellTooltipMode="overflow"
      format="json"
      formatOptions={{ automaticColors: true }}
      groupAggregationMode="none"
      key="journal_entries"
      label="Journal entries"
      placeholder="Enter value"
      position="center"
      size={100}
      summaryAggregationMode="none"
    />
    <Column
      id="54c59"
      alignment="left"
      cellTooltipMode="overflow"
      format="json"
      formatOptions={{ automaticColors: true }}
      groupAggregationMode="none"
      key="historical_matches"
      label="Historical matches"
      placeholder="Enter value"
      position="center"
      size={100}
      summaryAggregationMode="none"
    />
    <Action id="fb9f6" icon="bold/interface-add-2" label="Action 1">
      <Event
        event="clickAction"
        method="run"
        params={{
          map: {
            src: 'console.log("🚀 Script started");\n\nconst suggestion = currentSourceRow;\nconst bankTransactionId = table57.currentSourceRow.bank_transaction_id;\n\nif (!bankTransactionId) {\n  utils.showNotification({\n    title: "Error",\n    description: "Missing bank_transaction_id",\n    notificationType: "error"\n  });\n  return;\n}\n\nconst suggestionTypeMap = {\n  "Create New": "create_new",\n  "create_new": "create_new",\n  "Use Existing Book": "use_existing_book",\n  "use_existing_book": "use_existing_book"\n};\n\nconst apiSuggestionType = suggestionTypeMap[suggestion.suggestion_type] || "create_new";\n\nconst payload = {\n  suggestions: [{\n    suggestion_type: apiSuggestionType,\n    bank_transaction_id: bankTransactionId,\n    transaction: {\n      date: suggestion.transaction.date,\n      entity_id: suggestion.transaction.entity_id,\n      description: suggestion.transaction.description,\n      amount: suggestion.transaction.amount,\n      currency_id: suggestion.transaction.currency_id,\n      state: suggestion.transaction.state || "pending"\n    },\n    journal_entries: suggestion.journal_entries.map(je => ({\n      account_id: je.account_id,\n      debit_amount: je.debit_amount,\n      credit_amount: je.credit_amount,\n      description: je.description,\n      cost_center_id: je.cost_center_id\n    }))\n  }]\n};\n\nconsole.log("📦 payload:", JSON.stringify(payload, null, 2));\n\n// Just log if unbalanced - no blocking confirmation\nconst totalDebit = suggestion.journal_entries.reduce((sum, je) => \n  sum + parseFloat(je.debit_amount || 0), 0);\nconst totalCredit = suggestion.journal_entries.reduce((sum, je) => \n  sum + parseFloat(je.credit_amount || 0), 0);\nconst isBalanced = Math.abs(totalDebit - totalCredit) < 0.01;\n\nif (!isBalanced) {\n  console.log("⚠️ Unbalanced transaction - proceeding anyway");\n}\n\nconsole.log("🔄 Calling API...");\n\ntry {\n  const response = await createSuggestionsQuery.trigger({\n    additionalScope: { payload }\n  });\n  \n  console.log("📥 Response:", response);\n  \n  if (response?.errors?.length > 0) {\n    utils.showNotification({\n      title: "Error",\n      description: response.errors[0].error || JSON.stringify(response.errors[0]),\n      notificationType: "error"\n    });\n    return;\n  }\n  \n  const successMsg = isBalanced \n    ? "Transaction created successfully" \n    : "Unbalanced transaction created (single entry)";\n  \n  utils.showNotification({\n    title: "✓ Created",\n    description: successMsg,\n    notificationType: "success"\n  });\n  \n  await table57?.refresh();\n  \n} catch (error) {\n  console.log("💥 Error:", error);\n  utils.showNotification({\n    title: "API Error",\n    description: error.message,\n    notificationType: "error"\n  });\n}',
          },
        }}
        pluginId=""
        type="script"
        waitMs="0"
        waitType="debounce"
      />
    </Action>
    <Action id="c7dfb" icon="bold/interface-edit-pencil" label="Action 2">
      <Event
        event="clickAction"
        method="run"
        params={{ map: { src: 'console.log("hi")' } }}
        pluginId=""
        type="script"
        waitMs="0"
        waitType="debounce"
      />
    </Action>
    <ToolbarButton
      id="1a"
      icon="bold/interface-text-formatting-filter-2"
      label="Filter"
      type="filter"
    />
    <ToolbarButton
      id="3c"
      icon="bold/interface-download-button-2"
      label="Download"
      type="custom"
    >
      <Event
        event="clickToolbar"
        method="exportData"
        pluginId="table58"
        type="widget"
        waitMs="0"
        waitType="debounce"
      />
    </ToolbarButton>
    <ToolbarButton
      id="4d"
      icon="bold/interface-arrows-round-left"
      label="Refresh"
      type="custom"
    >
      <Event
        event="clickToolbar"
        method="refresh"
        pluginId="table58"
        type="widget"
        waitMs="0"
        waitType="debounce"
      />
    </ToolbarButton>
  </Table>
</ExpandedRow>
