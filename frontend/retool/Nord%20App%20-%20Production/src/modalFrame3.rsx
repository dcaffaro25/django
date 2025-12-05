<ModalFrame
  id="modalFrame3"
  footerPadding="8px 12px"
  headerPadding="8px 12px"
  hidden={true}
  isHiddenOnMobile={true}
  padding="8px 12px"
  showFooter={true}
  showHeader={true}
  showOverlay={true}
  size="fullScreen"
>
  <Header>
    <Text
      id="modalTitle4"
      value={
        '#### {{ IntegrationRuleSelected.value === "" ? "Nova" : "Editar" }} Regra de Integração'
      }
      verticalAlign="center"
    />
    <Button
      id="modalCloseButton4"
      ariaLabel="Close"
      horizontalAlign="right"
      iconBefore="bold/interface-delete-1"
      style={{ ordered: [{ border: "transparent" }] }}
      styleVariant="outline"
    >
      <Event
        event="click"
        method="setHidden"
        params={{ ordered: [{ hidden: true }] }}
        pluginId="modalFrame3"
        type="widget"
        waitMs="0"
        waitType="debounce"
      />
    </Button>
  </Header>
  <Body>
    <Include src="./container2.rsx" />
    <Form
      id="IntegrationRuleForm"
      footerPadding="4px 12px"
      headerPadding="4px 12px"
      heightType="fixed"
      initialData="{{ IntegrationRuleSelected.value }}"
      padding="12px"
      requireValidation={true}
      resetAfterSubmit={true}
      showBody={true}
      showHeader={true}
    >
      <Header>
        <Switch
          id="switch1"
          formDataKey="is_active"
          label="Regra Ativa"
          value="{{ IntegrationRuleSelected.value[self.formDataKey] }}"
        />
      </Header>
      <Body>
        <TextInput
          id="Nome2"
          formDataKey="name"
          label="Nome"
          labelPosition="top"
          placeholder="Enter value"
          required={true}
          value="{{ IntegrationRuleSelected.value[self.formDataKey] }}"
        />
        <TextArea
          id="Field2"
          autoResize={true}
          formDataKey="description"
          label="Descrição"
          labelPosition="top"
          minLines={2}
          placeholder="Enter value"
          required={true}
          value="{{ IntegrationRuleSelected.value[self.formDataKey] }}"
        />
        <Select
          id="company5"
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
        <Select
          id="select18"
          emptyMessage="No options"
          formDataKey="trigger_event"
          itemMode="static"
          label="Gatilho"
          labelPosition="top"
          overlayMaxHeight={375}
          placeholder="Select an option"
          required={true}
          showSelectionIndicator={true}
          value="{{ IntegrationRuleSelected.value[self.formDataKey] }}"
        >
          <Option id="b3f10" value="payroll_approved" />
          <Option id="fedb7" value="payroll_created" />
        </Select>
        <NumberInput
          id="numberInput63"
          currency="USD"
          formDataKey="execution_order"
          inputValue={0}
          label="Prioridade"
          labelPosition="top"
          placeholder="Enter value"
          showSeparators={true}
          showStepper={true}
          value="{{ IntegrationRuleSelected.value[self.formDataKey] }}"
        />
        <Container
          id="group12"
          footerPadding="4px 12px"
          headerPadding="4px 12px"
          margin="0"
          padding="0"
          showBody={true}
          showBorder={false}
          style={{ ordered: [{ background: "rgba(255, 255, 255, 0)" }] }}
        >
          <View id="20a2e" viewKey="View 1">
            <Container
              id="group13"
              _gap="0px"
              _justify="space-between"
              _type="stack"
              footerPadding="4px 12px"
              headerPadding="4px 12px"
              margin="0"
              padding="0"
              showBody={true}
              showBorder={false}
              style={{ ordered: [{ background: "rgba(255, 255, 255, 0)" }] }}
            >
              <View id="20a2e" viewKey="View 1">
                <Text id="text7" value="**Condições**" verticalAlign="center" />
                <Button
                  id="button8"
                  iconBefore="bold/programming-script-code"
                  style={{ ordered: [] }}
                  styleVariant="outline"
                >
                  <Event
                    event="click"
                    method="show"
                    params={{ ordered: [] }}
                    pluginId="modalCodeEditorCondicao"
                    type="widget"
                    waitMs="0"
                    waitType="debounce"
                  />
                </Button>
              </View>
            </Container>
            <TextArea
              id="textArea8"
              autoResize={true}
              disabled="true"
              formDataKey="filter_conditions"
              label=""
              labelPosition="top"
              maxLines="5"
              minLines={2}
              placeholder="Enter value"
              value="{{ CodeEditorRegra.model.code }}"
            />
          </View>
        </Container>
        <Container
          id="group11"
          footerPadding="4px 12px"
          headerPadding="4px 12px"
          margin="0"
          padding="0"
          showBody={true}
          showBorder={false}
          style={{ ordered: [{ background: "rgba(255, 255, 255, 0)" }] }}
        >
          <View id="20a2e" viewKey="View 1">
            <Container
              id="group10"
              _gap="0px"
              _justify="space-between"
              _type="stack"
              footerPadding="4px 12px"
              headerPadding="4px 12px"
              margin="0"
              padding="0"
              showBody={true}
              showBorder={false}
              style={{ ordered: [{ background: "rgba(255, 255, 255, 0)" }] }}
            >
              <View id="20a2e" viewKey="View 1">
                <Text
                  id="text6"
                  value={'**Regra** <span style="color: red;">*</span>'}
                  verticalAlign="center"
                />
                <Button
                  id="button7"
                  iconBefore="bold/programming-script-code"
                  style={{ ordered: [] }}
                  styleVariant="outline"
                >
                  <Event
                    event="click"
                    method="show"
                    params={{ ordered: [] }}
                    pluginId="modalCodeEditorRegra"
                    type="widget"
                    waitMs="0"
                    waitType="debounce"
                  />
                </Button>
              </View>
            </Container>
            <TextArea
              id="textArea7"
              autoResize={true}
              disabled="true"
              formDataKey="rule"
              label=""
              labelPosition="top"
              maxLines="15"
              minLines={2}
              placeholder="Enter value"
              value="{{ CodeEditorRegra.model.code }}"
            />
          </View>
        </Container>
      </Body>
      <Event
        event="submit"
        method="trigger"
        params={{ ordered: [] }}
        pluginId="IntegrationRule_edit"
        type="datasource"
        waitMs="0"
        waitType="debounce"
      />
    </Form>
  </Body>
  <Footer>
    <Button
      id="EditButton9"
      hidden={'{{ IntegrationRuleSelected.value === "" }}'}
      submit={true}
      submitTargetId="IntegrationRuleForm"
      text="Edit"
    />
    <Button
      id="NewButton9"
      hidden={'{{ IntegrationRuleSelected.value !== "" }}'}
      submitTargetId="IntegrationRuleForm"
      text="Submit"
    >
      <Event
        event="click"
        method="trigger"
        params={{ ordered: [] }}
        pluginId="IntegrationRule_new"
        type="datasource"
        waitMs="0"
        waitType="debounce"
      />
    </Button>
  </Footer>
</ModalFrame>
