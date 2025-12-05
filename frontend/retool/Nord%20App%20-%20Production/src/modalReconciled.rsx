<ModalFrame
  id="modalReconciled"
  enableFullBleed={true}
  footerPadding="8px 12px"
  headerPadding="8px 12px"
  hidden={true}
  hideOnEscape={true}
  isHiddenOnMobile={true}
  overlayInteraction={true}
  padding="8px 12px"
  showFooter={true}
  showHeader={true}
  showOverlay={true}
  size="fullScreen"
>
  <Header>
    <Text
      id="modalTitle47"
      value="### Registros Conciliados"
      verticalAlign="center"
    />
    <Button
      id="modalCloseButton52"
      ariaLabel="Close"
      horizontalAlign="right"
      iconBefore="bold/interface-delete-1"
      style={{ map: { border: "transparent" } }}
      styleVariant="outline"
    >
      <Event
        event="click"
        method="setHidden"
        params={{ map: { hidden: true } }}
        pluginId="modalReconciled"
        type="widget"
        waitMs="0"
        waitType="debounce"
      />
    </Button>
  </Header>
  <Body>
    <Table
      id="table55"
      actionsOverflowPosition={1}
      cellSelection="none"
      clearChangesetOnSave={true}
      data="{{ Conciliation_get3.data }}"
      defaultSelectedRow={{ mode: "index", indexType: "display", index: 0 }}
      emptyMessage="No rows found"
      enableSaveActions={true}
      rowHeight="medium"
      rowSelection="multiple"
      showBorder={true}
      showFooter={true}
      showHeader={true}
      toolbarPosition="bottom"
    >
      <Column
        id="ba1be"
        alignment="left"
        format="string"
        groupAggregationMode="none"
        key="reference"
        label="Reference"
        placeholder="Enter value"
        position="center"
        size={190.46875}
        summaryAggregationMode="none"
      />
      <Column
        id="a8220"
        alignment="right"
        editableOptions={{ showStepper: true }}
        format="decimal"
        formatOptions={{ showSeparators: true, notation: "standard" }}
        groupAggregationMode="sum"
        key="bank_sum_value"
        label="Bank sum value"
        placeholder="Enter value"
        position="center"
        size={119}
        summaryAggregationMode="none"
      />
      <Column
        id="d3a1f"
        alignment="right"
        editableOptions={{ showStepper: true }}
        format="decimal"
        formatOptions={{ showSeparators: true, notation: "standard" }}
        groupAggregationMode="sum"
        key="book_sum_value"
        label="Book sum value"
        placeholder="Enter value"
        position="center"
        size={121}
        summaryAggregationMode="none"
      />
      <Column
        id="6371b"
        alignment="right"
        editableOptions={{ showStepper: true }}
        format="decimal"
        formatOptions={{ showSeparators: true, notation: "standard" }}
        groupAggregationMode="sum"
        key="difference"
        label="Difference"
        placeholder="Enter value"
        position="center"
        size={95}
        summaryAggregationMode="none"
      />
      <Column
        id="db002"
        alignment="left"
        format="date"
        groupAggregationMode="none"
        key="bank_avg_date"
        label="Bank avg date"
        placeholder="Enter value"
        position="center"
        size={117}
        summaryAggregationMode="none"
      />
      <Column
        id="1e25c"
        alignment="left"
        format="date"
        groupAggregationMode="none"
        key="book_avg_date"
        label="Book avg date"
        placeholder="Enter value"
        position="center"
        size={141}
        summaryAggregationMode="none"
      />
      <Column
        id="3fcf9"
        alignment="left"
        format="string"
        groupAggregationMode="none"
        key="bank_description"
        label="Bank description"
        placeholder="Enter value"
        position="center"
        size={465}
        summaryAggregationMode="none"
      />
      <Column
        id="81233"
        alignment="left"
        format="string"
        groupAggregationMode="none"
        key="book_description"
        label="Book description"
        placeholder="Enter value"
        position="center"
        size={852}
        summaryAggregationMode="none"
      />
      <Column
        id="85de8"
        alignment="left"
        cellTooltipMode="overflow"
        format="multilineString"
        groupAggregationMode="none"
        key="notes"
        label="Notes"
        placeholder="Enter value"
        position="center"
        size={375}
        summaryAggregationMode="none"
      />
      <Column
        id="9abbf"
        alignment="right"
        editableOptions={{ showStepper: true }}
        format="decimal"
        formatOptions={{ showSeparators: true, notation: "standard" }}
        groupAggregationMode="sum"
        key="reconciliation_id"
        label="Reconciliation ID"
        placeholder="Enter value"
        position="center"
        size={108}
        summaryAggregationMode="none"
      />
      <Column
        id="423db"
        alignment="left"
        cellTooltipMode="overflow"
        format="tags"
        formatOptions={{ automaticColors: true }}
        groupAggregationMode="none"
        key="bank_ids"
        label="Bank ids"
        placeholder="Select options"
        position="center"
        size={100}
        summaryAggregationMode="none"
      />
      <Column
        id="171ee"
        alignment="left"
        cellTooltipMode="overflow"
        format="tags"
        formatOptions={{ automaticColors: true }}
        groupAggregationMode="none"
        key="book_ids"
        label="Book ids"
        placeholder="Select options"
        position="center"
        size={71}
        summaryAggregationMode="none"
      />
      <Action
        id="481f6"
        icon="bold/interface-delete-bin-put-back-1"
        label="Delete"
      >
        <Event
          event="clickAction"
          method="setValue"
          params={{ map: { value: "{{ currentSourceRow }}" } }}
          pluginId="Conciliation_selected"
          type="state"
          waitMs="0"
          waitType="debounce"
        />
        <Event
          enabled=""
          event="clickAction"
          method="trigger"
          params={{}}
          pluginId="Conciliation_delete"
          type="datasource"
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
          pluginId="table55"
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
          pluginId="table55"
          type="widget"
          waitMs="0"
          waitType="debounce"
        />
      </ToolbarButton>
    </Table>
  </Body>
</ModalFrame>
