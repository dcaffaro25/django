<ModalFrame
  id="modalContract"
  footerPadding="8px 12px"
  headerPadding="8px 12px"
  hidden={true}
  hideOnEscape={true}
  isHiddenOnMobile={true}
  overlayInteraction={true}
  padding="8px 12px"
  showHeader={true}
  showOverlay={true}
  size="medium"
>
  <Header>
    <Text
      id="modalTitle29"
      value={
        '#### {{ contract_mode.value !== "edit" ? "Novo" : "Editar" }} Contrato'
      }
      verticalAlign="center"
    />
    <Button
      id="modalCloseButton31"
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
        pluginId="modalContract"
        type="widget"
        waitMs="0"
        waitType="debounce"
      />
    </Button>
  </Header>
  <Body>
    <Form
      id="ContractForm"
      footerPadding="4px 12px"
      headerPadding="4px 12px"
      initialData="{{ contract_selected.value ? contract_selected.value : null }}"
      padding="12px"
      requireValidation={true}
      resetAfterSubmit={true}
      scroll={true}
      showBody={true}
      showFooter={true}
    >
      <Body>
        <Select
          id="companyInput12"
          data="{{ clientes.data }}"
          emptyMessage="No options"
          formDataKey="company"
          label="Company"
          labelPosition="top"
          labels="{{ item.name }}"
          overlayMaxHeight={375}
          placeholder="Select an option"
          required={true}
          showSelectionIndicator={true}
          value="{{ contract_selected.value ? contract_selected.value[self.formDataKey] : ClienteDropDown.selectedItem.id }}"
          values="{{ item.id }}"
        />
        <Select
          id="partnerInput"
          captionByIndex="{{ item.email }}"
          data="{{ business_partner_get.data }}"
          emptyMessage="No options"
          formDataKey="partner"
          label="Partner"
          labelPosition="top"
          labels="{{ item.name }}"
          overlayMaxHeight={375}
          placeholder="Select an option"
          required={true}
          showSelectionIndicator={true}
          value="{{ contract_selected.value ? contract_selected.value[self.formDataKey].id : null }}"
          values="{{ item.id }}"
        />
        <NumberInput
          id="contractNumberInput"
          currency="USD"
          formDataKey="contract_number"
          inputValue={0}
          label="Contract number"
          labelPosition="top"
          placeholder="Enter value"
          required={true}
          showSeparators={true}
          showStepper={true}
          value={0}
        />
        <TextInput
          id="descriptionInput4"
          formDataKey="description"
          label="Description"
          labelPosition="top"
          placeholder="Enter value"
        />
        <Date
          id="startDateInput"
          dateFormat="MMM d, yyyy"
          datePlaceholder="{{ self.dateFormat.toUpperCase() }}"
          formDataKey="start_date"
          iconBefore="bold/interface-calendar"
          label="Start date"
          labelPosition="top"
          required={true}
          value="{{ contract_selected.value ? contract_selected.value[self.formDataKey] : new Date() }}"
        />
        <Date
          id="endDateInput"
          dateFormat="MMM d, yyyy"
          datePlaceholder="{{ self.dateFormat.toUpperCase() }}"
          formDataKey="end_date"
          iconBefore="bold/interface-calendar"
          label="End date"
          labelPosition="top"
          value="{{ contract_selected.value ? contract_selected.value[self.formDataKey] : new Date() }}"
        />
        <TextInput
          id="recurrenceRuleInput"
          formDataKey="recurrence_rule"
          label="Recurrence rule"
          labelPosition="top"
          placeholder="Enter value"
        />
        <Select
          id="adjustmentIndexInput"
          emptyMessage="No options"
          formDataKey="adjustment_index"
          label="Adjustment index"
          labelPosition="top"
          labels={null}
          overlayMaxHeight={375}
          placeholder="Select an option"
          showSelectionIndicator={true}
          values={null}
        >
          <Option id="00030" value="Option 1" />
          <Option id="00031" value="Option 2" />
          <Option id="00032" value="Option 3" />
        </Select>
        <NumberInput
          id="baseValueInput"
          currency="USD"
          formDataKey="base_value"
          inputValue={0}
          label="Base value"
          labelPosition="top"
          placeholder="Enter value"
          required={true}
          showSeparators={true}
          showStepper={true}
          value={0}
        />
        <TextInput
          id="baseIndexDateInput"
          formDataKey="base_index_date"
          label="Base index date"
          labelPosition="top"
          placeholder="Enter value"
        />
        <TextInput
          id="adjustmentFrequencyInput"
          formDataKey="adjustment_frequency"
          label="Adjustment frequency"
          labelPosition="top"
          placeholder="Enter value"
        />
        <TextInput
          id="adjustmentCapInput"
          formDataKey="adjustment_cap"
          label="Adjustment cap"
          labelPosition="top"
          placeholder="Enter value"
        />
        <Checkbox
          id="isActiveInput5"
          formDataKey="is_active"
          label="Is active"
          labelWidth="100"
          required={true}
        />
      </Body>
      <Footer>
        <Button
          id="NewButton19"
          hidden={'{{ contract_mode.value !== "new" }}'}
          submitTargetId="ContractForm"
          text="Submit"
        >
          <Event
            event="click"
            method="trigger"
            params={{ ordered: [] }}
            pluginId="contract_new"
            type="datasource"
            waitMs="0"
            waitType="debounce"
          />
        </Button>
        <Button
          id="EditButton19"
          hidden={'{{ contract_mode.value !== "edit" }}'}
          submit={true}
          submitTargetId="ContractForm"
          text="Edit"
        />
      </Footer>
    </Form>
  </Body>
</ModalFrame>
