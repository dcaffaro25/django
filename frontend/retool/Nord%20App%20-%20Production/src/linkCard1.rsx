<Container
  id="linkCard1"
  footerPadding="4px 12px"
  headerPadding="4px 12px"
  padding="12px"
  showBody={true}
  showBorder={false}
>
  <View id="00030" viewKey="View 1">
    <ButtonGroup2 id="buttonGroup7" alignment="right" overflowPosition={1}>
      <ButtonGroup2-Button id="c7e32" styleVariant="outline" text="Edit">
        <Event
          event="click"
          method="setValue"
          params={{ map: { value: "{{ item }}" } }}
          pluginId="SelectedTenant"
          type="state"
          waitMs="0"
          waitType="debounce"
        />
        <Event
          event="click"
          method="show"
          params={{}}
          pluginId="modalFrame9"
          type="widget"
          waitMs="0"
          waitType="debounce"
        />
      </ButtonGroup2-Button>
    </ButtonGroup2>
    <Spacer id="spacer1" />
    <Text
      id="containerTitle23"
      style={{ map: { color: "{{ linkCard1.hovered ? theme.primary : '' }}" } }}
      value="#### {{ item.name }}
**{{ item.subdomain }}**"
      verticalAlign="center"
    />
    <Text
      id="containerTitle24"
      value="A link card is useful for providing text in a clickable card."
      verticalAlign="center"
    />
    <Spacer id="spacer2" />
    <Text
      id="containerFooter1"
      style={{ map: { color: "{{ linkCard1.hovered ? theme.primary : '' }}" } }}
      value="**Click to open**"
      verticalAlign="center"
    />
  </View>
  <Event
    event="click"
    method="run"
    params={{
      map: {
        src: 'localStorage.setValue(\n  "SelectedTenant",\n  item);\nSelectedTenant.setValue(item);\ntenant_subdomain.setValue(item.subdomain);',
      },
    }}
    pluginId=""
    type="script"
    waitMs="0"
    waitType="debounce"
  />
</Container>
