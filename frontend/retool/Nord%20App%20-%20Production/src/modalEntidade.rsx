<ModalFrame
  id="modalEntidade"
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
      id="modalTitle11"
      value={
        '#### {{ entity_mode.value !== "edit"  ? "Nova" : "Editar" }} Entidade'
      }
      verticalAlign="center"
    />
    <Button
      id="modalCloseButton13"
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
        pluginId="modalEntidade"
        type="widget"
        waitMs="0"
        waitType="debounce"
      />
    </Button>
  </Header>
  <Body>
    <Form
      id="EntityForm"
      footerPadding="4px 12px"
      headerPadding="4px 12px"
      initialData=""
      padding="12px"
      requireValidation={true}
      resetAfterSubmit={true}
      scroll={true}
      showBody={true}
    >
      <Header>
        <Text
          id="formTitle24"
          value={
            '#### {{ entity_selected.value === "" ? "Nova" : "Editar" }} Entidade'
          }
          verticalAlign="center"
        />
      </Header>
      <Body>
        <Select
          id="companyInput"
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
          value="{{ ClienteDropDown.selectedItem.id }}"
          values="{{ item.id }}"
        />
        <TextInput
          id="nameInput"
          formDataKey="name"
          label="Name"
          labelPosition="top"
          placeholder="Enter value"
          required={true}
          value="{{ entity_selected.value.name }}"
        />
        <Select
          id="parentIdInput"
          data="{{ entities_get.data }}"
          emptyMessage="No options"
          formDataKey="parent"
          label="Parent"
          labelPosition="top"
          labels="{{ item.path }}"
          overlayMaxHeight={375}
          placeholder="Select an option"
          showClear={true}
          showSelectionIndicator={true}
          value="{{ entity_selected.value.parent_id }}"
          values="{{ item.id }}"
        />
        <Container
          id="group42"
          _align="end"
          _gap="0px"
          _type="stack"
          footerPadding="4px 12px"
          headerPadding="4px 12px"
          heightType="fixed"
          margin="0"
          overflowType="hidden"
          padding="0"
          showBody={true}
          showBorder={false}
          style={{ map: { background: "rgba(255, 255, 255, 0)" } }}
        >
          <View id="108be" viewKey="View 1">
            <Checkbox
              id="inheritAccountsInput"
              formDataKey="inherit_accounts"
              label="Inherit accounts"
              labelWidth="100"
              value="{{ entity_selected.value.inherit_accounts ? entity_selected.value.inherit_accounts : false }}"
            >
              <Event
                event="change"
                method="trigger"
                params={{}}
                pluginId="entity_context_get"
                type="datasource"
                waitMs="0"
                waitType="debounce"
              />
            </Checkbox>
            <Icon
              id="icon2"
              horizontalAlign="center"
              icon="bold/interface-file-double"
            >
              <Event
                event="click"
                method="setValue"
                params={{
                  map: {
                    value:
                      "{{ entity_context_get.data.available_accounts.map(a => a.id) }}",
                  },
                }}
                pluginId="accountsInput"
                type="widget"
                waitMs="0"
                waitType="debounce"
              />
            </Icon>
          </View>
        </Container>
        <Container
          id="group43"
          _align="end"
          _flexWrap={true}
          _gap="0px"
          _type="stack"
          footerPadding="4px 12px"
          headerPadding="4px 12px"
          heightType="fixed"
          margin="0"
          overflowType="hidden"
          padding="0"
          showBody={true}
          showBorder={false}
          style={{ map: { background: "rgba(255, 255, 255, 0)" } }}
        >
          <View id="108be" viewKey="View 1">
            <Checkbox
              id="inheritCostCentersInput"
              formDataKey="inherit_cost_centers"
              label="Inherit cost centers"
              labelWidth="100"
              value="{{ entity_selected.value.inherit_cost_centers ? entity_selected.value.inherit_cost_centers : false }}"
            >
              <Event
                event="change"
                method="trigger"
                params={{}}
                pluginId="entity_context_get"
                type="datasource"
                waitMs="0"
                waitType="debounce"
              />
            </Checkbox>
            <Icon
              id="icon3"
              horizontalAlign="center"
              icon="bold/interface-file-double"
            >
              <Event
                event="click"
                method="setValue"
                params={{
                  map: {
                    value:
                      "{{ entity_context_get.data.available_cost_centers.map(a => a.id) }}",
                  },
                }}
                pluginId="accountsInput"
                type="widget"
                waitMs="0"
                waitType="debounce"
              />
            </Icon>
          </View>
        </Container>
        <MultiselectListbox
          id="costCentersInput"
          data="{{ entity_context_get.data.available_cost_centers ? entity_context_get.data.available_cost_centers : null }}"
          disabledByIndex="{{ inheritCostCentersInput.value }}"
          emptyMessage="No options"
          formDataKey="cost_centers"
          label="Cost centers"
          labelPosition="top"
          labels="{{ item.name }}"
          showSelectionIndicator={true}
          value="{{  inheritCostCentersInput.value ? entity_context_get.data.available_cost_centers.map(a => a.id) : entity_context_get.data.selected_cost_centers }}"
          values="{{ item.id }}"
        />
        <MultiselectListbox
          id="accountsInput"
          data="{{ entity_context_get.data.available_accounts ? entity_context_get.data.available_accounts : null }}"
          disabledByIndex="{{ inheritAccountsInput.value }}"
          emptyMessage="No options"
          formDataKey="accounts"
          label="Accounts"
          labelPosition="top"
          labels="{{ item.name }}"
          showSelectionIndicator={true}
          value="{{  inheritAccountsInput.value ? entity_context_get.data.available_accounts.map(a => a.id) : entity_context_get.data.selected_accounts }}"
          values="{{ item.id }}"
        />
      </Body>
      <Event
        event="submit"
        method="trigger"
        params={{}}
        pluginId="entity_edit"
        type="datasource"
        waitMs="0"
        waitType="debounce"
      />
    </Form>
  </Body>
  <Footer>
    <Button
      id="NewButton14"
      hidden={'{{ entity_mode.value !== "new" }}'}
      submitTargetId="EntityForm"
      text="Submit"
    >
      <Event
        event="click"
        method="trigger"
        params={{ ordered: [] }}
        pluginId="entity_new"
        type="datasource"
        waitMs="0"
        waitType="debounce"
      />
    </Button>
    <Button
      id="EditButton14"
      hidden={'{{ entity_mode.value !== "edit" }}'}
      submit={true}
      submitTargetId="EntityForm"
      text="Edit"
    />
  </Footer>
</ModalFrame>
