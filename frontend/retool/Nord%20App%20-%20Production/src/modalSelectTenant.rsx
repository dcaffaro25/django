<ModalFrame
  id="modalSelectTenant"
  footerPadding="8px 12px"
  headerPadding="8px 12px"
  hidden={
    '{{ tenant_subdomain.value !== null ||  url.href.split("/").pop() == "login"  || url.href.split("/").pop() == "home" }}'
  }
  hideOnEscape={true}
  isHiddenOnMobile={true}
  padding="8px 12px"
  showFooter={true}
  showHeader={true}
  showOverlay={true}
>
  <Header>
    <Text
      id="modalTitle8"
      value="### Selecionar Empresa"
      verticalAlign="center"
    />
    <Button
      id="modalCloseButton8"
      ariaLabel="Close"
      hidden="true"
      horizontalAlign="right"
      iconBefore="bold/interface-delete-1"
      style={{ ordered: [{ border: "transparent" }] }}
      styleVariant="outline"
    >
      <Event
        event="click"
        method="setHidden"
        params={{ ordered: [{ hidden: true }] }}
        pluginId="modalSelectTenant"
        type="widget"
        waitMs="0"
        waitType="debounce"
      />
    </Button>
  </Header>
  <Body>
    <Select
      id="ClienteDropDown2"
      data="{{ clientes.data }}"
      emptyMessage="No options"
      label="Cliente"
      labelPosition="top"
      labels="{{ item.name }}"
      overlayMaxHeight={375}
      placeholder="Select an option"
      showSelectionIndicator={true}
      value="{{ tenant_subdomain.value }}"
      values="{{ item.subdomain }}"
    >
      <Event
        event="change"
        method="setValue"
        params={{ ordered: [{ value: "{{ ClienteDropDown2.value }}" }] }}
        pluginId="tenant_subdomain"
        type="state"
        waitMs="0"
        waitType="debounce"
      />
      <Event
        enabled={'{{ url.href.split("/").pop() == "page3" }}'}
        event="change"
        method="openPage"
        params={{
          ordered: [
            { options: { ordered: [{ passDataWith: "urlParams" }] } },
            { pageName: "home" },
          ],
        }}
        pluginId=""
        type="util"
        waitMs="0"
        waitType="debounce"
      />
      <Event
        event="change"
        method="setValue"
        params={{ map: { value: "{{ self.selectedItem }}" } }}
        pluginId="SelectedTenant"
        type="state"
        waitMs="0"
        waitType="debounce"
      />
    </Select>
    <Button id="btnNewTenant" iconBefore="bold/interface-add-2">
      <Event
        event="click"
        method="show"
        params={{}}
        pluginId="modalFrame9"
        type="widget"
        waitMs="0"
        waitType="debounce"
      />
    </Button>
  </Body>
</ModalFrame>
