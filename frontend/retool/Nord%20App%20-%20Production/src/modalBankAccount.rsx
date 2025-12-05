<ModalFrame
  id="modalBankAccount"
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
    <Button
      id="modalCloseButton15"
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
        pluginId="modalBankAccount"
        type="widget"
        waitMs="0"
        waitType="debounce"
      />
    </Button>
    <Text
      id="modalTitle13"
      value={
        '#### {{ bankaccount_mode.value !== "edit"  ? "Nova" : "Editar" }} Conta Bancária'
      }
      verticalAlign="center"
    />
  </Header>
  <Body>
    <Form
      id="BankAccountForm"
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
        id="entityInput"
        data="{{ entities_get.data }}"
        emptyMessage="No options"
        formDataKey="entity"
        label="Entity"
        labelPosition="top"
        labels="{{ item.path }}"
        overlayMaxHeight={375}
        placeholder="Select an option"
        required={true}
        showSelectionIndicator={true}
        value="{{ bankaccount_selected.value && bankaccount_selected.value[self.formDataKey] ? bankaccount_selected.value[self.formDataKey].id : null }}"
        values="{{ item.id }}"
      />
      <Select
        id="accountTypeInput"
        emptyMessage="No options"
        formDataKey="account_type"
        itemMode="static"
        label="Account type"
        labelPosition="top"
        labels={null}
        overlayMaxHeight={375}
        placeholder="Select an option"
        required={true}
        showSelectionIndicator={true}
        value="{{ bankaccount_selected.value[self.formDataKey] ? bankaccount_selected.value[self.formDataKey] : null }}
"
        values={null}
      >
        <Option id="63f85" value="cash" />
        <Option id="3dd00" value="Option 2" />
        <Option id="d63b4" value="Option 3" />
      </Select>
      <TextInput
        id="nameInput2"
        formDataKey="name"
        label="Name"
        labelPosition="top"
        placeholder="Enter value"
        required={true}
        value="{{ bankaccount_selected.value[self.formDataKey] }}"
      />
      <Select
        id="currencyInput"
        data="{{ currencies.data }}"
        emptyMessage="No options"
        formDataKey="currency"
        label="Currency"
        labelPosition="top"
        labels="{{ item.name }}"
        overlayMaxHeight={375}
        placeholder="Select an option"
        required={true}
        showSelectionIndicator={true}
        value="{{ bankaccount_selected.value && bankaccount_selected.value[self.formDataKey] ? bankaccount_selected.value[self.formDataKey].id : null }}"
        values="{{ item.id }}"
      />
      <Select
        id="bankInput"
        data="{{ bank_get.data }}"
        emptyMessage="No options"
        formDataKey="bank"
        label="Bank"
        labelPosition="top"
        labels="{{ item.name }}"
        overlayMaxHeight={375}
        placeholder="Select an option"
        required={true}
        showSelectionIndicator={true}
        value="{{ bankaccount_selected.value[self.formDataKey] ? bankaccount_selected.value[self.formDataKey].id : null }}"
        values="{{ item.id }}"
      />
      <NumberInput
        id="branchIdInput"
        currency="USD"
        formDataKey="branch_id"
        inputValue={0}
        label="Branch ID"
        labelPosition="top"
        placeholder="Enter value"
        required={true}
        showSeparators={true}
        showStepper={true}
        value="{{ bankaccount_selected.value[self.formDataKey] }}"
      />
      <NumberInput
        id="accountNumberInput"
        currency="USD"
        formDataKey="account_number"
        inputValue={0}
        label="Account number"
        labelPosition="top"
        placeholder="Enter value"
        required={true}
        showSeparators={true}
        showStepper={true}
        value="{{ bankaccount_selected.value[self.formDataKey] }}"
      />
      <Date
        id="balanceDateInput"
        dateFormat="yyyy-MM-dd"
        datePlaceholder="{{ self.dateFormat.toUpperCase() }}"
        formDataKey="balance_date"
        iconBefore="bold/interface-calendar"
        label="Balance date"
        labelPosition="top"
        required={true}
        value="{{ bankaccount_selected.value[self.formDataKey] }}"
      />
      <NumberInput
        id="balanceInput"
        currency="USD"
        formDataKey="balance"
        inputValue={0}
        label="Balance"
        labelPosition="top"
        placeholder="Enter value"
        showSeparators={true}
        showStepper={true}
        value="{{ bankaccount_selected.value[self.formDataKey] }}"
      />
      <Select
        id="companyInput2"
        data="{{ clientes.data }}"
        emptyMessage="No options"
        formDataKey="company"
        hidden="true"
        hiddenByIndex=""
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
    </Form>
  </Body>
  <Footer>
    <Button
      id="button26"
      hidden={'{{ bankaccount_mode.value !== "edit" }}'}
      text="Edit"
    >
      <Event
        event="click"
        method="run"
        params={{
          map: {
            src: 'bankaccount_edit.trigger({\n  onSuccess: function(response) {\n    console.log("✅ Success");\n  },\n\n  onFailure: function(error) {\n    console.log("❌ Validation error");\n\n    const errors = error.data.data || {};\n\n    BankAccountForm.fields.forEach(field => {\n      const fieldKey = field.formDataKey;\n\n      if (errors[fieldKey]) {\n        field.setValidationMessage(errors[fieldKey][0]);\n      } else {\n        field.setValidationMessage(\'\');\n      }\n    });\n  }\n});\n',
          },
        }}
        pluginId=""
        type="script"
        waitMs="0"
        waitType="debounce"
      />
    </Button>
    <Button
      id="button27"
      hidden={'{{ bankaccount_mode.value !== "new" }}'}
      text="Submit"
    >
      <Event
        event="click"
        method="trigger"
        params={{}}
        pluginId="bankaccount_new"
        type="datasource"
        waitMs="0"
        waitType="debounce"
      />
    </Button>
  </Footer>
</ModalFrame>
