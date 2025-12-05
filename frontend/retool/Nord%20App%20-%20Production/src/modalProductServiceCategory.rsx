<ModalFrame
  id="modalProductServiceCategory"
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
      id="modalCloseButton28"
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
        pluginId="modalProductServiceCategory"
        type="widget"
        waitMs="0"
        waitType="debounce"
      />
    </Button>
    <Text
      id="modalTitle26"
      value={
        '#### {{ product_service_categories_mode.value !== "edit"  ? "Nova" : "Editar" }} Categoria Produto ou Serviço'
      }
      verticalAlign="center"
    />
  </Header>
  <Body>
    <Form
      id="ProductServiceCategoryForm"
      footerPadding="4px 12px"
      headerPadding="4px 12px"
      initialData="{{ product_service_categories_selected.value && product_service_categories_selected.value ? product_service_categories_selected.value : null }}"
      padding="12px"
      requireValidation={true}
      resetAfterSubmit={true}
      scroll={true}
      showBody={true}
    >
      <TextInput
        id="nameInput14"
        formDataKey="name"
        label="Name"
        labelPosition="top"
        placeholder="Enter value"
        required={true}
      />
      <Select
        id="companyInput10"
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
        value="{{ product_service_categories_selected.value && product_service_categories_selected.value ? product_service_categories_selected.value : ClienteDropDown.selectedItem.id }}"
        values="{{ item.id }}"
      />
      <Select
        id="parentInput2"
        data="{{ product_service_categories_get.data }}"
        emptyMessage="No options"
        formDataKey="parent"
        label="Parent"
        labelPosition="top"
        labels="{{ item.name }}"
        overlayMaxHeight={375}
        placeholder="Select an option"
        showSelectionIndicator={true}
        values="{{ item.id }}"
      />
      <Checkbox
        id="isDeletedInput3"
        formDataKey="is_deleted"
        label="Is deleted"
        labelWidth="100"
        required={true}
      />
    </Form>
  </Body>
  <Footer>
    <Button
      id="button32"
      hidden={'{{ product_service_categories_mode.value !== "edit" }}'}
      text="Edit"
    >
      <Event
        event="click"
        method="run"
        params={{
          map: {
            src: 'product_service_categories_edit.trigger({\n  onSuccess: function(response) {\n    console.log("✅ Success");\n  },\n\n  onFailure: function(error) {\n    console.log("❌ Validation error");\n\n    const errors = error.data.data || {};\n\n    ProductServiceCategoryForm.fields.forEach(field => {\n      const fieldKey = field.formDataKey;\n\n      if (errors[fieldKey]) {\n        field.setValidationMessage(errors[fieldKey][0]);\n      } else {\n        field.setValidationMessage(\'\');\n      }\n    });\n  }\n});\n',
          },
        }}
        pluginId=""
        type="script"
        waitMs="0"
        waitType="debounce"
      />
    </Button>
    <Button
      id="button33"
      hidden={'{{ product_service_categories_mode.value !== "new" }}'}
      text="Submit"
    >
      <Event
        event="click"
        method="trigger"
        params={{}}
        pluginId="product_service_categories_new"
        type="datasource"
        waitMs="0"
        waitType="debounce"
      />
    </Button>
  </Footer>
</ModalFrame>
