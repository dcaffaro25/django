<Container
  id="tabbedContainer2"
  _gap="0px"
  currentViewKey="{{ self.viewKeys[0] }}"
  footerPadding="4px 12px"
  headerPadding="4px 12px"
  padding="12px"
  showBody={true}
>
  <Header>
    <Tabs
      id="tabs2"
      itemMode="static"
      navigateContainer={true}
      style={{ ordered: [] }}
      targetContainerId="tabbedContainer2"
      value="{{ self.values[0] }}"
    >
      <Option id="e5bca" value="Tab 1" />
      <Option id="dbdbc" value="Tab 2" />
      <Option id="fa204" value="Tab 3" />
    </Tabs>
  </Header>
  <View id="ef909" label="Regras de Integração" viewKey="Regras de Integração">
    <Container
      id="Funcionario2"
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
          id="table14"
          actionsOverflowPosition={1}
          cellSelection="none"
          clearChangesetOnSave={true}
          data="{{ SubstitutionRule_get.data }}"
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
            size={30.765625}
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
            size={97.875}
            summaryAggregationMode="none"
          />
          <Column
            id="ace2f"
            alignment="left"
            format="tag"
            formatOptions={{ automaticColors: true }}
            groupAggregationMode="none"
            key="model_name"
            label="Model name"
            placeholder="Select option"
            position="center"
            size={110}
            summaryAggregationMode="none"
            valueOverride="{{ _.startCase(item) }}"
          />
          <Column
            id="88c86"
            alignment="left"
            format="tag"
            formatOptions={{ automaticColors: true }}
            groupAggregationMode="none"
            key="field_name"
            label="Field name"
            placeholder="Select option"
            position="center"
            size={92}
            summaryAggregationMode="none"
            valueOverride="{{ _.startCase(item) }}"
          />
          <Column
            id="f7d63"
            alignment="left"
            format="tag"
            formatOptions={{ automaticColors: true }}
            groupAggregationMode="none"
            key="match_type"
            label="Match type"
            placeholder="Select option"
            position="center"
            size={91}
            summaryAggregationMode="none"
            valueOverride="{{ _.startCase(item) }}"
          />
          <Column
            id="0cbe3"
            alignment="left"
            format="string"
            groupAggregationMode="none"
            key="match_value"
            label="Match value"
            placeholder="Enter value"
            position="center"
            size={156}
            summaryAggregationMode="none"
          />
          <Column
            id="5cda1"
            alignment="left"
            format="string"
            groupAggregationMode="none"
            key="substitution_value"
            label="Substitution value"
            placeholder="Enter value"
            position="center"
            size={119.359375}
            summaryAggregationMode="none"
          />
          <Action id="3fbf6" icon="bold/interface-edit-pencil" label="Edit">
            <Event
              event="clickAction"
              method="setValue"
              params={{ ordered: [{ value: "{{ currentSourceRow }}" }] }}
              pluginId="IntegrationRuleSelected"
              type="state"
              waitMs="0"
              waitType="debounce"
            />
            <Event
              event="clickAction"
              method="show"
              params={{ ordered: [] }}
              pluginId="modalFrame3"
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
              pluginId="table14"
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
              pluginId="table14"
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
              pluginId="IntegrationRuleSelected"
              type="state"
              waitMs="0"
              waitType="debounce"
            />
            <Event
              event="clickToolbar"
              method="show"
              params={{ ordered: [] }}
              pluginId="modalFrame3"
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
      id="group7"
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
          id="table15"
          actionsOverflowPosition={1}
          cellSelection="none"
          clearChangesetOnSave={true}
          data="{{ SubstituteRule_get.data }}"
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
            size={30.765625}
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
            id="a4b02"
            alignment="left"
            format="tag"
            formatOptions={{ automaticColors: true }}
            groupAggregationMode="none"
            key="model_name"
            label="Model name"
            placeholder="Select option"
            position="center"
            size={85.703125}
            summaryAggregationMode="none"
            valueOverride="{{ _.startCase(item) }}"
          />
          <Column
            id="84166"
            alignment="left"
            format="tag"
            formatOptions={{ automaticColors: true }}
            groupAggregationMode="none"
            key="field_name"
            label="Field name"
            placeholder="Select option"
            position="center"
            size={77.765625}
            summaryAggregationMode="none"
            valueOverride="{{ _.startCase(item) }}"
          />
          <Column
            id="3608c"
            alignment="left"
            format="tag"
            formatOptions={{ automaticColors: true }}
            groupAggregationMode="none"
            key="match_type"
            label="Match type"
            placeholder="Select option"
            position="center"
            size={80.25}
            summaryAggregationMode="none"
            valueOverride="{{ _.startCase(item) }}"
          />
          <Column
            id="43308"
            alignment="left"
            format="string"
            groupAggregationMode="none"
            key="match_value"
            label="Match value"
            placeholder="Enter value"
            position="center"
            size={509.8125}
            summaryAggregationMode="none"
          />
          <Column
            id="4e1fb"
            alignment="right"
            editableOptions={{ showStepper: true }}
            format="decimal"
            formatOptions={{ showSeparators: true, notation: "standard" }}
            groupAggregationMode="sum"
            key="substitution_value"
            label="Substitution value"
            placeholder="Enter value"
            position="center"
            size={117.71875}
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
              pluginId="table15"
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
              pluginId="table15"
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
      id="group8"
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
          id="table16"
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
              pluginId="table16"
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
              pluginId="table16"
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
          id="TimeTrackingForm2"
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
              id="formTitle15"
              value={
                '#### {{ timetracking_selected.value === "" ? "Novo" : "Editar" }} Time Tracking'
              }
              verticalAlign="center"
            />
          </Header>
          <Body>
            <Select
              id="select15"
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
              id="Date10"
              dateFormat="MMM d, yyyy"
              datePlaceholder="{{ self.dateFormat.toUpperCase() }}"
              formDataKey="month_date"
              iconBefore="bold/interface-calendar"
              label="Data"
              labelPosition="top"
              value="{{ timetracking_selected.value[self.formDataKey] }}"
            />
            <Divider id="divider9" />
            <Date
              id="Date11"
              dateFormat="MMM d, yyyy"
              datePlaceholder="{{ self.dateFormat.toUpperCase() }}"
              formDataKey="month"
              iconBefore="bold/interface-calendar"
              label="Início Férias"
              labelPosition="top"
              value="{{ timetracking_selected.value[self.formDataKey] }}"
            />
            <Date
              id="Date12"
              dateFormat="MMM d, yyyy"
              datePlaceholder="{{ self.dateFormat.toUpperCase() }}"
              formDataKey="month"
              iconBefore="bold/interface-calendar"
              label="Fim Férias"
              labelPosition="top"
              value="{{ timetracking_selected.value[self.formDataKey] }}"
            />
            <NumberInput
              id="numberInput60"
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
              id="numberInput62"
              currency="USD"
              inputValue={0}
              label="Férias Vendidas"
              labelPosition="top"
              placeholder="Enter value"
              showSeparators={true}
              showStepper={true}
              value={0}
            />
            <Divider id="divider8" />
            <NumberInput
              id="numberInput54"
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
              id="numberInput55"
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
              id="numberInput58"
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
            <Divider id="divider7" />
            <NumberInput
              id="numberInput57"
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
              id="numberInput56"
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
              id="numberInput59"
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
              id="numberInput61"
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
              value="{{ numberInput38.value - numberInput59.value }}"
            />
            <TextInput
              id="textInput11"
              labelPosition="top"
              placeholder="Enter value"
              value="{{ select15.value }}"
            />
          </Body>
          <Footer>
            <Button
              id="NewButton7"
              hidden={'{{ timetracking_selected.value !== "" }}'}
              submitTargetId="TimeTrackingForm2"
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
              id="EditButton7"
              hidden={'{{ timetracking_selected.value === "" }}'}
              submit={true}
              submitTargetId="TimeTrackingForm2"
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
      id="group9"
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
          id="table18"
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
              pluginId="table18"
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
              pluginId="table18"
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
          id="RecurringAdjustmentForm2"
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
              id="formTitle16"
              value={
                '#### {{ recurring_adjustment_selected.value === "" ? "Novo" : "Editar" }} Ajuste'
              }
              verticalAlign="center"
            />
          </Header>
          <Body>
            <TextInput
              id="textInput12"
              formDataKey="name"
              label="Nome do Ajuste"
              labelPosition="top"
              placeholder="Enter value"
              value="{{ recurring_adjustment_selected.value[self.formDataKey] }}"
            />
            <Select
              id="select16"
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
              id="Date13"
              dateFormat="MMM d, yyyy"
              datePlaceholder="{{ self.dateFormat.toUpperCase() }}"
              formDataKey="start_date"
              iconBefore="bold/interface-calendar"
              label="Data Início"
              labelPosition="top"
              value="{{ recurring_adjustment_selected.value[self.formDataKey] }}"
            />
            <Date
              id="Date14"
              dateFormat="MMM d, yyyy"
              datePlaceholder="{{ self.dateFormat.toUpperCase() }}"
              formDataKey="end_date"
              iconBefore="bold/interface-calendar"
              label="Data Fim"
              labelPosition="top"
              value="{{ recurring_adjustment_selected.value[self.formDataKey] }}"
            />
            <Select
              id="select17"
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
              id="checkbox10"
              formDataKey="base_for_inss"
              label="Impacta INSS"
              labelWidth="100"
              value="{{ recurring_adjustment_selected.value[self.formDataKey] }}"
            />
            <Checkbox
              id="checkbox11"
              formDataKey="base_for_fgts"
              label="Impacta FGTS"
              labelWidth="100"
              value="{{ recurring_adjustment_selected.value[self.formDataKey] }}"
            />
            <Checkbox
              id="checkbox12"
              formDataKey="base_for_irpf"
              label="Impacta IRRF"
              labelWidth="100"
              value="{{ recurring_adjustment_selected.value[self.formDataKey] }}"
            />
            <Divider id="divider10" />
            <TagsWidget2
              id="tags2"
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
                  ordered: [{ value: "{{ textArea4.value }}[{{ item }}]" }],
                }}
                pluginId="textArea4"
                type="widget"
                waitMs="0"
                waitType="debounce"
              />
              <Event
                event="click"
                method="focus"
                params={{ ordered: [] }}
                pluginId="textArea4"
                type="widget"
                waitMs="0"
                waitType="debounce"
              />
            </TagsWidget2>
            <TextArea
              id="textArea4"
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
              id="NewButton8"
              hidden={'{{ recurring_adjustment_selected.value !== "" }}'}
              submitTargetId="RecurringAdjustmentForm2"
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
              id="EditButton8"
              hidden={'{{ recurring_adjustment_selected.value === "" }}'}
              submit={true}
              submitTargetId="RecurringAdjustmentForm2"
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
      id="table17"
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
          pluginId="table17"
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
          pluginId="table17"
          type="widget"
          waitMs="0"
          waitType="debounce"
        />
      </ToolbarButton>
    </Table>
  </View>
</Container>
