<ModalFrame
  id="modalBankAccountsFS2"
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
      id="modalTitle27"
      value="### Categoria Produto ou Serviço"
      verticalAlign="center"
    />
    <Button
      id="modalCloseButton29"
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
        pluginId="modalBankAccountsFS2"
        type="widget"
        waitMs="0"
        waitType="debounce"
      />
    </Button>
  </Header>
  <Body>
    <Table
      id="tableBankAccount9"
      actionsOverflowPosition={2}
      autoColumnWidth={true}
      cellSelection="none"
      clearChangesetOnSave={true}
      data="{{ product_service_categories_get.data }}"
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
        id="57030"
        alignment="right"
        editableOptions={{ showStepper: true }}
        format="decimal"
        formatOptions={{ showSeparators: true, notation: "standard" }}
        groupAggregationMode="sum"
        hidden="false"
        key="company"
        label="Company"
        placeholder="Enter value"
        position="center"
        size={69.84375}
        summaryAggregationMode="none"
      />
      <Column
        id="4583d"
        alignment="right"
        editableOptions={{ showStepper: true }}
        format="decimal"
        formatOptions={{ showSeparators: true, notation: "standard" }}
        groupAggregationMode="sum"
        key="level"
        label="Level"
        placeholder="Enter value"
        position="center"
        size={100}
        summaryAggregationMode="none"
      />
      <Column
        id="10f75"
        alignment="left"
        format="string"
        groupAggregationMode="none"
        key="parent"
        label="Parent"
        placeholder="Enter value"
        position="center"
        size={100}
        summaryAggregationMode="none"
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
        size={116.421875}
        summaryAggregationMode="none"
      />
      <Column
        id="2328b"
        alignment="left"
        format="boolean"
        groupAggregationMode="none"
        key="is_deleted"
        label="Is deleted"
        placeholder="Enter value"
        position="center"
        size={100}
        summaryAggregationMode="none"
      />
      <Action id="3fbf6" icon="bold/interface-edit-pencil" label="Edit">
        <Event
          event="clickAction"
          method="setValue"
          params={{ ordered: [{ value: "{{ currentSourceRow }}" }] }}
          pluginId="product_service_categories_selected"
          type="state"
          waitMs="0"
          waitType="debounce"
        />
        <Event
          event="clickAction"
          method="show"
          params={{}}
          pluginId="modalProductServiceCategory"
          type="widget"
          waitMs="0"
          waitType="debounce"
        />
        <Event
          event="clickAction"
          method="setValue"
          params={{ map: { value: "edit" } }}
          pluginId="product_service_categories_mode"
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
          pluginId="product_service_categories_selected"
          type="state"
          waitMs="0"
          waitType="debounce"
        />
        <Event
          event="clickAction"
          method="setValue"
          params={{ map: { value: "new" } }}
          pluginId="product_service_categories_mode"
          type="state"
          waitMs="0"
          waitType="debounce"
        />
        <Event
          event="clickAction"
          method="show"
          params={{}}
          pluginId="modalProductServiceCategory"
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
          pluginId="tableBankAccount9"
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
          pluginId="tableBankAccount9"
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
          pluginId="product_service_categories_selected"
          type="state"
          waitMs="0"
          waitType="debounce"
        />
        <Event
          event="clickToolbar"
          method="show"
          params={{}}
          pluginId="modalProductServiceCategory"
          type="widget"
          waitMs="0"
          waitType="debounce"
        />
        <Event
          event="clickToolbar"
          method="setValue"
          params={{ map: { value: "new" } }}
          pluginId="product_service_categories_mode"
          type="state"
          waitMs="0"
          waitType="debounce"
        />
      </ToolbarButton>
    </Table>
  </Body>
</ModalFrame>
