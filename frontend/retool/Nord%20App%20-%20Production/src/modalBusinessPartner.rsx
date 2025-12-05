<ModalFrame
  id="modalBusinessPartner"
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
      id="modalTitle30"
      value={
        '#### {{ business_partner_mode.value !== "edit"  ? "Novo" : "Editar" }} Parceiro'
      }
      verticalAlign="center"
    />
    <Button
      id="modalCloseButton32"
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
        pluginId="modalBusinessPartner"
        type="widget"
        waitMs="0"
        waitType="debounce"
      />
    </Button>
  </Header>
  <Body>
    <Form
      id="BusinessPartnerForm"
      footerPadding="4px 12px"
      headerPadding="4px 12px"
      initialData="{{ business_partner_selected.value && business_partner_selected.value ? business_partner_selected.value : null }}"
      padding="12px"
      requireValidation={true}
      resetAfterSubmit={true}
      scroll={true}
      showBody={true}
    >
      <TextInput
        id="nameInput13"
        formDataKey="name"
        label="Name"
        labelPosition="top"
        placeholder="Enter value"
        required={true}
      />
      <Select
        id="categoryInput"
        data="{{ business_partner_categories_get.data }}"
        emptyMessage="No options"
        formDataKey="category"
        label="Category"
        labelPosition="top"
        labels={null}
        overlayMaxHeight={375}
        placeholder="Select an option"
        required={true}
        showSelectionIndicator={true}
        value="{{ business_partner_selected.value && business_partner_selected.value[self.formDataKey] ? business_partner_selected.value[self.formDataKey] : null }}"
        values={null}
      />
      <Select
        id="partnerTypeInput"
        emptyMessage="No options"
        formDataKey="partner_type"
        itemMode="static"
        label="Partner type"
        labelPosition="top"
        labels={null}
        overlayMaxHeight={375}
        placeholder="Select an option"
        required={true}
        showSelectionIndicator={true}
        values={null}
      >
        <Option id="00030" label="Cliente" value="client" />
        <Option id="00031" label="Fornecedor" value="vendor" />
      </Select>
      <NumberInput
        id="identifierInput"
        currency="USD"
        formDataKey="identifier"
        inputValue={0}
        label="Identifier"
        labelPosition="top"
        placeholder="Enter value"
        required={true}
        showSeparators={true}
        showStepper={true}
        value={0}
      />
      <Select
        id="countryInput2"
        emptyMessage="No options"
        formDataKey="country"
        itemMode="static"
        label="Country"
        labelPosition="top"
        labels={null}
        overlayMaxHeight={375}
        placeholder="Select an option"
        required={true}
        showSelectionIndicator={true}
        value="Brazil"
        values={null}
      >
        <Option id="00030" value="Brazil" />
      </Select>
      <TextInput
        id="addressInput"
        formDataKey="address"
        label="Address"
        labelPosition="top"
        placeholder="Enter value"
      />
      <TextInput
        id="cityInput"
        formDataKey="city"
        label="City"
        labelPosition="top"
        placeholder="Enter value"
      />
      <TextInput
        id="stateInput"
        formDataKey="state"
        label="State"
        labelPosition="top"
        placeholder="Enter value"
      />
      <TextInput
        id="zipcodeInput"
        formDataKey="zipcode"
        label="Zipcode"
        labelPosition="top"
        placeholder="Enter value"
      />
      <TextInput
        id="emailInput"
        formDataKey="email"
        iconBefore="bold/mail-send-envelope"
        label="Email"
        labelPosition="top"
        patternType="email"
        placeholder="you@example.com"
      />
      <TextInput
        id="paymentTermsInput"
        formDataKey="payment_terms"
        label="Payment terms"
        labelPosition="top"
        placeholder="Enter value"
      />
      <Select
        id="companyInput9"
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
        value="{{ ClienteDropDown.selectedItem.id  }}"
        values="{{ item.id }}"
      />
      <Checkbox
        id="isActiveInput3"
        formDataKey="is_active"
        label="Is active"
        labelWidth="100"
        required={true}
        value="true"
      />
      <TextInput
        id="phoneInput"
        formDataKey="phone"
        label="Phone"
        labelPosition="top"
        placeholder="Enter value"
      />
      <Select
        id="currencyInput5"
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
        value="{{ business_partner_selected.value && business_partner_selected.value[self.formDataKey] ? business_partner_selected.value[self.formDataKey] : null }}"
        values="{{ item.id }}"
      />
      <Checkbox
        id="isDeletedInput2"
        formDataKey="is_deleted"
        label="Is deleted"
        labelWidth="100"
        required={true}
      />
    </Form>
  </Body>
  <Footer>
    <Button
      id="button34"
      hidden={'{{ business_partner_mode.value !== "edit" }}'}
      text="Edit"
    >
      <Event
        event="click"
        method="trigger"
        params={{
          map: {
            options: {
              object: {
                onSuccess: null,
                onFailure: null,
                additionalScope: null,
              },
            },
          },
        }}
        pluginId="business_partner_edit"
        type="datasource"
        waitMs="0"
        waitType="debounce"
      />
    </Button>
    <Button
      id="button35"
      hidden={'{{ business_partner_mode.value !== "new" }}'}
      text="Submit"
    >
      <Event
        event="click"
        method="trigger"
        params={{}}
        pluginId="business_partner_new"
        type="datasource"
        waitMs="0"
        waitType="debounce"
      />
    </Button>
  </Footer>
</ModalFrame>
