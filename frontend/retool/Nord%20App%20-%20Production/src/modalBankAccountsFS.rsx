<ModalFrame
  id="modalBankAccountsFS"
  footerPadding="8px 12px"
  headerPadding="8px 12px"
  hidden={true}
  hideOnEscape={true}
  isHiddenOnMobile={true}
  overlayInteraction={true}
  padding="8px 12px"
  showHeader={true}
  showOverlay={true}
  size="fullScreen"
>
  <Header>
    <Text
      id="modalTitle14"
      value="### Contas Bancárias"
      verticalAlign="center"
    />
    <Button
      id="modalCloseButton16"
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
        pluginId="modalBankAccountsFS"
        type="widget"
        waitMs="0"
        waitType="debounce"
      />
    </Button>
  </Header>
  <Body>
    <Table
      id="tableBankAccount5"
      actionsOverflowPosition={2}
      autoColumnWidth={true}
      cellSelection="none"
      clearChangesetOnSave={true}
      data="{{ bankaccount_get.data }}"
      defaultSelectedRow={{ mode: "index", indexType: "display", index: 0 }}
      emptyMessage="No rows found"
      enableSaveActions={true}
      rowHeight="medium"
      showFooter={true}
      showHeader={true}
      toolbarPosition="bottom"
    >
      <Column
        id="fd4d0"
        alignment="right"
        editableOptions={{ showStepper: true }}
        format="decimal"
        formatOptions={{ showSeparators: true, notation: "standard" }}
        groupAggregationMode="sum"
        key="id"
        label="ID"
        placeholder="Enter value"
        position="center"
        size={27.765625}
        summaryAggregationMode="none"
      />
      <Column
        id="2b815"
        alignment="left"
        format="string"
        groupAggregationMode="none"
        key="entity"
        label="Entity"
        placeholder="Enter value"
        position="center"
        size={121.90625}
        summaryAggregationMode="none"
        valueOverride="{{ item.name }}"
      />
      <Column
        id="9ba5c"
        alignment="left"
        format="string"
        groupAggregationMode="none"
        key="name"
        label="Name"
        placeholder="Enter value"
        position="center"
        size={92.734375}
        summaryAggregationMode="none"
      />
      <Column
        id="0c975"
        alignment="left"
        format="tag"
        formatOptions={{ automaticColors: true }}
        groupAggregationMode="none"
        key="account_type"
        label="Account type"
        placeholder="Select option"
        position="center"
        size={91.734375}
        summaryAggregationMode="none"
        valueOverride="{{ _.startCase(item) }}"
      />
      <Column
        id="57030"
        alignment="right"
        editableOptions={{ showStepper: true }}
        format="decimal"
        formatOptions={{ showSeparators: true, notation: "standard" }}
        groupAggregationMode="sum"
        hidden="true"
        key="company"
        label="Company"
        placeholder="Enter value"
        position="center"
        size={0}
        summaryAggregationMode="none"
      />
      <Column
        id="9588f"
        alignment="left"
        format="string"
        groupAggregationMode="none"
        key="currency"
        label="Currency"
        placeholder="Enter value"
        position="center"
        size={67.8125}
        summaryAggregationMode="none"
        valueOverride="{{ item.code }}"
      />
      <Column
        id="c17b4"
        alignment="left"
        format="string"
        groupAggregationMode="none"
        key="bank"
        label="Bank"
        placeholder="Enter value"
        position="center"
        size={134.171875}
        summaryAggregationMode="none"
        valueOverride="{{ item.name }}"
      />
      <Column
        id="d91f9"
        alignment="right"
        editableOptions={{ showStepper: true }}
        format="decimal"
        formatOptions={{ showSeparators: true, notation: "standard" }}
        groupAggregationMode="sum"
        key="branch_id"
        label="Branch ID"
        placeholder="Enter value"
        position="center"
        size={71.015625}
        summaryAggregationMode="none"
      />
      <Column
        id="37e6b"
        alignment="right"
        editableOptions={{ showStepper: true }}
        format="decimal"
        formatOptions={{ showSeparators: true, notation: "standard" }}
        groupAggregationMode="sum"
        key="account_number"
        label="Account number"
        placeholder="Enter value"
        position="center"
        size={109.71875}
        summaryAggregationMode="none"
      />
      <Column
        id="8b190"
        alignment="left"
        format="date"
        groupAggregationMode="none"
        key="balance_date"
        label="Balance date"
        placeholder="Enter value"
        position="center"
        size={90.640625}
        summaryAggregationMode="none"
      />
      <Column
        id="fa12f"
        alignment="right"
        editableOptions={{ showStepper: true }}
        format="decimal"
        formatOptions={{ showSeparators: true, notation: "standard" }}
        groupAggregationMode="sum"
        key="balance"
        label="Balance"
        placeholder="Enter value"
        position="center"
        size={60.875}
        summaryAggregationMode="none"
      />
      <Column
        id="a0163"
        alignment="right"
        editableOptions={{ showStepper: true }}
        format="decimal"
        formatOptions={{ showSeparators: true, notation: "standard" }}
        groupAggregationMode="sum"
        key="current_balance"
        label="Current balance"
        placeholder="Enter value"
        position="center"
        size={106.6875}
        summaryAggregationMode="none"
      />
      <Action id="3fbf6" icon="bold/interface-edit-pencil" label="Edit">
        <Event
          event="clickAction"
          method="setValue"
          params={{ ordered: [{ value: "{{ currentSourceRow }}" }] }}
          pluginId="bankaccount_selected"
          type="state"
          waitMs="0"
          waitType="debounce"
        />
        <Event
          event="clickAction"
          method="show"
          params={{}}
          pluginId="modalBankAccount"
          type="widget"
          waitMs="0"
          waitType="debounce"
        />
        <Event
          event="clickAction"
          method="setValue"
          params={{ map: { value: "edit" } }}
          pluginId="bankaccount_mode"
          type="state"
          waitMs="0"
          waitType="debounce"
        />
      </Action>
      <Action id="9e6d2" icon="bold/interface-file-double" label="Duplicate">
        <Event
          event="clickAction"
          method="setValue"
          params={{ map: { value: "{{ currentSourceRow }}" } }}
          pluginId="bankaccount_selected"
          type="state"
          waitMs="0"
          waitType="debounce"
        />
        <Event
          event="clickAction"
          method="setValue"
          params={{ map: { value: "new" } }}
          pluginId="bankaccount_mode"
          type="state"
          waitMs="0"
          waitType="debounce"
        />
        <Event
          event="clickAction"
          method="show"
          params={{}}
          pluginId="modalBankAccount"
          type="widget"
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
          pluginId="tableBankAccount5"
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
          pluginId="tableBankAccount5"
          type="widget"
          waitMs="0"
          waitType="debounce"
        />
      </ToolbarButton>
      <ToolbarButton
        id="9357d"
        icon="bold/interface-add-1"
        label="Add Row"
        type="custom"
      >
        <Event
          event="clickToolbar"
          method="setValue"
          params={{ ordered: [{ value: '""' }] }}
          pluginId="bankaccount_selected"
          type="state"
          waitMs="0"
          waitType="debounce"
        />
        <Event
          event="clickToolbar"
          method="show"
          params={{}}
          pluginId="modalBankAccount"
          type="widget"
          waitMs="0"
          waitType="debounce"
        />
        <Event
          event="clickToolbar"
          method="setValue"
          params={{ map: { value: "new" } }}
          pluginId="bankaccount_mode"
          type="state"
          waitMs="0"
          waitType="debounce"
        />
      </ToolbarButton>
    </Table>
  </Body>
</ModalFrame>
