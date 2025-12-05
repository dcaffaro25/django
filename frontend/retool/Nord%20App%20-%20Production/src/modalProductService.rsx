<ModalFrame
  id="modalProductService"
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
      id="modalTitle28"
      value={
        '#### {{ product_service_mode.value !== "edit" ? "Novo" : "Editar" }} Produto ou Serviço'
      }
      verticalAlign="center"
    />
    <Button
      id="modalCloseButton30"
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
        pluginId="modalProductService"
        type="widget"
        waitMs="0"
        waitType="debounce"
      />
    </Button>
  </Header>
  <Body>
    <Form
      id="ProductServiceForm"
      footerPadding="4px 12px"
      headerPadding="4px 12px"
      initialData="{{ product_service_selected.value && product_service_selected.value ? product_service_selected.value : null }}"
      padding="12px"
      requireValidation={true}
      resetAfterSubmit={true}
      scroll={true}
      showBody={true}
      showFooter={true}
    >
      <Body>
        <Select
          id="companyInput11"
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
          value="{{ product_service_selected.value && product_service_selected.value ? product_service_selected.value : ClienteDropDown.selectedItem.id }}"
          values="{{ item.id }}"
        />
        <TextInput
          id="nameInput15"
          formDataKey="name"
          label="Name"
          labelPosition="top"
          placeholder="Enter value"
          required={true}
        />
        <Select
          id="itemTypeInput"
          emptyMessage="No options"
          formDataKey="item_type"
          itemMode="static"
          label="Item type"
          labelPosition="top"
          labels={null}
          overlayMaxHeight={375}
          placeholder="Select an option"
          required={true}
          showSelectionIndicator={true}
          values={null}
        >
          <Option id="00030" label="Produto" value="product" />
          <Option id="00031" label="Serviço" value="service" />
        </Select>
        <Select
          id="categoryInput2"
          data="{{ product_service_categories_get.data }}"
          emptyMessage="No options"
          formDataKey="category"
          label="Category"
          labelPosition="top"
          labels="{{ item.name }}"
          overlayMaxHeight={375}
          placeholder="Select an option"
          required={true}
          showSelectionIndicator={true}
          values="{{ item.id }}"
        />
        <NumberInput
          id="codeInput"
          currency="USD"
          formDataKey="code"
          inputValue={0}
          label="Code"
          labelPosition="top"
          placeholder="Enter value"
          required={true}
          showSeparators={true}
          showStepper={true}
          value={0}
        />
        <TextInput
          id="descriptionInput3"
          formDataKey="description"
          label="Description"
          labelPosition="top"
          placeholder="Enter value"
          required={true}
        />
        <Select
          id="currencyInput6"
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
          value="{{ product_service_selected.value && product_service_selected.value ? product_service_selected.value : 1 }}"
          values="{{ item.id }}"
        />
        <NumberInput
          id="priceInput"
          currency="USD"
          formDataKey="price"
          inputValue={0}
          label="Price"
          labelPosition="top"
          placeholder="Enter value"
          showSeparators={true}
          showStepper={true}
          value={0}
        />
        <TextInput
          id="costInput"
          formDataKey="cost"
          label="Cost"
          labelPosition="top"
          placeholder="Enter value"
          required={'{{ itemTypeInput.value === "product" }}'}
        />
        <TextInput
          id="taxCodeInput"
          formDataKey="tax_code"
          label="Tax code"
          labelPosition="top"
          placeholder="Enter value"
        />
        <Checkbox
          id="trackInventoryInput"
          formDataKey="track_inventory"
          label="Track inventory"
          labelWidth="100"
        />
        <NumberInput
          id="stockQuantityInput"
          currency="USD"
          formDataKey="stock_quantity"
          inputValue={0}
          label="Stock quantity"
          labelPosition="top"
          placeholder="Enter value"
          showSeparators={true}
          showStepper={true}
          value={0}
        />
        <Checkbox
          id="isActiveInput4"
          formDataKey="is_active"
          label="Is active"
          labelWidth="100"
          value="{{ product_service_selected.value && product_service_selected.value ? product_service_selected.value : true }}"
        />
        <Checkbox
          id="isDeletedInput4"
          formDataKey="is_deleted"
          label="Is deleted"
          labelWidth="100"
        />
      </Body>
      <Footer>
        <Button
          id="NewButton18"
          hidden={'{{ product_service_mode.value !== "new" }}'}
          submitTargetId="ProductServiceForm"
          text="Submit"
        >
          <Event
            event="click"
            method="trigger"
            params={{ ordered: [] }}
            pluginId="product_service_new"
            type="datasource"
            waitMs="0"
            waitType="debounce"
          />
        </Button>
        <Button
          id="EditButton18"
          hidden={'{{ product_service_mode.value !== "edit" }}'}
          submit={true}
          submitTargetId="ProductServiceForm"
          text="Edit"
        />
      </Footer>
    </Form>
  </Body>
</ModalFrame>
