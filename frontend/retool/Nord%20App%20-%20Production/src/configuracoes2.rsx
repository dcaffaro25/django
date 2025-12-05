<Screen
  id="configuracoes2"
  _customShortcuts={[]}
  _hashParams={[]}
  _searchParams={[]}
  browserTitle=""
  title="Configurações"
  urlSlug="configuracoes-1"
  uuid="5f46fa14-5804-4cbe-84f7-a6a20fa1eb95"
>
  <RESTQuery
    id="IntegrationRule_new2"
    body="{{ IntegrationRuleForm2.data }}"
    bodyType="raw"
    cookies={'[{"key":"","value":""}]'}
    headers={'[{"key":"Content-Type","value":"application/json"}]'}
    isHidden={false}
    isMultiplayerEdited={false}
    query="/{{ tenant_subdomain.value }}/api/core/integration-rules/?"
    resourceDisplayName="Tenant Specific"
    resourceName="e4a763c9-4f5e-4f5a-99f7-6a33454d4577"
    resourceTypeOverride=""
    runWhenModelUpdates={false}
    type="POST"
  >
    <Event
      event="success"
      method="trigger"
      params={{ ordered: [] }}
      pluginId="IntegrationRule_get2"
      type="datasource"
      waitMs="0"
      waitType="debounce"
    />
    <Event
      event="success"
      method="setValue"
      params={{ ordered: [{ value: '""' }] }}
      pluginId="IntegrationRuleSelected2"
      type="state"
      waitMs="0"
      waitType="debounce"
    />
    <Event
      event="success"
      method="hide"
      params={{ ordered: [] }}
      pluginId="modalFrame13"
      type="widget"
      waitMs="0"
      waitType="debounce"
    />
  </RESTQuery>
  <SqlTransformQuery
    id="check_login8"
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
  <State id="IntegrationRuleSelected2" />
  <RESTQuery
    id="IntegrationRule_testrun2"
    body={
      '{\n  "setup_data": {{ CodeEditorSetup2.model.code }},\n  "payload": {{ CodeEditorPayloadFiltrado3.model.code }},\n  "rule": {{ IntegrationRuleForm2.data.rule }}\n}'
    }
    bodyType="raw"
    cookies={'[{"key":"","value":""}]'}
    headers={'[{"key":"Content-Type","value":"application/json"}]'}
    isHidden={false}
    isMultiplayerEdited={false}
    query="/{{ tenant_subdomain.value }}/api/core/test-rule/"
    resourceDisplayName="Tenant Specific"
    resourceName="e4a763c9-4f5e-4f5a-99f7-6a33454d4577"
    resourceTypeOverride=""
    runWhenModelUpdates={false}
    type="POST"
  >
    <Event
      event="success"
      method="updateModel"
      params={{
        ordered: [
          {
            model:
              "{code: {{ JSON.stringify(IntegrationRule_testrun2.data, null, 4) }} }",
          },
        ],
      }}
      pluginId="CodeEditorPayloadFiltrado4"
      type="widget"
      waitMs="0"
      waitType="debounce"
    />
  </RESTQuery>
  <RESTQuery
    id="IntegrationRule_get2"
    isHidden={false}
    isMultiplayerEdited={false}
    query="/{{ tenant_subdomain.value }}/api/core/integration-rules/"
    resourceDisplayName="Tenant Specific"
    resourceName="e4a763c9-4f5e-4f5a-99f7-6a33454d4577"
    resourceTypeOverride=""
  />
  <RESTQuery
    id="IntegrationRule_validate2"
    body={
      '{\n  "trigger_event": {{ IntegrationRuleForm2.data.trigger_event }},\n  "rule": {{ IntegrationRuleForm2.data.rule }},\n  "filter_conditions": {{ IntegrationRuleForm2.data.filter_conditions }},\n  "num_records": 10\n}'
    }
    bodyType="raw"
    cookies={'[{"key":"","value":""}]'}
    headers={'[{"key":"Content-Type","value":"application/json"}]'}
    isHidden={false}
    isMultiplayerEdited={false}
    query="/{{ tenant_subdomain.value }}/api/core/validate-rule/"
    resourceDisplayName="Tenant Specific"
    resourceName="e4a763c9-4f5e-4f5a-99f7-6a33454d4577"
    resourceTypeOverride=""
    runWhenModelUpdates={false}
    type="POST"
  >
    <Event
      event="success"
      method="updateModel"
      params={{
        ordered: [
          {
            model:
              '{\n  "code": {{ IntegrationRule_validate2.data.setup_data }} ,\n}',
          },
        ],
      }}
      pluginId="CodeEditorSetup2"
      type="widget"
      waitMs="0"
      waitType="debounce"
    />
    <Event
      event="success"
      method="updateModel"
      params={{
        ordered: [
          {
            model:
              '{\n  "code": {{ IntegrationRule_validate2.data.mock_payload }} ,\n}',
          },
        ],
      }}
      pluginId="CodeEditorPayload2"
      type="widget"
      waitMs="0"
      waitType="debounce"
    />
    <Event
      event="success"
      method="updateModel"
      params={{
        ordered: [
          {
            model:
              '{\n  "code": {{ IntegrationRule_validate2.data.mock_filtered_payload }} ,\n}',
          },
        ],
      }}
      pluginId="CodeEditorPayloadFiltrado3"
      type="widget"
      waitMs="0"
      waitType="debounce"
    />
  </RESTQuery>
  <RESTQuery
    id="IntegrationRule_edit2"
    body="{{ IntegrationRuleForm2.data }}"
    bodyType="raw"
    cookies={'[{"key":"","value":""}]'}
    headers={'[{"key":"Content-Type","value":"application/json"}]'}
    isHidden={false}
    isMultiplayerEdited={false}
    query="/{{ tenant_subdomain.value }}/api/core/integration-rules/{{ 
