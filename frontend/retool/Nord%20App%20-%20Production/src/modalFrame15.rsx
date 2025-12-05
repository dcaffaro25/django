<ModalFrame
  id="modalFrame15"
  footerPadding="8px 12px"
  headerPadding="8px 12px"
  hidden={true}
  hideOnEscape={true}
  isHiddenOnMobile={true}
  overlayInteraction={true}
  padding="8px 12px"
  showHeader={true}
  showOverlay={true}
  size="large"
>
  <Header>
    <Text id="modalTitle45" value="#### Error Message" verticalAlign="center" />
    <Button
      id="modalCloseButton50"
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
        pluginId="modalFrame15"
        type="widget"
        waitMs="0"
        waitType="debounce"
      />
    </Button>
  </Header>
  <Body>
    <HTML
      id="html3"
      css={include("../lib/html3.css", "string")}
      html="{{ ErrorMessage.value.data ? ErrorMessage.value.data.message : ErrorMessage.value }}"
    />
  </Body>
</ModalFrame>
