<Container
  id="tabbedContainer4"
  _gap="0px"
  currentViewKey="{{ self.viewKeys[0] }}"
  footerPadding="4px 12px"
  headerPadding="4px 12px"
  padding="12px"
  showBody={true}
>
  <Header>
    <Tabs
      id="tabs4"
      itemMode="static"
      navigateContainer={true}
      style={{ ordered: [] }}
      targetContainerId="tabbedContainer4"
      value="{{ self.values[0] }}"
    >
      <Option id="e5bca" value="Tab 1" />
      <Option id="dbdbc" value="Tab 2" />
      <Option id="fa204" value="Tab 3" />
    </Tabs>
  </Header>
  <View id="ef909" label="Regras de Integração" viewKey="Regras de Integração">
    <Container
      id="Funcionario3"
      footerPadding="4px 12px"
      headerPadding="4px 12px"
      margin="0"
      padding="0"
      showBody={true}
      showBorder={false}
      style={{ ordered: [{ background: "rgba(255, 255, 255, 0)" }] }}
    >
      <View id="80487" viewKey="View 1">
        <Table
          id="table50"
          actionsOverflowPosition={1}
          cellSelection="none"
          clearChangesetOnSave={true}
          data="{{ IntegrationRule_get2.data }}"
          defaultSelectedRow={{ mode: "index", indexType: "display", index: 0 }}
          emptyMessage="No rows found"
          enableSaveActions={true}
          rowHeight="small"
          showBorder={true}
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
            size={27.75}
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
            size={83.71875}
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
            size={69.78125}
            summaryAggregationMode="none"
          />
          <Column
            id="81d3a"
            alignment="left"
            format="string"
            groupAggregationMode="none"
            key="created_at"
            label="Created at"
            placeholder="Enter value"
            position="center"
            size={100}
            summaryAggregationMode="none"
          />
          <Column
            id="a83f7"
            alignment="left"
            format="string"
            groupAggregationMode="none"
            key="updated_at"
            label="Updated at"
            placeholder="Enter value"
            position="center"
            size={100}
            summaryAggregationMode="none"
          />
          <Column
            id="921eb"
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
          <Column
            id="50d3a"
            alignment="left"
            format="string"
            groupAggregationMode="none"
            key="description"
            label="Description"
            placeholder="Enter value"
            position="center"
            size={100}
            summaryAggregationMode="none"
          />
          <Column
            id="ca70c"
            alignment="left"
            format="string"
            groupAggregationMode="none"
            key="trigger_event"
            label="Trigger event"
            placeholder="Enter value"
            position="center"
            size={100}
            summaryAggregationMode="none"
          />
          <Column
            id="29e7d"
            alignment="right"
            editableOptions={{ showStepper: true }}
            format="decimal"
            formatOptions={{ showSeparators: true, notation: "standard" }}
            groupAggregationMode="sum"
            key="execution_order"
            label="Execution order"
            placeholder="Enter value"
            position="center"
            size={100}
            summaryAggregationMode="none"
          />
          <Column
            id="6dfcd"
            alignment="left"
            format="string"
            groupAggregationMode="none"
            key="filter_conditions"
            label="Filter conditions"
            placeholder="Enter value"
            position="center"
            size={100}
            summaryAggregationMode="none"
          />
          <Column
            id="19fb7"
            alignment="left"
            cellTooltipMode="overflow"
            format="multilineString"
            groupAggregationMode="none"
            key="rule"
            label="Rule"
            placeholder="Enter value"
            position="center"
            size={100}
            summaryAggregationMode="none"
          />
          <Column
            id="d087c"
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
            id="00b32"
            alignment="left"
            format="string"
            groupAggregationMode="none"
            key="last_run_at"
            label="Last run at"
            placeholder="Enter value"
            position="center"
            size={100}
            summaryAggregationMode="none"
          />
          <Column
            id="5322f"
            alignment="right"
            editableOptions={{ showStepper: true }}
            format="decimal"
            formatOptions={{ showSeparators: true, notation: "standard" }}
            groupAggregationMode="sum"
            key="times_executed"
            label="Times executed"
            placeholder="Enter value"
            position="center"
            size={100}
            summaryAggregationMode="none"
          />
          <Column
            id="9d687"
            alignment="left"
            format="string"
            groupAggregationMode="none"
            key="created_by"
            label="Created by"
            placeholder="Enter value"
            position="center"
            size={100}
            summaryAggregationMode="none"
          />
          <Column
            id="d277b"
            alignment="left"
            format="string"
            groupAggregationMode="none"
            key="updated_by"
            label="Updated by"
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
              pluginId="IntegrationRuleSelected2"
              type="state"
              waitMs="0"
              waitType="debounce"
            />
            <Event
              event="clickAction"
              method="show"
              params={{ ordered: [] }}
              pluginId="modalFrame13"
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
              pluginId="table50"
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
              pluginId="table50"
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
              pluginId="IntegrationRuleSelected2"
              type="state"
              waitMs="0"
              waitType="debounce"
            />
            <Event
              event="clickToolbar"
              method="show"
              params={{ ordered: [] }}
              pluginId="modalFrame13"
              type="widget"
              waitMs="0"
              waitType="debounce"
            />
          </ToolbarButton>
        </Table>
      </View>
    </Container>
  </View>
  <View id="46672" label="Regras de Ajuste" viewKey="Regras de Ajuste">
    <Container
      id="group68"
      footerPadding="4px 12px"
      headerPadding="4px 12px"
      margin="0"
      padding="0"
      showBody={true}
      showBorder={false}
      style={{ ordered: [{ background: "rgba(255, 255, 255, 0)" }] }}
    >
      <View id="80487" viewKey="View 1">
        <Table
          id="table51"
          actionsOverflowPosition={1}
          cellSelection="none"
          clearChangesetOnSave={true}
          data="{{ positions_get.data }}"
          defaultSelectedRow={{ mode: "index", indexType: "display", index: 0 }}
          emptyMessage="No rows found"
          enableSaveActions={true}
          rowHeight="small"
          showBorder={true}
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
            size={27.796875}
            summaryAggregationMode="none"
          />
          <Column
            id="57030"
            alignment="right"
            editableOptions={{ showStepper: true }}
            format="decimal"
            formatOptions={{ showSeparators: true, notation: "standard" }}
            groupAggregationMode="sum"
            key="company"
            label="Company"
            placeholder="Enter value"
            position="center"
            size={69.875}
            summaryAggregationMode="none"
          />
          <Column
            id="9fa13"
            alignment="left"
            format="string"
            groupAggregationMode="none"
            key="title"
            label="Title"
            placeholder="Enter value"
            position="center"
            size={100}
            summaryAggregationMode="none"
          />
          <Column
            id="440bf"
            alignment="left"
            format="string"
            groupAggregationMode="none"
            key="description"
            label="Description"
            placeholder="Enter value"
            position="center"
            size={100}
            summaryAggregationMode="none"
          />
          <Column
            id="996b9"
            alignment="left"
            format="string"
            groupAggregationMode="none"
            key="department"
            label="Department"
            placeholder="Enter value"
            position="center"
            size={100}
            summaryAggregationMode="none"
          />
          <Column
            id="5b7e2"
            alignment="right"
            editableOptions={{ showStepper: true }}
            format="decimal"
            formatOptions={{ showSeparators: true, notation: "standard" }}
            groupAggregationMode="sum"
            key="hierarchy_level"
            label="Hierarchy level"
            placeholder="Enter value"
            position="center"
            size={100}
            summaryAggregationMode="none"
          />
          <Column
            id="b4081"
            alignment="right"
            editableOptions={{ showStepper: true }}
            format="decimal"
            formatOptions={{ showSeparators: true, notation: "standard" }}
            groupAggregationMode="sum"
            key="min_salary"
            label="Min salary"
            placeholder="Enter value"
            position="center"
            size={100}
            summaryAggregationMode="none"
          />
          <Column
            id="d7435"
            alignment="right"
            editableOptions={{ showStepper: true }}
            format="decimal"
            formatOptions={{ showSeparators: true, notation: "standard" }}
            groupAggregationMode="sum"
            key="max_salary"
            label="Max salary"
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
              pluginId="position_selected"
              type="state"
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
              pluginId="table51"
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
              pluginId="table51"
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
              pluginId="position_selected"
              type="state"
              waitMs="0"
              waitType="debounce"
            />
          </ToolbarButton>
        </Table>
      </View>
    </Container>
  </View>
  <View id="df07f" label="Time Tracking" viewKey="View 3">
    <Container
      id="group69"
      footerPadding="4px 12px"
      headerPadding="4px 12px"
      margin="0"
      padding="0"
      showBody={true}
      showBorder={false}
      style={{ ordered: [{ background: "rgba(255, 255, 255, 0)" }] }}
    >
      <View id="80487" viewKey="View 1">
        <Table
          id="table52"
          actionsOverflowPosition={2}
          cellSelection="none"
          clearChangesetOnSave={true}
          data="{{ timetracking_get.data }}"
          defaultSelectedRow={{ mode: "index", indexType: "display", index: 0 }}
          emptyMessage="No rows found"
          enableSaveActions={true}
          rowHeight="small"
          showBorder={true}
          showFooter={true}
          showHeader={true}
          toolbarPosition="bottom"
        >
          <Column
            id="ff2a0"
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
            id="3e4df"
            alignment="left"
            format="string"
            groupAggregationMode="none"
            key="employee"
            label="Employee"
            placeholder="Enter value"
            position="center"
            size={100}
            summaryAggregationMode="none"
            valueOverride="{{ item.name }}"
          />
          <Column
            id="3b943"
            alignment="left"
            format="date"
            groupAggregationMode="none"
            key="month"
            label="Month"
            placeholder="Enter value"
            position="center"
            size={100}
            summaryAggregationMode="none"
          />
          <Column
            id="7f6c7"
            alignment="right"
            editableOptions={{ showStepper: true }}
            format="decimal"
            formatOptions={{ showSeparators: true, notation: "standard" }}
            groupAggregationMode="sum"
            key="total_hours_worked"
            label="Total hours worked"
            placeholder="Enter value"
            position="center"
            size={100}
            summaryAggregationMode="none"
          />
          <Column
            id="f8a3a"
            alignment="right"
            editableOptions={{ showStepper: true }}
            format="decimal"
            formatOptions={{ showSeparators: true, notation: "standard" }}
            groupAggregationMode="sum"
            key="total_overtime_hours"
            label="Total overtime hours"
            placeholder="Enter value"
            position="center"
            size={100}
            summaryAggregationMode="none"
          />
          <Column
            id="3e7a2"
            alignment="right"
            editableOptions={{ showStepper: true }}
            format="decimal"
            formatOptions={{ showSeparators: true, notation: "standard" }}
            groupAggregationMode="sum"
            key="overtime_hours_paid"
            label="Overtime hours paid"
            placeholder="Enter value"
            position="center"
            size={100}
            summaryAggregationMode="none"
          />
          <Column
            id="0b4fe"
            alignment="right"
            editableOptions={{ showStepper: true }}
            format="decimal"
            formatOptions={{ showSeparators: true, notation: "standard" }}
            groupAggregationMode="sum"
            key="days_present"
            label="Days present"
            placeholder="Enter value"
            position="center"
            size={100}
            summaryAggregationMode="none"
          />
          <Column
            id="2f629"
            alignment="right"
            editableOptions={{ showStepper: true }}
            format="decimal"
            formatOptions={{ showSeparators: true, notation: "standard" }}
            groupAggregationMode="sum"
            key="days_absent"
            label="Days absent"
            placeholder="Enter value"
            position="center"
            size={100}
            summaryAggregationMode="none"
          />
          <Column
            id="a96ee"
            alignment="right"
            editableOptions={{ showStepper: true }}
            format="decimal"
            formatOptions={{ showSeparators: true, notation: "standard" }}
            groupAggregationMode="sum"
            key="leave_days"
            label="Leave days"
            placeholder="Enter value"
            position="center"
            size={100}
            summaryAggregationMode="none"
          />
          <Column
            id="4cbb5"
            alignment="right"
            editableOptions={{ showStepper: true }}
            format="decimal"
            formatOptions={{ showSeparators: true, notation: "standard" }}
            groupAggregationMode="sum"
            key="effective_hours"
            label="Effective hours"
            placeholder="Enter value"
            position="center"
            size={100}
            summaryAggregationMode="none"
          />
          <Column
            id="b49e5"
            alignment="left"
            format="boolean"
            groupAggregationMode="none"
            key="overtime_eligible"
            label="Overtime eligible"
            placeholder="Enter value"
            position="center"
            size={100}
            summaryAggregationMode="none"
          />
          <Column
            id="b1d9d"
            alignment="right"
            editableOptions={{ showStepper: true }}
            format="decimal"
            formatOptions={{ showSeparators: true, notation: "standard" }}
            groupAggregationMode="sum"
            key="bank_hours_balance"
            label="Bank hours balance"
            placeholder="Enter value"
            position="center"
            size={100}
            summaryAggregationMode="none"
          />
          <Column
            id="68f95"
            alignment="left"
            format="string"
            groupAggregationMode="none"
            key="vacation_start_date"
            label="Vacation start date"
            placeholder="Enter value"
            position="center"
            size={100}
            summaryAggregationMode="none"
          />
          <Column
            id="31637"
            alignment="left"
            format="string"
            groupAggregationMode="none"
            key="vacation_end_date"
            label="Vacation end date"
            placeholder="Enter value"
            position="center"
            size={100}
            summaryAggregationMode="none"
          />
          <Column
            id="d8c12"
            alignment="right"
            editableOptions={{ showStepper: true }}
            format="decimal"
            formatOptions={{ showSeparators: true, notation: "standard" }}
            groupAggregationMode="sum"
            key="vacation_days_used"
            label="Vacation days used"
            placeholder="Enter value"
            position="center"
            size={100}
            summaryAggregationMode="none"
          />
          <Column
            id="e4aa1"
            alignment="left"
            format="string"
            groupAggregationMode="none"
            key="vacation_status"
            label="Vacation status"
            placeholder="Enter value"
            position="center"
            size={100}
            summaryAggregationMode="none"
          />
          <Column
            id="820c8"
            alignment="left"
            format="string"
            groupAggregationMode="none"
            key="absence_reason"
            label="Absence reason"
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
              pluginId="timetracking_selected"
              type="state"
              waitMs="0"
              waitType="debounce"
            />
          </Action>
          <Action id="a4440" icon="bold/interface-delete-bin-2" label="Delete">
            <Event
              event="clickAction"
              method="setValue"
              params={{ ordered: [{ value: "{{ currentSourceRow }}" }] }}
              pluginId="timetracking_selected"
              type="state"
              waitMs="0"
              waitType="debounce"
            />
            <Event
              event="clickAction"
              method="trigger"
              params={{ ordered: [] }}
              pluginId="timetracking_delete"
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
              pluginId="table52"
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
              pluginId="table52"
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
              pluginId="timetracking_selected"
              type="state"
              waitMs="0"
              waitType="debounce"
            />
          </ToolbarButton>
        </Table>
        <Form
          id="TimeTrackingForm3"
          footerPadding="4px 12px"
          headerPadding="4px 12px"
          initialData=""
          padding="12px"
          requireValidation={true}
          resetAfterSubmit={true}
          showBody={true}
          showFooter={true}
          showHeader={true}
        >
          <Header>
            <Text
              id="formTitle33"
              value={
                '#### {{ timetracking_selected.value === "" ? "Novo" : "Editar" }} Time Tracking'
              }
              verticalAlign="center"
            />
          </Header>
          <Body>
            <Select
              id="select21"
              data="{{ employees_get.data }}"
              emptyMessage="No options"
              formDataKey="employee"
              label="Funcionário"
              labelPosition="top"
              labels="{{ item.name }}"
              overlayMaxHeight={375}
              placeholder="Select an option"
              showSelectionIndicator={true}
              value="{{ timetracking_selected.value.employee.id }}"
              values="{{ item.id }}"
            />
            <Date
              id="Date16"
              dateFormat="MMM d, yyyy"
              datePlaceholder="{{ self.dateFormat.toUpperCase() }}"
              formDataKey="month_date"
              iconBefore="bold/interface-calendar"
              label="Data"
              labelPosition="top"
              value="{{ timetracking_selected.value[self.formDataKey] }}"
            />
            <Divider id="divider23" />
            <Date
              id="Date17"
              dateFormat="MMM d, yyyy"
              datePlaceholder="{{ self.dateFormat.toUpperCase() }}"
              formDataKey="month"
              iconBefore="bold/interface-calendar"
              label="Início Férias"
              labelPosition="top"
              value="{{ timetracking_selected.value[self.formDataKey] }}"
            />
            <Date
              id="Date18"
              dateFormat="MMM d, yyyy"
              datePlaceholder="{{ self.dateFormat.toUpperCase() }}"
              formDataKey="month"
              iconBefore="bold/interface-calendar"
              label="Fim Férias"
              labelPosition="top"
              value="{{ timetracking_selected.value[self.formDataKey] }}"
            />
            <NumberInput
              id="numberInput106"
              currency="USD"
              decimalPlaces="2"
              formDataKey="overtime_hours"
              inputValue={0}
              label="Dias Férias Usados"
              labelPosition="top"
              min="0"
              placeholder="Enter value"
              showSeparators={true}
              showStepper={true}
              value="{{ timetracking_selected.value[self.formDataKey] }}"
            />
            <NumberInput
              id="numberInput108"
              currency="USD"
              inputValue={0}
              label="Férias Vendidas"
              labelPosition="top"
              placeholder="Enter value"
              showSeparators={true}
              showStepper={true}
              value={0}
            />
            <Divider id="divider22" />
            <NumberInput
              id="numberInput100"
              currency="USD"
              decimalPlaces="2"
              formDataKey="days_present"
              inputValue={0}
              label="Dias Trabalhados"
              labelPosition="top"
              min="0"
              placeholder="Enter value"
              showSeparators={true}
              showStepper={true}
              value="{{ timetracking_selected.value[self.formDataKey] }}"
            />
            <NumberInput
              id="numberInput101"
              currency="USD"
              decimalPlaces="2"
              formDataKey="days_absent"
              inputValue={0}
              label="Faltas Descontadas"
              labelPosition="top"
              min="0"
              placeholder="Enter value"
              showSeparators={true}
              showStepper={true}
              value="{{ timetracking_selected.value[self.formDataKey] }}"
            />
            <NumberInput
              id="numberInput104"
              currency="USD"
              decimalPlaces="2"
              formDataKey="leave_days"
              inputValue={0}
              label="Faltas Justificadas"
              labelPosition="top"
              min="0"
              placeholder="Enter value"
              showSeparators={true}
              showStepper={true}
              value="{{ timetracking_selected.value[self.formDataKey] }}"
            />
            <Divider id="divider21" />
            <NumberInput
              id="numberInput103"
              currency="USD"
              decimalPlaces="2"
              formDataKey="total_hours_worked"
              inputValue={0}
              label="Horas Trabalhadas"
              labelPosition="top"
              min="0"
              placeholder="Enter value"
              showSeparators={true}
              showStepper={true}
              value="{{ timetracking_selected.value[self.formDataKey] }}"
            />
            <NumberInput
              id="numberInput102"
              currency="USD"
              decimalPlaces="2"
              formDataKey="total_overtime_hours"
              inputValue={0}
              label="Horas Extras"
              labelPosition="top"
              min="0"
              placeholder="Enter value"
              showSeparators={true}
              showStepper={true}
              value="{{ timetracking_selected.value[self.formDataKey] }}"
            />
            <NumberInput
              id="numberInput105"
              currency="USD"
              decimalPlaces="2"
              formDataKey="overtime_hours_paid"
              inputValue={0}
              label="Horas Extras Pagas"
              labelPosition="top"
              min="0"
              placeholder="Enter value"
              showSeparators={true}
              showStepper={true}
              value="{{ timetracking_selected.value[self.formDataKey] }}"
            />
            <NumberInput
              id="numberInput107"
              currency="USD"
              decimalPlaces="2"
              disabled="true"
              formDataKey=""
              inputValue={0}
              label="Banco de Horas"
              labelPosition="top"
              min="0"
              placeholder="Enter value"
              showSeparators={true}
              value="{{ numberInput38.value - numberInput105.value }}"
            />
            <TextInput
              id="textInput25"
              labelPosition="top"
              placeholder="Enter value"
              value="{{ select21.value }}"
            />
          </Body>
          <Footer>
            <Button
              id="NewButton20"
              hidden={'{{ timetracking_selected.value !== "" }}'}
              submitTargetId="TimeTrackingForm3"
              text="Submit"
            >
              <Event
                event="click"
                method="trigger"
                params={{ ordered: [] }}
                pluginId="timetracking_new"
                type="datasource"
                waitMs="0"
                waitType="debounce"
              />
            </Button>
            <Button
              id="EditButton20"
              hidden={'{{ timetracking_selected.value === "" }}'}
              submit={true}
              submitTargetId="TimeTrackingForm3"
              text="Edit"
            />
          </Footer>
          <Event
            event="submit"
            method="trigger"
            params={{ ordered: [] }}
            pluginId="timetracking_edit"
            type="datasource"
            waitMs="0"
            waitType="debounce"
          />
        </Form>
      </View>
    </Container>
  </View>
  <View
    id="b7c00"
    disabled={false}
    hidden={false}
    iconPosition="left"
    label="Benefícios e Descontos"
    viewKey="View 5"
  >
    <Container
      id="group70"
      footerPadding="4px 12px"
      headerPadding="4px 12px"
      margin="0"
      padding="0"
      showBody={true}
      showBorder={false}
      style={{ ordered: [{ background: "rgba(255, 255, 255, 0)" }] }}
    >
      <View id="80487" viewKey="View 1">
        <Table
          id="table54"
          actionsOverflowPosition={1}
          cellSelection="none"
          clearChangesetOnSave={true}
          data="{{ recurring_adjustment_get.data }}"
          defaultSelectedRow={{ mode: "index", indexType: "display", index: 0 }}
          emptyMessage="No rows found"
          enableSaveActions={true}
          rowHeight="small"
          showBorder={true}
          showFooter={true}
          showHeader={true}
          toolbarPosition="bottom"
        >
          <Column
            id="ff2a0"
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
            size={27.796875}
            summaryAggregationMode="none"
          />
          <Column
            id="3e4df"
            alignment="left"
            format="string"
            groupAggregationMode="none"
            key="employee"
            label="Employee"
            placeholder="Enter value"
            position="center"
            size={71.109375}
            summaryAggregationMode="none"
            valueOverride="{{ item.name }}"
          />
          <Column
            id="b099b"
            alignment="left"
            format="string"
            groupAggregationMode="none"
            key="name"
            label="Name"
            placeholder="Enter value"
            position="center"
            size={175.484375}
            summaryAggregationMode="none"
          />
          <Column
            id="fcb96"
            alignment="left"
            format="string"
            groupAggregationMode="none"
            key="type"
            label="Type"
            placeholder="Enter value"
            position="center"
            size={72.953125}
            summaryAggregationMode="none"
          />
          <Column
            id="accbd"
            alignment="left"
            format="date"
            groupAggregationMode="none"
            key="start_date"
            label="Start date"
            placeholder="Enter value"
            position="center"
            size={83.359375}
            summaryAggregationMode="none"
          />
          <Column
            id="c65b9"
            alignment="left"
            format="date"
            groupAggregationMode="none"
            key="end_date"
            label="End date"
            placeholder="Enter value"
            position="center"
            size={90.671875}
            summaryAggregationMode="none"
          />
          <Column
            id="30de3"
            alignment="left"
            format="boolean"
            groupAggregationMode="none"
            key="base_for_inss"
            label="Base for inss"
            placeholder="Enter value"
            position="center"
            size={88.6875}
            summaryAggregationMode="none"
          />
          <Column
            id="a0fbe"
            alignment="left"
            format="boolean"
            groupAggregationMode="none"
            key="base_for_fgts"
            label="Base for fgts"
            placeholder="Enter value"
            position="center"
            size={88.15625}
            summaryAggregationMode="none"
          />
          <Column
            id="77ec8"
            alignment="left"
            format="boolean"
            groupAggregationMode="none"
            key="base_for_irpf"
            label="Base for irpf"
            placeholder="Enter value"
            position="center"
            size={85.234375}
            summaryAggregationMode="none"
          />
          <Column
            id="f3c99"
            alignment="left"
            format="string"
            groupAggregationMode="none"
            key="calculation_formula"
            label="Calculation formula"
            placeholder="Enter value"
            position="center"
            size={100}
            summaryAggregationMode="none"
          />
          <Column
            id="a6635"
            alignment="left"
            format="string"
            groupAggregationMode="none"
            key="employer_cost_formula"
            label="Employer cost formula"
            placeholder="Enter value"
            position="center"
            size={100}
            summaryAggregationMode="none"
          />
          <Column
            id="368b3"
            alignment="right"
            editableOptions={{ showStepper: true }}
            format="decimal"
            formatOptions={{ showSeparators: true, notation: "standard" }}
            groupAggregationMode="sum"
            key="priority"
            label="Priority"
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
              pluginId="recurring_adjustment_selected"
              type="state"
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
              pluginId="table54"
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
              pluginId="table54"
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
              pluginId="recurring_adjustment_selected"
              type="state"
              waitMs="0"
              waitType="debounce"
            />
          </ToolbarButton>
        </Table>
        <Form
          id="RecurringAdjustmentForm3"
          footerPadding="4px 12px"
          headerPadding="4px 12px"
          initialData=""
          padding="12px"
          requireValidation={true}
          resetAfterSubmit={true}
          showBody={true}
          showFooter={true}
          showHeader={true}
        >
          <Header>
            <Text
              id="formTitle34"
              value={
                '#### {{ recurring_adjustment_selected.value === "" ? "Novo" : "Editar" }} Ajuste'
              }
              verticalAlign="center"
            />
          </Header>
          <Body>
            <TextInput
              id="textInput26"
              formDataKey="name"
              label="Nome do Ajuste"
              labelPosition="top"
              placeholder="Enter value"
              value="{{ recurring_adjustment_selected.value[self.formDataKey] }}"
            />
            <Select
              id="select22"
              data="{{ employees_get.data }}"
              emptyMessage="No options"
              formDataKey="employee"
              label="Funcionário"
              labelPosition="top"
              labels="{{ item.name }}"
              overlayMaxHeight={375}
              placeholder="Select an option"
              showSelectionIndicator={true}
              value="{{ recurring_adjustment_selected.value[self.formDataKey].id }}"
              values="{{ item.id }}"
            />
            <Date
              id="Date19"
              dateFormat="MMM d, yyyy"
              datePlaceholder="{{ self.dateFormat.toUpperCase() }}"
              formDataKey="start_date"
              iconBefore="bold/interface-calendar"
              label="Data Início"
              labelPosition="top"
              value="{{ recurring_adjustment_selected.value[self.formDataKey] }}"
            />
            <Date
              id="Date20"
              dateFormat="MMM d, yyyy"
              datePlaceholder="{{ self.dateFormat.toUpperCase() }}"
              formDataKey="end_date"
              iconBefore="bold/interface-calendar"
              label="Data Fim"
              labelPosition="top"
              value="{{ recurring_adjustment_selected.value[self.formDataKey] }}"
            />
            <Select
              id="select23"
              emptyMessage="No options"
              formDataKey="type"
              itemMode="static"
              label="Tipo"
              labelPosition="top"
              overlayMaxHeight={375}
              placeholder="Select an option"
              showSelectionIndicator={true}
              value="{{ recurring_adjustment_selected.value[self.formDataKey] }}"
            >
              <Option id="0d2b4" label="Dedução" value="deduction" />
              <Option id="f8ec9" label="Adicional" value="additional" />
            </Select>
            <Checkbox
              id="checkbox13"
              formDataKey="base_for_inss"
              label="Impacta INSS"
              labelWidth="100"
              value="{{ recurring_adjustment_selected.value[self.formDataKey] }}"
            />
            <Checkbox
              id="checkbox14"
              formDataKey="base_for_fgts"
              label="Impacta FGTS"
              labelWidth="100"
              value="{{ recurring_adjustment_selected.value[self.formDataKey] }}"
            />
            <Checkbox
              id="checkbox15"
              formDataKey="base_for_irpf"
              label="Impacta IRRF"
              labelWidth="100"
              value="{{ recurring_adjustment_selected.value[self.formDataKey] }}"
            />
            <Divider id="divider24" />
            <TagsWidget2
              id="tags3"
              _colorByIndex={["", "", ""]}
              _hiddenByIndex={[false, false, false]}
              _iconByIndex={["", "", ""]}
              _ids={["3611a", "25b24", "28900"]}
              _imageByIndex={["", "", ""]}
              _labels={["", "", ""]}
              _textColorByIndex={["", "", ""]}
              _tooltipByIndex={["", "", ""]}
              _values={["base_salary", "days_present", "leave"]}
              allowWrap={true}
              data={
                "[\"base_salary\", \"days_present\",\n'days_absent',\n            'leave_days',\n            'total_days',\n            'total_hours_worked',\n            'total_overtime_hours',\n            'overtime_hours_paid',\n            'bank_hours_balance',\n            'vacation_days_used']"
              }
              labels="{{ item }}"
              values="{{ item }}"
            >
              <Event
                event="click"
                method="setValue"
                params={{
                  ordered: [{ value: "{{ textArea12.value }}[{{ item }}]" }],
                }}
                pluginId="textArea12"
                type="widget"
                waitMs="0"
                waitType="debounce"
              />
              <Event
                event="click"
                method="focus"
                params={{ ordered: [] }}
                pluginId="textArea12"
                type="widget"
                waitMs="0"
                waitType="debounce"
              />
            </TagsWidget2>
            <TextArea
              id="textArea12"
              autoResize={true}
              formDataKey="calculation_formula"
              label="Fórmula"
              labelPosition="top"
              minLines={2}
              placeholder="Enter value"
              value="{{ recurring_adjustment_selected.value.calculation_formula }}"
            />
          </Body>
          <Footer>
            <Button
              id="NewButton21"
              hidden={'{{ recurring_adjustment_selected.value !== "" }}'}
              submitTargetId="RecurringAdjustmentForm3"
              text="Submit"
            >
              <Event
                event="click"
                method="trigger"
                params={{ ordered: [] }}
                pluginId="recurring_adjustment_new"
                type="datasource"
                waitMs="0"
                waitType="debounce"
              />
            </Button>
            <Button
              id="EditButton21"
              hidden={'{{ recurring_adjustment_selected.value === "" }}'}
              submit={true}
              submitTargetId="RecurringAdjustmentForm3"
              text="Edit"
            />
          </Footer>
          <Event
            event="submit"
            method="trigger"
            params={{ ordered: [] }}
            pluginId="recurring_adjustment_edit"
            type="datasource"
            waitMs="0"
            waitType="debounce"
          />
        </Form>
      </View>
    </Container>
  </View>
  <View
    id="9719f"
    disabled={false}
    hidden={false}
    iconPosition="left"
    label="Payroll"
    viewKey="View 4"
  >
    <Table
      id="table53"
      actionsOverflowPosition={2}
      cellSelection="none"
      clearChangesetOnSave={true}
      data="{{ payroll_get.data }}"
      defaultSelectedRow={{ mode: "index", indexType: "display", index: 0 }}
      emptyMessage="No rows found"
      enableSaveActions={true}
      rowHeight="small"
      showBorder={true}
      showFooter={true}
      showHeader={true}
      toolbarPosition="bottom"
    >
      <Column
        id="408b3"
        alignment="right"
        editableOptions={{ showStepper: true }}
        format="decimal"
        formatOptions={{ showSeparators: true, notation: "standard" }}
        groupAggregationMode="sum"
        key="id"
        label="ID"
        placeholder="Enter value"
        position="left"
        size={32.796875}
        summaryAggregationMode="none"
      />
      <Column
        id="5bf20"
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
        size={69.875}
        summaryAggregationMode="none"
      />
      <Column
        id="521d3"
        alignment="left"
        editableOptions={{ showStepper: true }}
        format="string"
        formatOptions={{ showSeparators: true, notation: "standard" }}
        groupAggregationMode="sum"
        key="employee"
        label="Employee"
        placeholder="Enter value"
        position="left"
        size={162.109375}
        summaryAggregationMode="none"
        valueOverride="{{ item.name }}"
      />
      <Column
        id="1303a"
        alignment="left"
        format="date"
        groupAggregationMode="none"
        key="pay_date"
        label="Pay date"
        placeholder="Enter value"
        position="center"
        size={83.03125}
        summaryAggregationMode="none"
      />
      <Column
        id="313e0"
        alignment="right"
        editableOptions={{ showStepper: true }}
        format="decimal"
        formatOptions={{ showSeparators: true, notation: "standard" }}
        groupAggregationMode="sum"
        key="gross_salary"
        label="Gross salary"
        placeholder="Enter value"
        position="center"
        size={86.265625}
        summaryAggregationMode="none"
      />
      <Column
        id="748f3"
        alignment="right"
        editableOptions={{ showStepper: true }}
        format="decimal"
        formatOptions={{ showSeparators: true, notation: "standard" }}
        groupAggregationMode="sum"
        key="net_salary"
        label="Net salary"
        placeholder="Enter value"
        position="center"
        size={73.78125}
        summaryAggregationMode="none"
      />
      <Column
        id="b5081"
        alignment="right"
        editableOptions={{ showStepper: true }}
        format="decimal"
        formatOptions={{ showSeparators: true, notation: "standard" }}
        groupAggregationMode="sum"
        key="inss_deduction"
        label="Inss deduction"
        placeholder="Enter value"
        position="center"
        size={99.0625}
        summaryAggregationMode="none"
      />
      <Column
        id="4bb07"
        alignment="right"
        editableOptions={{ showStepper: true }}
        format="decimal"
        formatOptions={{ showSeparators: true, notation: "standard" }}
        groupAggregationMode="sum"
        key="irrf_deduction"
        label="Irrf deduction"
        placeholder="Enter value"
        position="center"
        size={93.171875}
        summaryAggregationMode="none"
      />
      <Column
        id="55130"
        alignment="right"
        editableOptions={{ showStepper: true }}
        format="decimal"
        formatOptions={{ showSeparators: true, notation: "standard" }}
        groupAggregationMode="sum"
        key="fgts"
        label="Fgts"
        placeholder="Enter value"
        position="center"
        size={54.0625}
        summaryAggregationMode="none"
      />
      <Column
        id="50140"
        alignment="right"
        editableOptions={{ showStepper: true }}
        format="decimal"
        formatOptions={{ showSeparators: true, notation: "standard" }}
        groupAggregationMode="sum"
        key="bonus"
        label="Bonus"
        placeholder="Enter value"
        position="center"
        size={51.234375}
        summaryAggregationMode="none"
      />
      <Column
        id="9168e"
        alignment="right"
        editableOptions={{ showStepper: true }}
        format="decimal"
        formatOptions={{ showSeparators: true, notation: "standard" }}
        groupAggregationMode="sum"
        key="bank_hours"
        label="Bank hours"
        placeholder="Enter value"
        position="center"
        size={79.46875}
        summaryAggregationMode="none"
      />
      <Column
        id="d9fad"
        alignment="right"
        editableOptions={{ showStepper: true }}
        format="decimal"
        formatOptions={{ showSeparators: true, notation: "standard" }}
        groupAggregationMode="sum"
        key="absence_deduction"
        label="Absence deduction"
        placeholder="Enter value"
        position="center"
        size={125.859375}
        summaryAggregationMode="none"
      />
      <Column
        id="2a2e8"
        alignment="left"
        format="string"
        groupAggregationMode="none"
        key="status"
        label="Status"
        placeholder="Enter value"
        position="center"
        size={61.96875}
        summaryAggregationMode="none"
      />
      <Column
        id="8dff8"
        alignment="left"
        cellTooltipMode="overflow"
        format="multilineString"
        groupAggregationMode="none"
        key="adjustment_details"
        label="Adjustment details"
        placeholder="Enter value"
        position="center"
        size={897}
        summaryAggregationMode="none"
      />
      <Action
        id="8686a"
        icon="bold/interface-arrows-reload-2-alternate"
        label="Recalcular"
      >
        <Event
          event="clickAction"
          method="trigger"
          params={{ ordered: [] }}
          pluginId="payroll_recal"
          type="datasource"
          waitMs="0"
          waitType="debounce"
        />
      </Action>
      <Action id="d9f7c" icon="bold/interface-delete-bin-2" label="Delete">
        <Event
          event="clickAction"
          method="setValue"
          params={{ ordered: [{ value: "{{ currentSourceRow }}" }] }}
          pluginId="payroll_selected"
          type="state"
          waitMs="0"
          waitType="debounce"
        />
        <Event
          event="clickAction"
          method="trigger"
          params={{ ordered: [] }}
          pluginId="payroll_delete"
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
          pluginId="table53"
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
          pluginId="table53"
          type="widget"
          waitMs="0"
          waitType="debounce"
        />
      </ToolbarButton>
    </Table>
  </View>
</Container>
