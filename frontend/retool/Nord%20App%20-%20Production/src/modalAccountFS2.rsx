<ModalFrame
  id="modalAccountFS2"
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
      id="modalTitle32"
      value="### Contas Contábeis"
      verticalAlign="center"
    />
    <Button
      id="modalCloseButton34"
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
        pluginId="modalAccountFS2"
        type="widget"
        waitMs="0"
        waitType="debounce"
      />
    </Button>
  </Header>
  <Body>
    <Table
      id="tableAccount4"
      actionsOverflowPosition={2}
      autoColumnWidth={true}
      cellSelection="none"
      clearChangesetOnSave={true}
      data="{{ product_service_get.data }}"
      defaultSelectedRow={{ mode: "index", indexType: "display", index: 0 }}
      emptyMessage="No rows found"
      enableSaveActions={true}
      rowHeight="medium"
      showFooter={true}
      showHeader={true}
      toolbarPosition="bottom"
    >
      <Column
        id="f465c"
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
        id="14770"
        alignment="left"
        format="string"
        groupAggregationMode="none"
        key="parent"
        label="Parent"
        placeholder="Enter value"
        position="center"
        size={53}
        summaryAggregationMode="none"
      />
      <Column
        id="2b143"
        alignment="right"
        editableOptions={{ showStepper: true }}
        format="decimal"
        formatOptions={{ showSeparators: true, notation: "standard" }}
        groupAggregationMode="sum"
        key="level"
        label="Level"
        placeholder="Enter value"
        position="center"
        size={45.796875}
        summaryAggregationMode="none"
      />
      <Column
        id="139f3"
        alignment="right"
        editableOptions={{ showStepper: true }}
        format="decimal"
        formatOptions={{ showSeparators: true, notation: "standard" }}
        groupAggregationMode="sum"
        key="account_code"
        label="Account code"
        placeholder="Enter value"
        position="center"
        size={94.6875}
        summaryAggregationMode="none"
      />
      <Column
        id="356c1"
        alignment="left"
        format="string"
        groupAggregationMode="none"
        key="name"
        label="Name"
        placeholder="Enter value"
        position="center"
        size={115.09375}
        summaryAggregationMode="none"
      />
      <Column
        id="384e8"
        alignment="left"
        format="string"
        groupAggregationMode="none"
        key="type"
        label="Type"
        placeholder="Enter value"
        position="center"
        size={43.921875}
        summaryAggregationMode="none"
      />
      <Column
        id="ec745"
        alignment="left"
        format="string"
        groupAggregationMode="none"
        key="path"
        label="Path"
        placeholder="Enter value"
        position="center"
        size={242.859375}
        summaryAggregationMode="none"
      />
      <Column
        id="e9702"
        alignment="right"
        editableOptions={{ showStepper: true }}
        format="decimal"
        formatOptions={{ showSeparators: true, notation: "standard" }}
        groupAggregationMode="sum"
        key="account_direction"
        label="Account direction"
        placeholder="Enter value"
        position="center"
        size={116.03125}
        summaryAggregationMode="none"
      />
      <Column
        id="1eeae"
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
        id="52670"
        alignment="left"
        editableOptions={{ showStepper: true }}
        format="json"
        formatOptions={{ showSeparators: true, notation: "standard" }}
        groupAggregationMode="sum"
        key="bank_account"
        label="Bank account"
        placeholder="Enter value"
        position="center"
        size={95.1875}
        summaryAggregationMode="none"
        valueOverride="{{ item.name }}"
      />
      <Column
        id="b2ada"
        alignment="left"
        format="date"
        groupAggregationMode="none"
        key="balance_date"
        label="Balance date"
        placeholder="Enter value"
        position="center"
        size={89.765625}
        summaryAggregationMode="none"
      />
      <Column
        id="f897a"
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
        id="acc23"
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
      <Column
        id="faee8"
        alignment="left"
        format="boolean"
        groupAggregationMode="none"
        key="is_active"
        label="Is active"
        placeholder="Enter value"
        position="center"
        size={62.90625}
        summaryAggregationMode="none"
      />
      <Action id="3fbf6" icon="bold/interface-edit-pencil" label="Edit">
        <Event
          event="clickAction"
          method="setValue"
          params={{ ordered: [{ value: "{{ currentSourceRow }}" }] }}
          pluginId="product_service_selected"
          type="state"
          waitMs="0"
          waitType="debounce"
        />
        <Event
          event="clickAction"
          method="show"
          params={{}}
          pluginId="modalProductService"
          type="widget"
          waitMs="0"
          waitType="debounce"
        />
        <Event
          event="clickAction"
          method="setValue"
          params={{ map: { value: "edit" } }}
          pluginId="product_service_mode"
          type="state"
          waitMs="0"
          waitType="debounce"
        />
      </Action>
      <Action id="a4440" icon="bold/interface-file-double" label="Duplicate">
        <Event
          event="clickAction"
          method="setValue"
          params={{ ordered: [{ value: "{{ currentSourceRow }}" }] }}
          pluginId="product_service_selected"
          type="state"
          waitMs="0"
          waitType="debounce"
        />
        <Event
          event="clickAction"
          method="setValue"
          params={{ map: { value: "new" } }}
          pluginId="product_service_mode"
          type="state"
          waitMs="0"
          waitType="debounce"
        />
        <Event
          event="clickAction"
          method="show"
          params={{}}
          pluginId="modalProductService"
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
          pluginId="tableAccount4"
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
          pluginId="tableAccount4"
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
          pluginId="product_service_selected"
          type="state"
          waitMs="0"
          waitType="debounce"
        />
        <Event
          event="clickToolbar"
          method="show"
          params={{}}
          pluginId="modalProductService"
          type="widget"
          waitMs="0"
          waitType="debounce"
        />
        <Event
          event="clickToolbar"
          method="setValue"
          params={{ map: { value: "new" } }}
          pluginId="product_service_mode"
          type="state"
          waitMs="0"
          waitType="debounce"
        />
      </ToolbarButton>
    </Table>
  </Body>
</ModalFrame>
