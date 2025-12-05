<ModalFrame
  id="modalFrame9"
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
      id="modalTitle36"
      value={'### {{ SelectedTenant.value ? "Editar" : "Nova" }} Empresa'}
      verticalAlign="center"
    />
    <Button
      id="modalCloseButton40"
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
        pluginId="modalFrame9"
        type="widget"
        waitMs="0"
        waitType="debounce"
      />
    </Button>
  </Header>
  <Body>
    <Form
      id="formTenant"
      footerPadding="4px 12px"
      headerPadding="4px 12px"
      initialData=""
      padding="12px"
      requireValidation={true}
      resetAfterSubmit={true}
      showBody={true}
      showFooter={true}
    >
      <Header>
        <Text id="formTitle28" value="#### Form title" verticalAlign="center" />
      </Header>
      <Body>
        <TextInput
          id="textInputName"
          formDataKey="name"
          label="Name"
          labelPosition="top"
          placeholder="Enter value"
          value="{{ SelectedTenant.value ? SelectedTenant.value[self.formDataKey] : null }}"
        />
        <TextInput
          id="textInputSubdomain"
          formDataKey="subdomain"
          label="Subdomain"
          labelPosition="top"
          placeholder="Enter value"
          value="{{ SelectedTenant.value ? SelectedTenant.value[self.formDataKey] : null }}"
        />
      </Body>
      <Footer>
        <Button
          id="formButton15"
          hidden="{{ SelectedTenant.value ? true : false }}"
          submitTargetId="formTenant"
          text="Submit"
        >
          <Event
            event="click"
            method="trigger"
            params={{}}
            pluginId="companies_new"
            type="datasource"
            waitMs="0"
            waitType="debounce"
          />
        </Button>
        <Button
          id="formButton16"
          hidden="{{ SelectedTenant.value ? false : true }}"
          submitTargetId="formTenant"
          text="Edit"
        >
          <Event
            event="click"
            method="trigger"
            params={{}}
            pluginId="companies_edit"
            type="datasource"
            waitMs="0"
            waitType="debounce"
          />
        </Button>
      </Footer>
      <Event
        event="submit"
        method="trigger"
        params={{}}
        pluginId="companies_new"
        type="datasource"
        waitMs="0"
        waitType="debounce"
      />
    </Form>
  </Body>
</ModalFrame>
