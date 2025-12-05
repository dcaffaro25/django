<ModalFrame
  id="modalAccount"
  footerPadding="8px 12px"
  headerPadding="8px 12px"
  hidden={true}
  hideOnEscape={true}
  isHiddenOnMobile={true}
  overlayInteraction={true}
  padding="8px 12px"
  showFooter={true}
  showHeader={true}
  showOverlay={true}
  size="medium"
>
  <Header>
    <Text
      id="modalTitle15"
      value={
        '#### {{ account_mode.value !== "edit" ? "Nova" : "Editar" }} Conta Contábil'
      }
      verticalAlign="center"
    />
    <Button
      id="modalCloseButton17"
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
        pluginId="modalAccount"
        type="widget"
        waitMs="0"
        waitType="debounce"
      />
    </Button>
  </Header>
  <Body>
    <Form
      id="AccountForm"
      footerPadding="4px 12px"
      headerPadding="4px 12px"
      initialData=""
      padding="12px"
      requireValidation={true}
      resetAfterSubmit={true}
      scroll={true}
      showBody={true}
    >
      <Select
        id="companyInput3"
        data="{{ clientes.data }}"
        disabled="true"
        emptyMessage="No options"
        formDataKey="company"
        label="Company"
        labelPosition="top"
        labels="{{ item.name }}"
        overlayMaxHeight={375}
        placeholder="Select an option"
        required={true}
        showSelectionIndicator={true}
        value="{{ ClienteDropDown.selectedItem.id }}"
        values="{{ item.id }}"
      />
      <TextInput
        id="nameInput3"
        formDataKey="name"
        label="Name"
        labelPosition="top"
        placeholder="Enter value"
        required={true}
        value="{{ account_selected.value && account_selected.value[self.formDataKey] ? account_selected.value[self.formDataKey] : null }}"
      />
      <Select
        id="parentIdInput2"
        data="{{ account_get.data }}"
        emptyMessage="No options"
        formDataKey="parent"
        label="Parent"
        labelPosition="top"
        labels="{{ item.path }}"
        overlayMaxHeight={375}
        placeholder="Select an option"
        showSelectionIndicator={true}
        value="{{ account_selected.value.parent_id }}"
        values="{{ item.id }}"
      />
      <Select
        id="accountDirectionInput"
        emptyMessage="No options"
        formDataKey="account_direction"
        itemMode="static"
        label="Account direction"
        labelPosition="top"
        labels={null}
        overlayMaxHeight={375}
        placeholder="Select an option"
        required={true}
        showSelectionIndicator={true}
        value="{{ account_selected.value && account_selected.value[self.formDataKey] ? account_selected.value[self.formDataKey] : null }}"
        values={null}
      >
        <Option id="1f235" value="1" />
        <Option id="7f59c" value="-1" />
      </Select>
      <NumberInput
        id="accountCodeInput"
        currency="USD"
        formDataKey="account_code"
        inputValue={0}
        label="Account code"
        labelPosition="top"
        placeholder="Enter value"
        required={true}
        showSeparators={true}
        showStepper={true}
        value="{{ account_selected.value && account_selected.value[self.formDataKey] ? account_selected.value[self.formDataKey] : null }}"
      />
      <Select
        id="currencyInput2"
        data="{{ currencies.data }}"
        emptyMessage="No options"
        formDataKey="currency"
        label="Currency"
        labelPosition="top"
        labels="{{ item.code }}"
        overlayMaxHeight={375}
        placeholder="Select an option"
        required={true}
        showSelectionIndicator={true}
        value="{{ account_selected.value && account_selected.value[self.formDataKey] ? account_selected.value[self.formDataKey].id : null }}"
        values="{{ item.id }}"
      />
      <NumberInput
        id="balanceInput2"
        currency="USD"
        formDataKey="balance"
        inputValue={0}
        label="Balance"
        labelPosition="top"
        placeholder="Enter value"
        required={true}
        showSeparators={true}
        showStepper={true}
        value="{{ account_selected.value && account_selected.value[self.formDataKey] ? account_selected.value[self.formDataKey] : null }}"
      />
      <Date
        id="date15"
        dateFormat="yyyy-MM-dd"
        datePlaceholder="{{ self.dateFormat.toUpperCase() }}"
        formDataKey="balance_date"
        iconBefore="bold/interface-calendar"
        label="Balance Date"
        labelPosition="top"
        required={true}
        value="{{ account_selected.value && account_selected.value[self.formDataKey] ? account_selected.value[self.formDataKey] : null }}"
      />
      <Select
        id="selectBankAccount"
        data="{{ bankaccount_get.data }}"
        emptyMessage="No options"
        formDataKey="bank_account"
        label="Bank Account"
        labelPosition="top"
        labels="{{ item.name }} - {{ item.bank.name }} ({{ item.account_number }})"
        overlayMaxHeight={375}
        placeholder="Select an option"
        showClear={true}
        showSelectionIndicator={true}
        value="{{ account_selected.value && account_selected.value[self.formDataKey] ? account_selected.value[self.formDataKey].id : null }}"
        values="{{ item.id }}"
      />
      <TextArea
        id="textArea9"
        formDataKey="description"
        label="Description"
        labelPosition="top"
        minLines="3"
        placeholder="Enter value"
        value="{{ account_selected.value && account_selected.value[self.formDataKey] ? account_selected.value[self.formDataKey] : null }}"
      />
      <TextArea
        id="textArea11"
        formDataKey="key_words"
        label="Key Words"
        labelPosition="top"
        minLines="3"
        placeholder="Enter value"
        value="{{ account_selected.value && account_selected.value[self.formDataKey] ? account_selected.value[self.formDataKey] : null }}"
      />
      <TextArea
        id="textArea10"
        formDataKey="examples"
        label="Examples"
        labelPosition="top"
        minLines="3"
        placeholder="Enter value"
        value="{{ account_selected.value && account_selected.value[self.formDataKey] ? account_selected.value[self.formDataKey] : null }}"
      />
      <Checkbox
        id="isActiveInput"
        formDataKey="is_active"
        label="Is active"
        labelWidth="100"
        value="{{ account_selected.value && account_selected.value[self.formDataKey] ? account_selected.value[self.formDataKey] : true }}"
      />
      <Event
        event="submit"
        method="trigger"
        params={{}}
        pluginId="account_edit"
        type="datasource"
        waitMs="0"
        waitType="debounce"
      />
    </Form>
  </Body>
  <Footer>
    <Button
      id="NewButton15"
      hidden={'{{ account_mode.value !== "new" }}'}
      submitTargetId="AccountForm"
      text="Submit"
    >
      <Event
        event="click"
        method="trigger"
        params={{ ordered: [] }}
        pluginId="account_new"
        type="datasource"
        waitMs="0"
        waitType="debounce"
      />
    </Button>
    <Button
      id="EditButton15"
      hidden={'{{ account_mode.value !== "edit" }}'}
      submit={true}
      submitTargetId="AccountForm"
      text="Edit"
    />
  </Footer>
</ModalFrame>
