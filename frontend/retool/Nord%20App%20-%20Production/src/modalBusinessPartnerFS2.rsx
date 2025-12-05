<ModalFrame
  id="modalBusinessPartnerFS2"
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
    <Text id="modalTitle31" value="#### Parceiros" verticalAlign="center" />
    <Button
      id="modalCloseButton33"
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
        pluginId="modalBusinessPartnerFS2"
        type="widget"
        waitMs="0"
        waitType="debounce"
      />
    </Button>
  </Header>
  <Body>
    <Table
      id="tableBusinessPartner8"
      actionsOverflowPosition={2}
      autoColumnWidth={true}
      cellSelection="none"
      clearChangesetOnSave={true}
      data="{{ business_partner_get.data }}"
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
        id="9ba5c"
        alignment="left"
        format="string"
        groupAggregationMode="none"
        key="name"
        label="Name"
        placeholder="Enter value"
        position="center"
        size={141.90625}
        summaryAggregationMode="none"
      />
      <Column
        id="0b9a0"
        alignment="left"
        format="tag"
        formatOptions={{ automaticColors: true }}
        groupAggregationMode="none"
        key="partner_type"
        label="Partner type"
        placeholder="Select option"
        position="center"
        size={100}
        summaryAggregationMode="none"
        valueOverride="{{ _.startCase(item) }}"
      />
      <Column
        id="bca53"
        alignment="left"
        format="string"
        groupAggregationMode="none"
        key="category"
        label="Category"
        placeholder="Enter value"
        position="center"
        size={100}
        summaryAggregationMode="none"
      />
      <Column
        id="5ad73"
        alignment="left"
        format="tag"
        formatOptions={{ automaticColors: true }}
        groupAggregationMode="none"
        key="country"
        label="Country"
        placeholder="Select option"
        position="center"
        size={63.171875}
        summaryAggregationMode="none"
        valueOverride="{{ _.startCase(item) }}"
      />
      <Column
        id="0b4c6"
        alignment="right"
        editableOptions={{ showStepper: true }}
        format="decimal"
        formatOptions={{ showSeparators: true, notation: "standard" }}
        groupAggregationMode="sum"
        key="identifier"
        label="Identifier"
        placeholder="Enter value"
        position="center"
        size={100}
        summaryAggregationMode="none"
      />
      <Column
        id="d486a"
        alignment="left"
        format="string"
        groupAggregationMode="none"
        key="email"
        label="Email"
        placeholder="Enter value"
        position="center"
        size={100}
        summaryAggregationMode="none"
      />
      <Column
        id="6bc62"
        alignment="left"
        format="string"
        groupAggregationMode="none"
        key="phone"
        label="Phone"
        placeholder="Enter value"
        position="center"
        size={100}
        summaryAggregationMode="none"
      />
      <Column
        id="3ac15"
        alignment="left"
        format="string"
        groupAggregationMode="none"
        key="payment_terms"
        label="Payment terms"
        placeholder="Enter value"
        position="center"
        size={100}
        summaryAggregationMode="none"
      />
      <Column
        id="2c6bf"
        alignment="left"
        format="boolean"
        groupAggregationMode="none"
        key="is_active"
        label="Is active"
        placeholder="Enter value"
        position="center"
        size={100}
        summaryAggregationMode="none"
      />
      <Column
        id="f49f8"
        alignment="right"
        editableOptions={{ showStepper: true }}
        format="decimal"
        formatOptions={{ showSeparators: true, notation: "standard" }}
        groupAggregationMode="sum"
        key="currency"
        label="Currency"
        placeholder="Enter value"
        position="center"
        size={100}
        summaryAggregationMode="none"
      />
      <Column
        id="c1a85"
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
          pluginId="business_partner_selected"
          type="state"
          waitMs="0"
          waitType="debounce"
        />
        <Event
          event="clickAction"
          method="show"
          params={{}}
          pluginId="modalBusinessPartner"
          type="widget"
          waitMs="0"
          waitType="debounce"
        />
        <Event
          event="clickAction"
          method="setValue"
          params={{ map: { value: "edit" } }}
          pluginId="business_partner_mode"
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
          pluginId="business_partner_selected"
          type="state"
          waitMs="0"
          waitType="debounce"
        />
        <Event
          event="clickAction"
          method="setValue"
          params={{ map: { value: "new" } }}
          pluginId="business_partner_mode"
          type="state"
          waitMs="0"
          waitType="debounce"
        />
        <Event
          event="clickAction"
          method="show"
          params={{}}
          pluginId="modalBusinessPartner"
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
          pluginId="tableBusinessPartner8"
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
          pluginId="tableBusinessPartner8"
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
          pluginId="business_partner_selected"
          type="state"
          waitMs="0"
          waitType="debounce"
        />
        <Event
          event="clickToolbar"
          method="show"
          params={{}}
          pluginId="modalBusinessPartner"
          type="widget"
          waitMs="0"
          waitType="debounce"
        />
        <Event
          event="clickToolbar"
          method="setValue"
          params={{ map: { value: "new" } }}
          pluginId="business_partner_mode"
          type="state"
          waitMs="0"
          waitType="debounce"
        />
      </ToolbarButton>
    </Table>
  </Body>
</ModalFrame>
