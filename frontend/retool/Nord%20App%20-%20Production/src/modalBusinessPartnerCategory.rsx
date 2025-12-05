<ModalFrame
  id="modalBusinessPartnerCategory"
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
      id="modalTitle24"
      value={
        '#### {{ business_partner_categories_mode.value !== "edit"  ? "Nova" : "Editar" }} Categoria Parceiro'
      }
      verticalAlign="center"
    />
    <Button
      id="modalCloseButton26"
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
        pluginId="modalBusinessPartnerCategory"
        type="widget"
        waitMs="0"
        waitType="debounce"
      />
    </Button>
  </Header>
  <Body>
    <Form
      id="BusinessPartnerCategoryForm"
      footerPadding="4px 12px"
      headerPadding="4px 12px"
      initialData="{{ table40.selectedRow }}"
      padding="12px"
      requireValidation={true}
      resetAfterSubmit={true}
      scroll={true}
      showBody={true}
      showFooter={true}
    >
      <Header>
        <Text
          id="formTitle27"
          value={
            '#### {{ business_partner_categories_selected.value === "" ? "Nova" : "Editar" }} Entidade'
          }
          verticalAlign="center"
        />
      </Header>
      <Body>
        <Select
          id="parentInput"
          data="{{ business_partner_categories_get.data }}"
          emptyMessage="No options"
          formDataKey="parent"
          label="Parent"
          labelPosition="top"
          labels="{{ item.name }}"
          overlayMaxHeight={375}
          placeholder="Select an option"
          showSelectionIndicator={true}
          value="{{ business_partner_categories_selected.value && business_partner_categories_selected.value[self.formDataKey] ? business_partner_categories_selected.value[self.formDataKey] : null }}"
          values="{{ item.id }}"
        />
        <Select
          id="companyInput8"
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
          value="{{ business_partner_categories_selected.value && business_partner_categories_selected.value[self.formDataKey] ? business_partner_categories_selected.value[self.formDataKey].id : null }}"
          values="{{ item.id }}"
        />
        <TextInput
          id="nameInput12"
          formDataKey="name"
          label="Name"
          labelPosition="top"
          placeholder="Enter value"
          required={true}
          value="{{ business_partner_categories_selected.value && business_partner_categories_selected.value[self.formDataKey] ? business_partner_categories_selected.value[self.formDataKey] : null }}"
        />
      </Body>
      <Footer>
        <Button
          id="NewButton17"
          hidden={'{{ business_partner_categories_mode.value !== "new" }}'}
          submitTargetId="BusinessPartnerCategoryForm"
          text="Submit"
        >
          <Event
            event="click"
            method="trigger"
            params={{ ordered: [] }}
            pluginId="business_partner_categories_new"
            type="datasource"
            waitMs="0"
            waitType="debounce"
          />
        </Button>
        <Button
          id="EditButton17"
          hidden={'{{ business_partner_categories_mode.value !== "edit" }}'}
          submit={true}
          submitTargetId="BusinessPartnerCategoryForm"
          text="Edit"
        />
      </Footer>
      <Event
        event="submit"
        method="trigger"
        params={{}}
        pluginId="business_partner_categories_edit"
        type="datasource"
        waitMs="0"
        waitType="debounce"
      />
    </Form>
  </Body>
</ModalFrame>
