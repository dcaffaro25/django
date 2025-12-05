<Container
  id="group40"
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
      id="collapsibleContainer4"
      footerPadding="4px 12px"
      headerPadding="4px 12px"
      padding="12px"
      showBody={true}
      showHeader={true}
    >
      <Header>
        <Text
          id="collapsibleTitle4"
          tooltipText="Modelo: Entity
Usado para definir a estrutura organizacional da empresa (Modelo Company).
Permite criar relações de parentesco onde uma entidade pode pertencer à outra."
          value="##### Estrutura Organizacional"
          verticalAlign="center"
        />
        <ToggleButton
          id="collapsibleToggle4"
          horizontalAlign="right"
          iconForFalse="bold/interface-arrows-button-down"
          iconForTrue="bold/interface-arrows-button-up"
          iconPosition="replace"
          styleVariant="outline"
          text="{{ self.value ? 'Hide' : 'Show' }}"
          value="{{ collapsibleContainer4.showBody }}"
        >
          <Event
            event="change"
            method="setShowBody"
            params={{ map: { showBody: "{{ self.value }}" } }}
            pluginId="collapsibleContainer4"
            type="widget"
            waitMs="0"
            waitType="debounce"
          />
        </ToggleButton>
      </Header>
      <View id="fd113" viewKey="View 1">
        <Table
          id="table36"
          actionsOverflowPosition={2}
          autoColumnWidth={true}
          cellSelection="none"
          clearChangesetOnSave={true}
          data="{{ entities_get.data }}"
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
            id="47f91"
            alignment="right"
            editableOptions={{ showStepper: true }}
            format="decimal"
            formatOptions={{ showSeparators: true, notation: "standard" }}
            groupAggregationMode="sum"
            key="parent_id"
            label="Parent ID"
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
            id="c5ade"
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
            id="87573"
            alignment="left"
            format="boolean"
            groupAggregationMode="none"
            key="inherit_accounts"
            label="Inherit accounts"
            placeholder="Enter value"
            position="center"
            summaryAggregationMode="none"
          />
          <Column
            id="139f7"
            alignment="left"
            format="boolean"
            groupAggregationMode="none"
            key="inherit_cost_centers"
            label="Inherit cost centers"
            placeholder="Enter value"
            position="center"
            summaryAggregationMode="none"
          />
          <Action id="3fbf6" icon="bold/interface-edit-pencil" label="Edit">
            <Event
              event="clickAction"
              method="setValue"
              params={{ ordered: [{ value: "{{ currentSourceRow }}" }] }}
              pluginId="entity_selected"
              type="state"
              waitMs="0"
              waitType="debounce"
            />
            <Event
              event="clickAction"
              method="show"
              params={{}}
              pluginId="modalEntidade"
              type="widget"
              waitMs="0"
              waitType="debounce"
            />
            <Event
              event="clickAction"
              method="setValue"
              params={{ map: { value: "edit" } }}
              pluginId="entity_mode"
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
              pluginId="entity_selected"
              type="state"
              waitMs="0"
              waitType="debounce"
            />
            <Event
              event="clickAction"
              method="setValue"
              params={{ map: { value: "new" } }}
              pluginId="entity_mode"
              type="state"
              waitMs="0"
              waitType="debounce"
            />
            <Event
              event="clickAction"
              method="show"
              params={{}}
              pluginId="modalEntidade"
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
              pluginId="table36"
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
              pluginId="table36"
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
              pluginId="entity_selected"
              type="state"
              waitMs="0"
              waitType="debounce"
            />
            <Event
              event="clickToolbar"
              method="show"
              params={{}}
              pluginId="modalEntidade"
              type="widget"
              waitMs="0"
              waitType="debounce"
            />
            <Event
              event="clickToolbar"
              method="setValue"
              params={{ map: { value: "new" } }}
              pluginId="entity_mode"
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
              pluginId="modalEntidadeFC"
              type="widget"
              waitMs="0"
              waitType="debounce"
            />
          </ToolbarButton>
        </Table>
      </View>
    </Container>
    <Container
      id="collapsibleContainer9"
      footerPadding="4px 12px"
      headerPadding="4px 12px"
      padding="12px"
      showBody={true}
      showHeader={true}
    >
      <Header>
        <Text
          id="collapsibleTitle9"
          value="##### Bancos"
          verticalAlign="center"
        />
        <ToggleButton
          id="collapsibleToggle9"
          horizontalAlign="right"
          iconForFalse="bold/interface-arrows-button-down"
          iconForTrue="bold/interface-arrows-button-up"
          iconPosition="replace"
          styleVariant="outline"
          text="{{ self.value ? 'Hide' : 'Show' }}"
          value="{{ collapsibleContainer9.showBody }}"
        >
          <Event
            event="change"
            method="setShowBody"
            params={{ map: { showBody: "{{ self.value }}" } }}
            pluginId="collapsibleContainer9"
            type="widget"
            waitMs="0"
            waitType="debounce"
          />
        </ToggleButton>
      </Header>
      <View id="fd113" viewKey="View 1">
        <Table
          id="tableBankAccount3"
          actionsOverflowPosition={2}
          autoColumnWidth={true}
          cellSelection="none"
          clearChangesetOnSave={true}
          data="{{ bank_get.data }}"
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
            size={0}
            summaryAggregationMode="none"
          />
          <Column
            id="ead14"
            alignment="right"
            editableOptions={{ showStepper: true }}
            format="decimal"
            formatOptions={{ showSeparators: true, notation: "standard" }}
            groupAggregationMode="sum"
            key="bank_code"
            label="Bank code"
            placeholder="Enter value"
            position="center"
            size={0}
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
            size={0}
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
            size={0}
            summaryAggregationMode="none"
            valueOverride="{{ _.startCase(item) }}"
          />
          <Action id="3fbf6" icon="bold/interface-edit-pencil" label="Edit">
            <Event
              event="clickAction"
              method="setValue"
              params={{ ordered: [{ value: "{{ currentSourceRow }}" }] }}
              pluginId="bank_selected"
              type="state"
              waitMs="0"
              waitType="debounce"
            />
            <Event
              event="clickAction"
              method="show"
              params={{}}
              pluginId="modalBank"
              type="widget"
              waitMs="0"
              waitType="debounce"
            />
            <Event
              event="clickAction"
              method="setValue"
              params={{ map: { value: "edit" } }}
              pluginId="bank_mode"
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
              pluginId="bank_selected"
              type="state"
              waitMs="0"
              waitType="debounce"
            />
            <Event
              event="clickAction"
              method="setValue"
              params={{ map: { value: "new" } }}
              pluginId="bank_mode"
              type="state"
              waitMs="0"
              waitType="debounce"
            />
            <Event
              event="clickAction"
              method="show"
              params={{}}
              pluginId="modalBank"
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
              pluginId="tableBankAccount3"
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
              pluginId="tableBankAccount3"
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
              pluginId="bank_selected"
              type="state"
              waitMs="0"
              waitType="debounce"
            />
            <Event
              event="clickToolbar"
              method="show"
              params={{}}
              pluginId="modalBank"
              type="widget"
              waitMs="0"
              waitType="debounce"
            />
            <Event
              event="clickToolbar"
              method="setValue"
              params={{ map: { value: "new" } }}
              pluginId="bank_mode"
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
              pluginId="modalBankFS"
              type="widget"
              waitMs="0"
              waitType="debounce"
            />
          </ToolbarButton>
        </Table>
      </View>
    </Container>
    <Container
      id="collapsibleContainer5"
      footerPadding="4px 12px"
      headerPadding="4px 12px"
      padding="12px"
      showBody={true}
      showHeader={true}
    >
      <Header>
        <Text
          id="collapsibleTitle5"
          value="##### Contas Bancárias"
          verticalAlign="center"
        />
        <ToggleButton
          id="collapsibleToggle5"
          horizontalAlign="right"
          iconForFalse="bold/interface-arrows-button-down"
          iconForTrue="bold/interface-arrows-button-up"
          iconPosition="replace"
          styleVariant="outline"
          text="{{ self.value ? 'Hide' : 'Show' }}"
          value="{{ collapsibleContainer5.showBody }}"
        >
          <Event
            event="change"
            method="setShowBody"
            params={{ map: { showBody: "{{ self.value }}" } }}
            pluginId="collapsibleContainer5"
            type="widget"
            waitMs="0"
            waitType="debounce"
          />
        </ToggleButton>
      </Header>
      <View id="fd113" viewKey="View 1">
        <Table
          id="tableBankAccount"
          actionsOverflowPosition={2}
          cellSelection="none"
          clearChangesetOnSave={true}
          data="{{ bankaccount_get.data }}"
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
            size={56}
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
            size={134}
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
            size={109}
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
            size={100}
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
            size={77}
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
            size={152}
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
            size={109}
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
            size={153}
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
            size={114}
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
            size={72}
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
            size={129}
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
          <Action
            id="9e6d2"
            icon="bold/interface-file-double"
            label="Duplicate"
          >
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
              pluginId="tableBankAccount"
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
              pluginId="tableBankAccount"
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
              pluginId="modalBankAccountsFS"
              type="widget"
              waitMs="0"
              waitType="debounce"
            />
          </ToolbarButton>
        </Table>
      </View>
    </Container>
    <Container
      id="collapsibleContainer6"
      footerPadding="4px 12px"
      headerPadding="4px 12px"
      padding="12px"
      showBody={true}
      showHeader={true}
    >
      <Header>
        <Text
          id="collapsibleTitle6"
          value="##### Contas Contábeis"
          verticalAlign="center"
        />
        <ToggleButton
          id="collapsibleToggle6"
          horizontalAlign="right"
          iconForFalse="bold/interface-arrows-button-down"
          iconForTrue="bold/interface-arrows-button-up"
          iconPosition="replace"
          styleVariant="outline"
          text="{{ self.value ? 'Hide' : 'Show' }}"
          value="{{ collapsibleContainer6.showBody }}"
        >
          <Event
            event="change"
            method="setShowBody"
            params={{ map: { showBody: "{{ self.value }}" } }}
            pluginId="collapsibleContainer6"
            type="widget"
            waitMs="0"
            waitType="debounce"
          />
        </ToggleButton>
        <TextInput
          id="textInput27"
          iconBefore="bold/interface-search"
          label=""
          labelPosition="top"
          placeholder="Enter value"
        />
      </Header>
      <View id="fd113" viewKey="View 1">
        <Table
          id="tableAccount"
          actionsOverflowPosition={2}
          cellSelection="none"
          clearChangesetOnSave={true}
          data="{{ account_get.data }}"
          defaultSelectedRow={{ mode: "index", indexType: "display", index: 0 }}
          emptyMessage="No rows found"
          enableSaveActions={true}
          rowHeight="medium"
          searchTerm="{{ textInput27.value }}"
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
            size={39.046875}
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
            size={53.015625}
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
            size={45.8125}
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
            cellTooltipMode="overflow"
            format="string"
            groupAggregationMode="none"
            key="name"
            label="Name"
            placeholder="Enter value"
            position="center"
            size={208.546875}
            summaryAggregationMode="none"
          />
          <Column
            id="ec745"
            alignment="left"
            cellTooltipMode="overflow"
            format="string"
            groupAggregationMode="none"
            key="path"
            label="Path"
            placeholder="Enter value"
            position="center"
            size={324.5}
            summaryAggregationMode="none"
          />
          <Column
            id="7c0bc"
            alignment="left"
            cellTooltipMode="overflow"
            format="string"
            groupAggregationMode="none"
            key="description"
            label="Description"
            placeholder="Enter value"
            position="center"
            size={296}
            summaryAggregationMode="none"
          />
          <Column
            id="eccb7"
            alignment="left"
            cellTooltipMode="overflow"
            format="string"
            groupAggregationMode="none"
            key="key_words"
            label="Key words"
            placeholder="Enter value"
            position="center"
            size={154}
            summaryAggregationMode="none"
          />
          <Column
            id="c03f1"
            alignment="left"
            cellTooltipMode="overflow"
            format="string"
            groupAggregationMode="none"
            key="examples"
            label="Examples"
            placeholder="Enter value"
            position="center"
            size={291}
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
            size={116.046875}
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
            size={93.1875}
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
            size={60.890625}
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
            size={106.71875}
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
            size={62.9375}
            summaryAggregationMode="none"
          />
          <Column
            id="70994"
            alignment="left"
            format="json"
            groupAggregationMode="none"
            hidden="true"
            key="company"
            label="Company"
            placeholder="Enter value"
            position="center"
            size={100}
            summaryAggregationMode="none"
          />
          <Column
            id="33768"
            alignment="left"
            cellTooltipMode="overflow"
            format="tags"
            formatOptions={{ automaticColors: true }}
            groupAggregationMode="none"
            hidden="true"
            key="path_ids"
            label="Path ids"
            placeholder="Select options"
            position="center"
            size={100}
            summaryAggregationMode="none"
          />
          <Column
            id="44c99"
            alignment="right"
            editableOptions={{ showStepper: true }}
            format="decimal"
            formatOptions={{ showSeparators: true, notation: "standard" }}
            groupAggregationMode="sum"
            hidden="true"
            key="parent_id"
            label="Parent ID"
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
              pluginId="account_selected"
              type="state"
              waitMs="0"
              waitType="debounce"
            />
            <Event
              event="clickAction"
              method="show"
              params={{}}
              pluginId="modalAccount"
              type="widget"
              waitMs="0"
              waitType="debounce"
            />
            <Event
              event="clickAction"
              method="setValue"
              params={{ map: { value: "edit" } }}
              pluginId="account_mode"
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
              pluginId="account_selected"
              type="state"
              waitMs="0"
              waitType="debounce"
            />
            <Event
              event="clickAction"
              method="setValue"
              params={{ map: { value: "new" } }}
              pluginId="account_mode"
              type="state"
              waitMs="0"
              waitType="debounce"
            />
            <Event
              event="clickAction"
              method="show"
              params={{}}
              pluginId="modalAccount"
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
              pluginId="tableAccount"
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
              pluginId="tableAccount"
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
              pluginId="account_selected"
              type="state"
              waitMs="0"
              waitType="debounce"
            />
            <Event
              event="clickToolbar"
              method="show"
              params={{}}
              pluginId="modalAccount"
              type="widget"
              waitMs="0"
              waitType="debounce"
            />
            <Event
              event="clickToolbar"
              method="setValue"
              params={{ map: { value: "new" } }}
              pluginId="account_mode"
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
              pluginId="modalAccountFS"
              type="widget"
              waitMs="0"
              waitType="debounce"
            />
          </ToolbarButton>
        </Table>
      </View>
    </Container>
    <Container
      id="collapsibleContainer7"
      footerPadding="4px 12px"
      headerPadding="4px 12px"
      padding="12px"
      showBody={true}
      showHeader={true}
    >
      <Header>
        <Text
          id="collapsibleTitle7"
          value="##### Centros de Custo"
          verticalAlign="center"
        />
        <ToggleButton
          id="collapsibleToggle7"
          horizontalAlign="right"
          iconForFalse="bold/interface-arrows-button-down"
          iconForTrue="bold/interface-arrows-button-up"
          iconPosition="replace"
          styleVariant="outline"
          text="{{ self.value ? 'Hide' : 'Show' }}"
          value="{{ collapsibleContainer7.showBody }}"
        >
          <Event
            event="change"
            method="setShowBody"
            params={{ map: { showBody: "{{ self.value }}" } }}
            pluginId="collapsibleContainer7"
            type="widget"
            waitMs="0"
            waitType="debounce"
          />
        </ToggleButton>
      </Header>
      <View id="fd113" viewKey="View 1">
        <Table
          id="tableCostCenter"
          actionsOverflowPosition={2}
          autoColumnWidth={true}
          cellSelection="none"
          clearChangesetOnSave={true}
          data="{{ costcenter_get.data }}"
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
            id="8aa16"
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
            id="1955a"
            alignment="left"
            format="tag"
            formatOptions={{ automaticColors: true }}
            groupAggregationMode="none"
            key="center_type"
            label="Center type"
            placeholder="Select option"
            position="center"
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
          <Action
            id="4255e"
            icon="bold/interface-file-double"
            label="Duplicate"
          >
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
              pluginId="tableCostCenter"
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
              pluginId="tableCostCenter"
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
      </View>
    </Container>
  </View>
</Container>
