<ExpandedRow id="table5ExpandedRow">
  <Table
    id="table7"
    cellSelection="none"
    clearChangesetOnSave={true}
    data="{{ journal_entries.data }}"
    defaultFilters={{
      0: {
        ordered: [
          { id: "3a140" },
          { columnId: "d7e76" },
          { operator: "=" },
          { value: "{{ currentSourceRow.id }}" },
          { disabled: false },
        ],
      },
    }}
    defaultSelectedRow={{ mode: "index", indexType: "display", index: 0 }}
    emptyMessage="No rows found"
    enableSaveActions={true}
    heightType="auto"
    primaryKeyColumnId="44389"
    rowHeight="small"
    showBorder={true}
    showHeader={true}
    showSummaryRow={true}
    style={{ summaryRowBackground: "surfacePrimary" }}
    toolbarPosition="bottom"
  >
    <Column
      id="44389"
      alignment="right"
      editable={false}
      editableOptions={{ showStepper: true }}
      format="decimal"
      formatOptions={{ showSeparators: true, notation: "standard" }}
      groupAggregationMode="sum"
      key="id"
      label="ID"
      placeholder="Enter value"
      position="center"
      size={100}
    />
    <Column
      id="98d36"
      alignment="left"
      format="json"
      groupAggregationMode="none"
      key="entity"
      label="Entity"
      placeholder="Enter value"
      position="center"
      size={167}
      summaryAggregationMode="none"
      valueOverride="{{ item.name }}"
    />
    <Column
      id="1c2d5"
      alignment="left"
      format="json"
      groupAggregationMode="none"
      key="account"
      label="Account"
      placeholder="Enter value"
      position="center"
      size={159}
      summaryAggregationMode="none"
      valueOverride="{{ item.account_code }} {{ item.name }}"
    />
    <Column
      id="838cf"
      alignment="right"
      editableOptions={{ showStepper: true }}
      format="decimal"
      formatOptions={{ showSeparators: true, notation: "standard" }}
      groupAggregationMode="sum"
      key="debit_amount"
      label="Debit amount"
      placeholder="Enter value"
      position="center"
      size={100}
      summaryAggregationMode="sum"
    />
    <Column
      id="cc27e"
      alignment="right"
      editableOptions={{ showStepper: true }}
      format="decimal"
      formatOptions={{ showSeparators: true, notation: "standard" }}
      groupAggregationMode="sum"
      key="credit_amount"
      label="Credit amount"
      placeholder="Enter value"
      position="center"
      size={100}
      summaryAggregationMode="sum"
    />
    <Column
      id="98f97"
      alignment="left"
      format="tag"
      formatOptions={{ automaticColors: true }}
      groupAggregationMode="none"
      key="state"
      label="State"
      placeholder="Select option"
      position="center"
      size={100}
      summaryAggregationMode="none"
      valueOverride="{{ _.startCase(item) }}"
    />
    <Column
      id="d7e76"
      alignment="right"
      editableOptions={{ showStepper: true }}
      format="decimal"
      formatOptions={{ showSeparators: true, notation: "standard" }}
      groupAggregationMode="sum"
      hidden="true"
      key="transaction"
      label="Transaction"
      placeholder="Enter value"
      position="center"
      size={100}
      summaryAggregationMode="none"
    />
  </Table>
</ExpandedRow>