IntegrationRuleSelected2.value.id }}/"
    resourceDisplayName="Tenant Specific"
    resourceName="e4a763c9-4f5e-4f5a-99f7-6a33454d4577"
    resourceTypeOverride=""
    runWhenModelUpdates={false}
    type="PUT"
  >
    <Event
      event="success"
      method="trigger"
      params={{ ordered: [] }}
      pluginId="IntegrationRule_get2"
      type="datasource"
      waitMs="0"
      waitType="debounce"
    />
    <Event
      event="success"
      method="setValue"
      params={{ ordered: [{ value: '""' }] }}
      pluginId="IntegrationRuleSelected2"
      type="state"
      waitMs="0"
      waitType="debounce"
    />
    <Event
      event="success"
      method="hide"
      params={{ ordered: [] }}
      pluginId="modalFrame13"
      type="widget"
      waitMs="0"
      waitType="debounce"
    />
  </RESTQuery>
  <Include src="./modalCodeEditorCondicao2.rsx" />
  <Include src="./modalCodeEditorRegra2.rsx" />
  <Include src="./modalFrame13.rsx" />
  <Include src="./modalFrame14.rsx" />
  <Frame
    id="$main13"
    enableFullBleed={false}
    isHiddenOnDesktop={false}
    isHiddenOnMobile={false}
    padding="8px 12px"
    sticky={null}
    type="main"
  >
    <Container
      id="container27"
      footerPadding="4px 12px"
      headerPadding="4px 12px"
      heightType="fixed"
      padding="12px"
      showBody={true}
      showHeader={true}
    >
      <Header>
        <Text
          id="containerTitle28"
          value="#### Container title"
          verticalAlign="center"
        />
      </Header>
      <View id="a1a7d" viewKey="View 1">
        <Include src="./tabbedContainer4.rsx" />
        <Navigation
          id="navigation3"
          data="{{  tabbedContainer4.labels }}"
          highlightByIndex="{{ tabbedContainer4.labels[tabbedContainer4.currentViewIndex] === item }}"
          labels="{{ item.title || item }}"
          orientation="vertical"
          retoolFileObject={{ ordered: [] }}
          style={{ ordered: [] }}
        >
          <Option id="57138" icon="bold/interface-home-3" label="Home" />
          <Option
            id="ccfb4"
            icon="bold/interface-user-multiple"
            label="Customers"
          />
          <Option
            id="ff0bd"
            icon="bold/interface-setting-cog"
            label="Settings"
          />
          <Event
            event="click"
            method="setCurrentViewIndex"
            params={{ ordered: [{ viewIndex: "{{ i }}" }] }}
            pluginId="tabbedContainer4"
            type="widget"
            waitMs="0"
            waitType="debounce"
          />
        </Navigation>
      </View>
    </Container>
  </Frame>
</Screen>
