<ExpandedRow id="table44ExpandedRow">
  <Table
    id="table45"
    cellSelection="none"
    clearChangesetOnSave={true}
    data="{{ currentSourceRow.bank_transaction_details }}"
    defaultSelectedRow={{ mode: "index", indexType: "display", index: 0 }}
    emptyMessage="No rows found"
    enableSaveActions={true}
    heightType="auto"
    primaryKeyColumnId="e572e"
    showBorder={true}
    showFooter={true}
    showHeader={true}
    toolbarPosition="bottom"
  >
    <Column
      id="e572e"
      alignment="right"
      editableOptions={{ showStepper: true }}
      format="decimal"
      formatOptions={{ showSeparators: true, notation: "standard" }}
      groupAggregationMode="sum"
      key="id"
      label="ID"
      placeholder="Enter value"
      position="center"
      size={100}
      summaryAggregationMode="none"
    />
    <Column
      id="9a09f"
      alignment="left"
      format="date"
      groupAggregationMode="none"
      key="date"
      label="Date"
      placeholder="Enter value"
      position="center"
      size={100}
      summaryAggregationMode="none"
    />
    <Column
      id="c6a8d"
      alignment="right"
      editableOptions={{ showStepper: true }}
      format="decimal"
      formatOptions={{ showSeparators: true, notation: "standard" }}
      groupAggregationMode="sum"
      key="amount"
      label="Amount"
      placeholder="Enter value"
      position="center"
      size={100}
      summaryAggregationMode="none"
    />
    <Column
      id="42704"
      alignment="right"
      editableOptions={{ showStepper: true }}
      format="decimal"
      formatOptions={{ showSeparators: true, notation: "standard" }}
      groupAggregationMode="sum"
      key="bank_account_id"
      label="Bank account ID"
      placeholder="Enter value"
      position="center"
      size={100}
      summaryAggregationMode="none"
    />
    <Column
      id="5232d"
      alignment="right"
      editableOptions={{ showStepper: true }}
      format="decimal"
      formatOptions={{ showSeparators: true, notation: "standard" }}
      groupAggregationMode="sum"
      key="entity_id"
      label="Entity ID"
      placeholder="Enter value"
      position="center"
      size={100}
      summaryAggregationMode="none"
    />
  </Table>
  <Table
    id="table46"
    cellSelection="none"
    clearChangesetOnSave={true}
    data="{{ currentSourceRow.journal_entry_details }}"
    defaultSelectedRow={{ mode: "index", indexType: "display", index: 0 }}
    emptyMessage="No rows found"
    enableSaveActions={true}
    heightType="auto"
    primaryKeyColumnId="e572e"
    showBorder={true}
    showFooter={true}
    showHeader={true}
    toolbarPosition="bottom"
  >
    <Column
      id="e572e"
      alignment="right"
      editableOptions={{ showStepper: true }}
      format="decimal"
      formatOptions={{ showSeparators: true, notation: "standard" }}
      groupAggregationMode="sum"
      key="id"
      label="ID"
      placeholder="Enter value"
      position="center"
      size={100}
      summaryAggregationMode="none"
    />
    <Column
      id="9a09f"
      alignment="left"
      format="date"
      groupAggregationMode="none"
      key="date"
      label="Date"
      placeholder="Enter value"
      position="center"
      size={100}
      summaryAggregationMode="none"
    />
    <Column
      id="c6a8d"
      alignment="right"
      editableOptions={{ showStepper: true }}
      format="decimal"
      formatOptions={{ showSeparators: true, notation: "standard" }}
      groupAggregationMode="sum"
      key="amount"
      label="Amount"
      placeholder="Enter value"
      position="center"
      size={100}
      summaryAggregationMode="none"
    />
    <Column
      id="42704"
      alignment="right"
      editableOptions={{ showStepper: true }}
      format="decimal"
      formatOptions={{ showSeparators: true, notation: "standard" }}
      groupAggregationMode="sum"
      key="bank_account_id"
      label="Bank account ID"
      placeholder="Enter value"
      position="center"
      size={100}
      summaryAggregationMode="none"
    />
    <Column
      id="5232d"
      alignment="right"
      editableOptions={{ showStepper: true }}
      format="decimal"
      formatOptions={{ showSeparators: true, notation: "standard" }}
      groupAggregationMode="sum"
      key="entity_id"
      label="Entity ID"
      placeholder="Enter value"
      position="center"
      size={100}
      summaryAggregationMode="none"
    />
  </Table>
</ExpandedRow>
