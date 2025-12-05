<ModalFrame
  id="modalFrame6"
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
      id="modalTitle20"
      value="### Centros de Custo"
      verticalAlign="center"
    />
    <Button
      id="modalCloseButton22"
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
        pluginId="modalFrame6"
        type="widget"
        waitMs="0"
        waitType="debounce"
      />
    </Button>
  </Header>
  <Body>
    <Table
      id="tableCostCenter2"
      actionsOverflowPosition={2}
      autoColumnWidth={true}
      cellSelection="none"
      clearChangesetOnSave={true}
      data="{{ costcenter_get.data }}"
      defaultSelectedRow={{ mode: "index", indexType: "display", index: 0 }}
      emptyMessage="No rows found"
      enableSaveActions={true}
      rowHeight="medium"
      showFooter={true}
      showHeader={true}
      toolbarPosition="bottom"
    >
      <Column
        id="4885a"
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
        id="8aa16"
        alignment="left"
        format="string"
        groupAggregationMode="none"
        key="name"
        label="Name"
        placeholder="Enter value"
        position="center"
        size={118.0625}
        summaryAggregationMode="none"
      />
      <Column
        id="1955a"
        alignment="left"
        format="tag"
        formatOptions={{ automaticColors: true }}
        groupAggregationMode="none"
        key="center_type"
        label="Center type"
        placeholder="Select option"
        position="center"
        size={83.203125}
        summaryAggregationMode="none"
        valueOverride="{{ _.startCase(item) }}"
      />
      <Column
        id="94215"
        alignment="left"
        format="string"
        groupAggregationMode="none"
        key="description"
        label="Description"
        placeholder="Enter value"
        position="center"
        size={186.875}
        summaryAggregationMode="none"
      />
      <Column
        id="fdb9e"
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
        id="caf90"
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
        id="c597a"
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
          pluginId="costcenter_selected"
          type="state"
          waitMs="0"
          waitType="debounce"
        />
        <Event
          event="clickAction"
          method="setValue"
          params={{ map: { value: "edit" } }}
          pluginId="costcenter_mode"
          type="state"
          waitMs="0"
          waitType="debounce"
        />
        <Event
          event="clickAction"
          method="show"
          params={{}}
          pluginId="modalCostCenter"
          type="widget"
          waitMs="0"
          waitType="debounce"
        />
      </Action>
      <Action id="4255e" icon="bold/interface-file-double" label="Duplicate">
        <Event
          event="clickAction"
          method="setValue"
          params={{ map: { value: "{{  currentSourceRow}}" } }}
          pluginId="costcenter_selected"
          type="state"
          waitMs="0"
          waitType="debounce"
        />
        <Event
          event="clickAction"
          method="setValue"
          params={{ map: { value: "new" } }}
          pluginId="costcenter_mode"
          type="state"
          waitMs="0"
          waitType="debounce"
        />
        <Event
          event="clickAction"
          method="show"
          params={{}}
          pluginId="modalCostCenter"
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
          pluginId="tableCostCenter2"
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
          pluginId="tableCostCenter2"
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
          pluginId="costcenter_selected"
          type="state"
          waitMs="0"
          waitType="debounce"
        />
        <Event
          event="clickToolbar"
          method="setValue"
          params={{ map: { value: "new" } }}
          pluginId="costcenter_mode"
          type="state"
          waitMs="0"
          waitType="debounce"
        />
        <Event
          event="clickToolbar"
          method="show"
          params={{}}
          pluginId="modalCostCenter"
          type="widget"
          waitMs="0"
          waitType="debounce"
        />
      </ToolbarButton>
      <ToolbarButton
        id="a4c1b"
        icon="bold/interface-arrows-expand-1"
        label="Fullscreen"
        type="custom"
      />
    </Table>
  </Body>
</ModalFrame>
