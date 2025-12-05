<Screen
  id="home"
  _customShortcuts={[]}
  _hashParams={[]}
  _searchParams={[]}
  browserTitle=""
  title="Home"
  urlSlug="home"
  uuid="bf32ff57-99aa-4661-ac08-b0492567d82b"
>
  <SqlTransformQuery
    id="check_login"
    resourceName="SQL Transforms"
    resourceTypeOverride=""
  >
    <Event
      event="success"
      method="trigger"
      params={{
        map: {
          options: { onSuccess: null, onFailure: null, additionalScope: null },
        },
      }}
      pluginId="redirect_login"
      type="datasource"
      waitMs="0"
      waitType="debounce"
    />
    <Event
      event="failure"
      method="trigger"
      params={{}}
      pluginId="redirect_login"
      type="datasource"
      waitMs="0"
      waitType="debounce"
    />
  </SqlTransformQuery>
  <SqlTransformQuery
    id="check_login4"
    resourceName="SQL Transforms"
    resourceTypeOverride=""
  >
    <Event
      event="success"
      method="trigger"
      params={{
        map: {
          options: { onSuccess: null, onFailure: null, additionalScope: null },
        },
      }}
      pluginId="redirect_login"
      type="datasource"
      waitMs="0"
      waitType="debounce"
    />
    <Event
      event="failure"
      method="trigger"
      params={{}}
      pluginId="redirect_login"
      type="datasource"
      waitMs="0"
      waitType="debounce"
    />
  </SqlTransformQuery>
  <SqlTransformQuery
    id="check_login5"
    resourceName="SQL Transforms"
    resourceTypeOverride=""
  >
    <Event
      event="success"
      method="trigger"
      params={{
        map: {
          options: { onSuccess: null, onFailure: null, additionalScope: null },
        },
      }}
      pluginId="redirect_login"
      type="datasource"
      waitMs="0"
      waitType="debounce"
    />
    <Event
      event="failure"
      method="trigger"
      params={{}}
      pluginId="redirect_login"
      type="datasource"
      waitMs="0"
      waitType="debounce"
    />
  </SqlTransformQuery>
  <SqlTransformQuery
    id="check_login6"
    resourceName="SQL Transforms"
    resourceTypeOverride=""
  >
    <Event
      event="success"
      method="trigger"
      params={{
        map: {
          options: { onSuccess: null, onFailure: null, additionalScope: null },
        },
      }}
      pluginId="redirect_login"
      type="datasource"
      waitMs="0"
      waitType="debounce"
    />
    <Event
      event="failure"
      method="trigger"
      params={{}}
      pluginId="redirect_login"
      type="datasource"
      waitMs="0"
      waitType="debounce"
    />
  </SqlTransformQuery>
  <Frame
    id="$main"
    enableFullBleed={false}
    isHiddenOnDesktop={false}
    isHiddenOnMobile={false}
    padding="8px 12px"
    type="main"
  >
    <TextInput
      id="textInput24"
      iconBefore="bold/interface-search"
      label=""
      labelPosition="top"
      placeholder="Search"
    />
    <Button
      id="button41"
      iconBefore="bold/interface-add-2"
      style={{}}
      text="Novo"
    >
      <Event
        event="click"
        method="setValue"
        params={{}}
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
    </Button>
    <ListViewBeta
      id="gridView1"
      _primaryKeys="{{ item.id }}"
      data="{{ clientes.data }}"
      itemWidth="200px"
      layoutType="grid"
      margin="0"
      numColumns={3}
      padding="0"
    >
      <Container
        id="container22"
        footerPadding="4px 12px"
        headerPadding="4px 12px"
        padding="12px"
        showBody={true}
      >
        <Header>
          <Text
            id="containerTitle22"
            value="#### {{ item }}"
            verticalAlign="center"
          />
        </Header>
        <View id="00030" viewKey="View 1">
          <Include src="./linkCard1.rsx" />
        </View>
      </Container>
    </ListViewBeta>
  </Frame>
</Screen>
