<Container
  id="group44"
  footerPadding="4px 12px"
  headerPadding="4px 12px"
  margin="0"
  padding="0"
  showBody={true}
  showBorder={false}
  style={{ map: { background: "rgba(255, 255, 255, 0)" } }}
>
  <View id="5de92" viewKey="View 1">
    <Container
      id="collapsibleContainer10"
      footerPadding="4px 12px"
      headerPadding="4px 12px"
      padding="12px"
      showBody={true}
      showHeader={true}
    >
      <Header>
        <Text
          id="collapsibleTitle10"
          tooltipText="Modelo: Entity
Usado para definir a estrutura organizacional da empresa (Modelo Company).
Permite criar relações de parentesco onde uma entidade pode pertencer à outra."
          value="##### Categoria Parceiro"
          verticalAlign="center"
        />
        <ToggleButton
          id="collapsibleToggle10"
          horizontalAlign="right"
          iconForFalse="bold/interface-arrows-button-down"
          iconForTrue="bold/interface-arrows-button-up"
          iconPosition="replace"
          styleVariant="outline"
          text="{{ self.value ? 'Hide' : 'Show' }}"
          value="{{ collapsibleContainer10.showBody }}"
        >
          <Event
            event="change"
            method="setShowBody"
            params={{ map: { showBody: "{{ self.value }}" } }}
            pluginId="collapsibleContainer10"
            type="widget"
            waitMs="0"
            waitType="debounce"
          />
        </ToggleButton>
      </Header>
      <View id="fd113" viewKey="View 1">
        <Table
          id="table40"
          actionsOverflowPosition={2}
          autoColumnWidth={true}
          cellSelection="none"
          clearChangesetOnSave={true}
          data="{{ business_partner_categories_get.data }}"
          defaultFilters={{
            0: {
              id: "80680",
              columnId: "fd4d0",
              operator: "isOneOf",
              value: "{{ multiselectEntidade.value }}",
              disabled: false,
            },
          }}
          defaultSelectedRow={{ mode: "index", indexType: "display", index: 0 }}
          emptyMessage="No rows found"
          enableSaveActions={true}
          linkedFilterId=""
          rowHeight="small"
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
            summaryAggregationMode="none"
          />
          <Column
            id="89e2d"
            alignment="right"
            editableOptions={{ showStepper: true }}
            format="decimal"
            formatOptions={{ showSeparators: true, notation: "standard" }}
            groupAggregationMode="sum"
            key="level"
            label="Level"
            placeholder="Enter value"
            position="center"
            summaryAggregationMode="none"
          />
          <Column
            id="3e356"
            alignment="left"
            format="string"
            groupAggregationMode="none"
            key="path"
            label="Path"
            placeholder="Enter value"
            position="center"
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
            summaryAggregationMode="none"
          />
          <Action id="3fbf6" icon="bold/interface-edit-pencil" label="Edit">
            <Event
              event="clickAction"
              method="setValue"
              params={{ ordered: [{ value: "{{ currentSourceRow }}" }] }}
              pluginId="business_partner_categories_selected"
              type="state"
              waitMs="0"
              waitType="debounce"
            />
            <Event
              event="clickAction"
              method="show"
              params={{}}
              pluginId="modalBusinessPartnerCategory"
              type="widget"
              waitMs="0"
              waitType="debounce"
            />
            <Event
              event="clickAction"
              method="setValue"
              params={{ map: { value: "edit" } }}
              pluginId="business_partner_categories_mode"
              type="state"
              waitMs="0"
              waitType="debounce"
            />
          </Action>
          <Action
            id="13ea9"
            icon="bold/interface-file-double"
            label="Duplicate"
          >
            <Event
              event="clickAction"
              method="setValue"
              params={{ map: { value: "{{  currentSourceRow}}" } }}
              pluginId="business_partner_categories_selected"
              type="state"
              waitMs="0"
              waitType="debounce"
            />
            <Event
              event="clickAction"
              method="setValue"
              params={{ map: { value: "new" } }}
              pluginId="business_partner_categories_mode"
              type="state"
              waitMs="0"
              waitType="debounce"
            />
            <Event
              event="clickAction"
              method="show"
              params={{}}
              pluginId="modalBusinessPartnerCategory"
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
              pluginId="table40"
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
              pluginId="table40"
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
              pluginId="business_partner_categories_selected"
              type="state"
              waitMs="0"
              waitType="debounce"
            />
            <Event
              event="clickToolbar"
              method="show"
              params={{}}
              pluginId="modalBusinessPartnerCategory"
              type="widget"
              waitMs="0"
              waitType="debounce"
            />
            <Event
              event="clickToolbar"
              method="setValue"
              params={{ map: { value: "new" } }}
              pluginId="business_partner_categories_mode"
              type="state"
              waitMs="0"
              waitType="debounce"
            />
          </ToolbarButton>
          <ToolbarButton
            id="49415"
            icon="bold/interface-arrows-expand-1"
            label="Fullscreen"
            type="custom"
          >
            <Event
              event="clickToolbar"
              method="show"
              params={{}}
              pluginId="modalEntidadeFC2"
              type="widget"
              waitMs="0"
              waitType="debounce"
            />
          </ToolbarButton>
        </Table>
      </View>
    </Container>
    <Container
      id="collapsibleContainer15"
      footerPadding="4px 12px"
      headerPadding="4px 12px"
      padding="12px"
      showBody={true}
      showHeader={true}
    >
      <Header>
        <Text
          id="collapsibleTitle15"
          value="##### Parceiro"
          verticalAlign="center"
        />
        <ToggleButton
          id="collapsibleToggle15"
          horizontalAlign="right"
          iconForFalse="bold/interface-arrows-button-down"
          iconForTrue="bold/interface-arrows-button-up"
          iconPosition="replace"
          styleVariant="outline"
          text="{{ self.value ? 'Hide' : 'Show' }}"
          value="{{ collapsibleContainer15.showBody }}"
        >
          <Event
            event="change"
            method="setShowBody"
            params={{ map: { showBody: "{{ self.value }}" } }}
            pluginId="collapsibleContainer15"
            type="widget"
            waitMs="0"
            waitType="debounce"
          />
        </ToggleButton>
      </Header>
      <View id="fd113" viewKey="View 1">
        <Table
          id="tableBusinessPartner"
          actionsOverflowPosition={2}
          cellSelection="none"
          clearChangesetOnSave={true}
          data="{{ business_partner_get.data }}"
          defaultSelectedRow={{ mode: "index", indexType: "display", index: 0 }}
          emptyMessage="No rows found"
          enableSaveActions={true}
          rowHeight="small"
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
            size={41.765625}
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
            size={178.90625}
            summaryAggregationMode="none"
          />
          <Column
            id="2896f"
            alignment="left"
            format="string"
            groupAggregationMode="none"
            key="partner_type"
            label="Partner type"
            placeholder="Enter value"
            position="center"
            size={104.8125}
            summaryAggregationMode="none"
          />
          <Column
            id="fa2bb"
            alignment="left"
            format="string"
            groupAggregationMode="none"
            key="category"
            label="Category"
            placeholder="Enter value"
            position="center"
            size={111.59375}
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
            id="eb25c"
            alignment="right"
            editableOptions={{ showStepper: true }}
            format="decimal"
            formatOptions={{ showSeparators: true, notation: "standard" }}
            groupAggregationMode="sum"
            key="identifier"
            label="Identifier"
            placeholder="Enter value"
            position="center"
            size={66.453125}
            summaryAggregationMode="none"
          />
          <Column
            id="406fa"
            alignment="left"
            format="string"
            groupAggregationMode="none"
            key="email"
            label="Email"
            placeholder="Enter value"
            position="center"
            size={46.046875}
            summaryAggregationMode="none"
          />
          <Column
            id="4bada"
            alignment="left"
            format="string"
            groupAggregationMode="none"
            key="phone"
            label="Phone"
            placeholder="Enter value"
            position="center"
            size={51.875}
            summaryAggregationMode="none"
          />
          <Column
            id="ad8fe"
            alignment="left"
            format="string"
            groupAggregationMode="none"
            key="payment_terms"
            label="Payment terms"
            placeholder="Enter value"
            position="center"
            size={101.4375}
            summaryAggregationMode="none"
          />
          <Column
            id="96960"
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
          <Column
            id="78f5e"
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
            size={100}
            summaryAggregationMode="none"
          />
          <Column
            id="81530"
            alignment="right"
            editableOptions={{ showStepper: true }}
            format="decimal"
            formatOptions={{ showSeparators: true, notation: "standard" }}
            groupAggregationMode="sum"
            key="currency"
            label="Currency"
            placeholder="Enter value"
            position="center"
            size={67.8125}
            summaryAggregationMode="none"
          />
          <Column
            id="fe93c"
            alignment="left"
            format="boolean"
            groupAggregationMode="none"
            key="is_deleted"
            label="Is deleted"
            placeholder="Enter value"
            position="center"
            size={71.8125}
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
          <Action
            id="9e6d2"
            icon="bold/interface-file-double"
            label="Duplicate"
          >
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
              pluginId="tableBusinessPartner"
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
              pluginId="tableBusinessPartner"
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
          <ToolbarButton
            id="b3d42"
            icon="bold/interface-arrows-expand-1"
            label="Fullscreen"
            type="custom"
          >
            <Event
              event="clickToolbar"
              method="show"
              params={{}}
              pluginId="modalBusinessPartnerFS2"
              type="widget"
              waitMs="0"
              waitType="debounce"
            />
          </ToolbarButton>
        </Table>
      </View>
    </Container>
    <Container
      id="collapsibleContainer11"
      footerPadding="4px 12px"
      headerPadding="4px 12px"
      padding="12px"
      showBody={true}
      showHeader={true}
    >
      <Header>
        <Text
          id="collapsibleTitle11"
          value="##### Categoria Produto ou Serviço"
          verticalAlign="center"
        />
        <ToggleButton
          id="collapsibleToggle11"
          horizontalAlign="right"
          iconForFalse="bold/interface-arrows-button-down"
          iconForTrue="bold/interface-arrows-button-up"
          iconPosition="replace"
          styleVariant="outline"
          text="{{ self.value ? 'Hide' : 'Show' }}"
          value="{{ collapsibleContainer11.showBody }}"
        >
          <Event
            event="change"
            method="setShowBody"
            params={{ map: { showBody: "{{ self.value }}" } }}
            pluginId="collapsibleContainer11"
            type="widget"
            waitMs="0"
            waitType="debounce"
          />
        </ToggleButton>
      </Header>
      <View id="fd113" viewKey="View 1">
        <Table
          id="tableProductServiceCategory"
          actionsOverflowPosition={2}
          autoColumnWidth={true}
          cellSelection="none"
          clearChangesetOnSave={true}
          data="{{ product_service_categories_get.data }}"
          defaultSelectedRow={{ mode: "index", indexType: "display", index: 0 }}
          emptyMessage="No rows found"
          enableSaveActions={true}
          rowHeight="small"
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
            summaryAggregationMode="none"
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
            summaryAggregationMode="none"
          />
          <Column
            id="99fb2"
            alignment="right"
            editableOptions={{ showStepper: true }}
            format="decimal"
            formatOptions={{ showSeparators: true, notation: "standard" }}
            groupAggregationMode="sum"
            key="level"
            label="Level"
            placeholder="Enter value"
            position="center"
            summaryAggregationMode="none"
          />
          <Column
            id="28193"
            alignment="left"
            format="string"
            groupAggregationMode="none"
            key="parent"
            label="Parent"
            placeholder="Enter value"
            position="center"
            summaryAggregationMode="none"
          />
          <Column
            id="8d3fa"
            alignment="left"
            format="boolean"
            groupAggregationMode="none"
            key="is_deleted"
            label="Is deleted"
            placeholder="Enter value"
            position="center"
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
          <Action
            id="9e6d2"
            icon="bold/interface-file-double"
            label="Duplicate"
          >
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
              pluginId="tableProductServiceCategory"
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
              pluginId="tableProductServiceCategory"
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
          <ToolbarButton
            id="b3d42"
            icon="bold/interface-arrows-expand-1"
            label="Fullscreen"
            type="custom"
          >
            <Event
              event="clickToolbar"
              method="show"
              params={{}}
              pluginId="modalBankAccountsFS2"
              type="widget"
              waitMs="0"
              waitType="debounce"
            />
          </ToolbarButton>
        </Table>
      </View>
    </Container>
    <Container
      id="collapsibleContainer12"
      footerPadding="4px 12px"
      headerPadding="4px 12px"
      padding="12px"
      showBody={true}
      showHeader={true}
    >
      <Header>
        <Text
          id="collapsibleTitle12"
          value="##### Produto ou Serviço"
          verticalAlign="center"
        />
        <ToggleButton
          id="collapsibleToggle12"
          horizontalAlign="right"
          iconForFalse="bold/interface-arrows-button-down"
          iconForTrue="bold/interface-arrows-button-up"
          iconPosition="replace"
          styleVariant="outline"
          text="{{ self.value ? 'Hide' : 'Show' }}"
          value="{{ collapsibleContainer12.showBody }}"
        >
          <Event
            event="change"
            method="setShowBody"
            params={{ map: { showBody: "{{ self.value }}" } }}
            pluginId="collapsibleContainer12"
            type="widget"
            waitMs="0"
            waitType="debounce"
          />
        </ToggleButton>
      </Header>
      <View id="fd113" viewKey="View 1">
        <Table
          id="tableProductService"
          actionsOverflowPosition={2}
          autoColumnWidth={true}
          cellSelection="none"
          clearChangesetOnSave={true}
          data="{{ product_service_get.data }}"
          defaultSelectedRow={{ mode: "index", indexType: "display", index: 0 }}
          emptyMessage="No rows found"
          enableSaveActions={true}
          rowHeight="small"
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
            summaryAggregationMode="none"
          />
          <Column
            id="7ddab"
            alignment="right"
            editableOptions={{ showStepper: true }}
            format="decimal"
            formatOptions={{ showSeparators: true, notation: "standard" }}
            groupAggregationMode="sum"
            key="company"
            label="Company"
            placeholder="Enter value"
            position="center"
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
            summaryAggregationMode="none"
          />
          <Column
            id="f28b6"
            alignment="left"
            format="string"
            groupAggregationMode="none"
            key="item_type"
            label="Item type"
            placeholder="Enter value"
            position="center"
            summaryAggregationMode="none"
          />
          <Column
            id="3c05f"
            alignment="right"
            editableOptions={{ showStepper: true }}
            format="decimal"
            formatOptions={{ showSeparators: true, notation: "standard" }}
            groupAggregationMode="sum"
            key="category"
            label="Category"
            placeholder="Enter value"
            position="center"
            summaryAggregationMode="none"
          />
          <Column
            id="564d0"
            alignment="right"
            editableOptions={{ showStepper: true }}
            format="decimal"
            formatOptions={{ showSeparators: true, notation: "standard" }}
            groupAggregationMode="sum"
            key="code"
            label="Code"
            placeholder="Enter value"
            position="center"
            summaryAggregationMode="none"
          />
          <Column
            id="88d32"
            alignment="left"
            format="string"
            groupAggregationMode="none"
            key="description"
            label="Description"
            placeholder="Enter value"
            position="center"
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
            summaryAggregationMode="none"
            valueOverride="{{ item.code }}"
          />
          <Column
            id="df826"
            alignment="right"
            editableOptions={{ showStepper: true }}
            format="decimal"
            formatOptions={{ showSeparators: true, notation: "standard" }}
            groupAggregationMode="sum"
            key="price"
            label="Price"
            placeholder="Enter value"
            position="center"
            summaryAggregationMode="none"
          />
          <Column
            id="b39e4"
            alignment="left"
            format="string"
            groupAggregationMode="none"
            key="cost"
            label="Cost"
            placeholder="Enter value"
            position="center"
            summaryAggregationMode="none"
          />
          <Column
            id="6ce96"
            alignment="left"
            format="string"
            groupAggregationMode="none"
            key="tax_code"
            label="Tax code"
            placeholder="Enter value"
            position="center"
            summaryAggregationMode="none"
          />
          <Column
            id="f1e61"
            alignment="left"
            format="boolean"
            groupAggregationMode="none"
            key="track_inventory"
            label="Track inventory"
            placeholder="Enter value"
            position="center"
            summaryAggregationMode="none"
          />
          <Column
            id="e119c"
            alignment="right"
            editableOptions={{ showStepper: true }}
            format="decimal"
            formatOptions={{ showSeparators: true, notation: "standard" }}
            groupAggregationMode="sum"
            key="stock_quantity"
            label="Stock quantity"
            placeholder="Enter value"
            position="center"
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
            summaryAggregationMode="none"
          />
          <Column
            id="b22c2"
            alignment="left"
            format="boolean"
            groupAggregationMode="none"
            key="is_deleted"
            label="Is deleted"
            placeholder="Enter value"
            position="center"
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
          <Action
            id="a4440"
            icon="bold/interface-file-double"
            label="Duplicate"
          >
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
              pluginId="tableProductService"
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
              pluginId="tableProductService"
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
          <ToolbarButton
            id="2672b"
            icon="bold/interface-arrows-expand-1"
            label="Fullscreen"
            type="custom"
          >
            <Event
              event="clickToolbar"
              method="show"
              params={{}}
              pluginId="modalAccountFS2"
              type="widget"
              waitMs="0"
              waitType="debounce"
            />
          </ToolbarButton>
        </Table>
      </View>
    </Container>
    <Container
      id="collapsibleContainer13"
      footerPadding="4px 12px"
      headerPadding="4px 12px"
      padding="12px"
      showBody={true}
      showHeader={true}
    >
      <Header>
        <Text
          id="collapsibleTitle13"
          value="##### Contratos"
          verticalAlign="center"
        />
        <ToggleButton
          id="collapsibleToggle13"
          horizontalAlign="right"
          iconForFalse="bold/interface-arrows-button-down"
          iconForTrue="bold/interface-arrows-button-up"
          iconPosition="replace"
          styleVariant="outline"
          text="{{ self.value ? 'Hide' : 'Show' }}"
          value="{{ collapsibleContainer13.showBody }}"
        >
          <Event
            event="change"
            method="setShowBody"
            params={{ map: { showBody: "{{ self.value }}" } }}
            pluginId="collapsibleContainer13"
            type="widget"
            waitMs="0"
            waitType="debounce"
          />
        </ToggleButton>
      </Header>
      <View id="fd113" viewKey="View 1">
        <Table
          id="tableContract"
          actionsOverflowPosition={2}
          autoColumnWidth={true}
          cellSelection="none"
          clearChangesetOnSave={true}
          data="{{ contract_get.data }}"
          defaultSelectedRow={{ mode: "index", indexType: "display", index: 0 }}
          emptyMessage="No rows found"
          enableSaveActions={true}
          rowHeight="small"
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
            summaryAggregationMode="none"
          />
          <Column
            id="fa4c4"
            alignment="right"
            editableOptions={{ showStepper: true }}
            format="decimal"
            formatOptions={{ showSeparators: true, notation: "standard" }}
            groupAggregationMode="sum"
            key="company"
            label="Company"
            placeholder="Enter value"
            position="center"
            summaryAggregationMode="none"
          />
          <Column
            id="54a8e"
            alignment="right"
            editableOptions={{ showStepper: true }}
            format="decimal"
            formatOptions={{ showSeparators: true, notation: "standard" }}
            groupAggregationMode="sum"
            key="partner"
            label="Partner"
            placeholder="Enter value"
            position="center"
            summaryAggregationMode="none"
          />
          <Column
            id="60ff3"
            alignment="right"
            editableOptions={{ showStepper: true }}
            format="decimal"
            formatOptions={{ showSeparators: true, notation: "standard" }}
            groupAggregationMode="sum"
            key="contract_number"
            label="Contract number"
            placeholder="Enter value"
            position="center"
            summaryAggregationMode="none"
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
            summaryAggregationMode="none"
          />
          <Column
            id="728af"
            alignment="left"
            format="date"
            groupAggregationMode="none"
            key="start_date"
            label="Start date"
            placeholder="Enter value"
            position="center"
            summaryAggregationMode="none"
          />
          <Column
            id="5a5db"
            alignment="left"
            format="string"
            groupAggregationMode="none"
            key="end_date"
            label="End date"
            placeholder="Enter value"
            position="center"
            summaryAggregationMode="none"
          />
          <Column
            id="4ba75"
            alignment="left"
            format="string"
            groupAggregationMode="none"
            key="recurrence_rule"
            label="Recurrence rule"
            placeholder="Enter value"
            position="center"
            summaryAggregationMode="none"
          />
          <Column
            id="a9fd7"
            alignment="left"
            format="string"
            groupAggregationMode="none"
            key="adjustment_index"
            label="Adjustment index"
            placeholder="Enter value"
            position="center"
            summaryAggregationMode="none"
          />
          <Column
            id="b9595"
            alignment="right"
            editableOptions={{ showStepper: true }}
            format="decimal"
            formatOptions={{ showSeparators: true, notation: "standard" }}
            groupAggregationMode="sum"
            key="base_value"
            label="Base value"
            placeholder="Enter value"
            position="center"
            summaryAggregationMode="none"
          />
          <Column
            id="88137"
            alignment="left"
            format="string"
            groupAggregationMode="none"
            key="base_index_date"
            label="Base index date"
            placeholder="Enter value"
            position="center"
            summaryAggregationMode="none"
          />
          <Column
            id="0457b"
            alignment="left"
            format="string"
            groupAggregationMode="none"
            key="adjustment_frequency"
            label="Adjustment frequency"
            placeholder="Enter value"
            position="center"
            summaryAggregationMode="none"
          />
          <Column
            id="a9a75"
            alignment="left"
            format="string"
            groupAggregationMode="none"
            key="adjustment_cap"
            label="Adjustment cap"
            placeholder="Enter value"
            position="center"
            summaryAggregationMode="none"
          />
          <Column
            id="c62fa"
            alignment="left"
            format="boolean"
            groupAggregationMode="none"
            key="is_active"
            label="Is active"
            placeholder="Enter value"
            position="center"
            summaryAggregationMode="none"
          />
          <Action id="3fbf6" icon="bold/interface-edit-pencil" label="Edit">
            <Event
              event="clickAction"
              method="setValue"
              params={{ ordered: [{ value: "{{ currentSourceRow }}" }] }}
              pluginId="contract_selected"
              type="state"
              waitMs="0"
              waitType="debounce"
            />
            <Event
              event="clickAction"
              method="setValue"
              params={{ map: { value: "edit" } }}
              pluginId="contract_mode"
              type="state"
              waitMs="0"
              waitType="debounce"
            />
            <Event
              event="clickAction"
              method="show"
              params={{}}
              pluginId="modalContract"
              type="widget"
              waitMs="0"
              waitType="debounce"
            />
          </Action>
          <Action
            id="4255e"
            icon="bold/interface-file-double"
            label="Duplicate"
          >
            <Event
              event="clickAction"
              method="setValue"
              params={{ map: { value: "{{  currentSourceRow}}" } }}
              pluginId="contract_selected"
              type="state"
              waitMs="0"
              waitType="debounce"
            />
            <Event
              event="clickAction"
              method="setValue"
              params={{ map: { value: "new" } }}
              pluginId="contract_mode"
              type="state"
              waitMs="0"
              waitType="debounce"
            />
            <Event
              event="clickAction"
              method="show"
              params={{}}
              pluginId="modalContract"
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
              pluginId="tableContract"
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
              pluginId="tableContract"
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
              pluginId="contract_selected"
              type="state"
              waitMs="0"
              waitType="debounce"
            />
            <Event
              event="clickToolbar"
              method="setValue"
              params={{ map: { value: "new" } }}
              pluginId="contract_mode"
              type="state"
              waitMs="0"
              waitType="debounce"
            />
            <Event
              event="clickToolbar"
              method="show"
              params={{}}
              pluginId="modalContract"
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
      </View>
    </Container>
  </View>
</Container>
