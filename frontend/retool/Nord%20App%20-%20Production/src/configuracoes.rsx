<Screen
  id="configuracoes"
  _customShortcuts={[]}
  _hashParams={[]}
  _searchParams={[]}
  browserTitle=""
  title="Configurações"
  urlSlug="configuracoes"
  uuid="ac07fed3-67d9-4bde-9277-0647eda71902"
>
  <State id="IntegrationRuleSelected" />
  <RESTQuery
    id="SubstitutionRule_get"
    isHidden={false}
    isMultiplayerEdited={false}
    query="{{ tenant_subdomain.value }}/api/core/substitution-rules/"
    resourceDisplayName="Tenant Specific - Production"
    resourceName="db4d0175-aa88-429c-ba3f-f4bbd2c875e3"
    resourceTypeOverride=""
  />
  <RESTQuery
    id="IntegrationRule_new"
    body="{{ IntegrationRuleForm.data }}"
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
      pluginId="SubstitutionRule_get"
      type="datasource"
      waitMs="0"
      waitType="debounce"
    />
    <Event
      event="success"
      method="setValue"
      params={{ ordered: [{ value: '""' }] }}
      pluginId="IntegrationRuleSelected"
      type="state"
      waitMs="0"
      waitType="debounce"
    />
    <Event
      event="success"
      method="hide"
      params={{ ordered: [] }}
      pluginId="modalFrame3"
      type="widget"
      waitMs="0"
      waitType="debounce"
    />
  </RESTQuery>
  <RESTQuery
    id="IntegrationRule_edit"
    body="{{ IntegrationRuleForm.data }}"
    bodyType="raw"
    cookies={'[{"key":"","value":""}]'}
    headers={'[{"key":"Content-Type","value":"application/json"}]'}
    isHidden={false}
    isMultiplayerEdited={false}
    query="/{{ tenant_subdomain.value }}/api/core/integration-rules/{{ 
IntegrationRuleSelected.value.id }}/"
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
      pluginId="SubstitutionRule_get"
      type="datasource"
      waitMs="0"
      waitType="debounce"
    />
    <Event
      event="success"
      method="setValue"
      params={{ ordered: [{ value: '""' }] }}
      pluginId="IntegrationRuleSelected"
      type="state"
      waitMs="0"
      waitType="debounce"
    />
    <Event
      event="success"
      method="hide"
      params={{ ordered: [] }}
      pluginId="modalFrame3"
      type="widget"
      waitMs="0"
      waitType="debounce"
    />
  </RESTQuery>
  <RESTQuery
    id="IntegrationRule_validate"
    body={
      '{\n  "trigger_event": {{ IntegrationRuleForm.data.trigger_event }},\n  "rule": {{ IntegrationRuleForm.data.rule }},\n  "filter_conditions": {{ IntegrationRuleForm.data.filter_conditions }},\n  "num_records": 10\n}'
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
              '{\n  "code": {{ IntegrationRule_validate.data.setup_data }} ,\n}',
          },
        ],
      }}
      pluginId="CodeEditorSetup"
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
              '{\n  "code": {{ IntegrationRule_validate.data.mock_payload }} ,\n}',
          },
        ],
      }}
      pluginId="CodeEditorPayload"
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
              '{\n  "code": {{ IntegrationRule_validate.data.mock_filtered_payload }} ,\n}',
          },
        ],
      }}
      pluginId="CodeEditorPayloadFiltrado"
      type="widget"
      waitMs="0"
      waitType="debounce"
    />
  </RESTQuery>
  <RESTQuery
    id="IntegrationRule_testrun"
    body={
      '{\n  "setup_data": {{ CodeEditorSetup.model.code }},\n  "payload": {{ CodeEditorPayloadFiltrado.model.code }},\n  "rule": {{ IntegrationRuleForm.data.rule }}\n}'
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
              "{code: {{ JSON.stringify(IntegrationRule_testrun.data, null, 4) }} }",
          },
        ],
      }}
      pluginId="CodeEditorPayloadFiltrado2"
      type="widget"
      waitMs="0"
      waitType="debounce"
    />
  </RESTQuery>
  <SqlTransformQuery
    id="check_login3"
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
  <RESTQuery
    id="bulk_import_preview4"
    body={
      '[{"key":"file","value":"{{ fileButton2.value[0] }}","operation":"binary"},{"key":"commit","value":"False","operation":"text"},{"key":"company_id","value":"4","operation":"text"}]'
    }
    bodyType="form-data"
    cookies={'[{"key":"","value":""}]'}
    headers="[]"
    isHidden={false}
    isMultiplayerEdited={false}
    query="bulk-import/"
    queryDisabled="{{ tenant_subdomain.value == null }}"
    queryTimeout="600000"
    resourceDisplayName="Geral - Production"
    resourceName="ea36f3b9-bc6a-4e1b-a40b-e1014f87e105"
    resourceTypeOverride=""
    runWhenModelUpdates={false}
    type="POST"
  >
    <Event
      event="failure"
      method="run"
      params={{
        map: {
          src: "ErrorMessage.setValue(self.data.message);\n\nmodalFrame15.show();\n\n",
        },
      }}
      pluginId=""
      type="script"
      waitMs="0"
      waitType="debounce"
    />
  </RESTQuery>
  <RESTQuery
    id="SubstituteRule_get"
    isHidden={false}
    isMultiplayerEdited={false}
    query="{{ tenant_subdomain.value }}/api/core/substitution-rules/"
    resourceDisplayName="Tenant Specific - Production"
    resourceName="db4d0175-aa88-429c-ba3f-f4bbd2c875e3"
    resourceTypeOverride=""
  >
    <Event
      event="failure"
      method="run"
      params={{
        map: {
          src: "ErrorMessage.setValue(self.data.message);\n\nmodalFrame15.show();\n\n",
        },
      }}
      pluginId=""
      type="script"
      waitMs="0"
      waitType="debounce"
    />
  </RESTQuery>
  <State id="SubstitutionRuleSelected" />
  <SqlTransformQuery
    id="check_login9"
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
  <RESTQuery
    id="Embeddings_Missing"
    headers={
      '[{"key":"Content-Type","value":"application/json"},{"key":"authorization","value":"Token {{ currentUser.value.token }}"}]'
    }
    isHidden={false}
    isMultiplayerEdited={false}
    query="{{ baseUrl.value }}/{{ SelectedTenant.value.id}} /embeddings/missing-counts/"
    resourceName="REST-WithoutResource"
    resourceTypeOverride=""
  />
  <RESTQuery
    id="Embeddings_Health"
    headers={
      '[{"key":"Content-Type","value":"application/json"},{"key":"authorization","value":"Token {{ currentUser.value.token }}"}]'
    }
    isHidden={false}
    isMultiplayerEdited={false}
    query="{{ baseUrl.value }}/{{ SelectedTenant.value.id}} /embeddings/health/"
    resourceName="REST-WithoutResource"
    resourceTypeOverride=""
  />
  <RESTQuery
    id="Embeddings_Backfill"
    bodyType="json"
    headers={
      '[{"key":"Content-Type","value":"application/json"},{"key":"authorization","value":"Token {{ currentUser.value.token }}"}]'
    }
    isHidden={false}
    isMultiplayerEdited={false}
    query="{{ baseUrl.value }}/{{ SelectedTenant.value.id}} /embeddings/backfill/"
    resourceName="REST-WithoutResource"
    resourceTypeOverride=""
    runWhenModelUpdates={false}
    type="POST"
  />
  <RESTQuery
    id="Embeddings_Tasks"
    headers={
      '[{"key":"Content-Type","value":"application/json"},{"key":"authorization","value":"Token {{ currentUser.value.token }}"}]'
    }
    isHidden={false}
    isMultiplayerEdited={false}
    query="{{ baseUrl.value }}/{{ SelectedTenant.value.id}} /embeddings/tasks/d94539fe-c890-491e-bacb-9ec64dced58d/"
    resourceName="REST-WithoutResource"
    resourceTypeOverride=""
  />
  <RESTQuery
    id="Embeddings_Tasks2"
    headers={
      '[{"key":"Content-Type","value":"application/json"},{"key":"authorization","value":"Token {{ currentUser.value.token }}"}]'
    }
    isHidden={false}
    isMultiplayerEdited={false}
    query="{{ baseUrl.value }}/{{ SelectedTenant.value.id}} /embeddings/jobs/"
    resourceName="REST-WithoutResource"
    resourceTypeOverride=""
  />
  <RESTQuery
    id="Tasks_get"
    headers={
      '[{"key":"Content-Type","value":"application/json"},{"key":"authorization","value":"Token {{ currentUser.value.token }}"}]'
    }
    isHidden={false}
    isMultiplayerEdited={false}
    query="{{ baseUrl.value }}/jobs/"
    resourceName="REST-WithoutResource"
    resourceTypeOverride=""
  />
  <RESTQuery
    id="Tasks_get2"
    headers={
      '[{"key":"Content-Type","value":"application/json"},{"key":"authorization","value":"Token {{ currentUser.value.token }}"}]'
    }
    isHidden={false}
    isMultiplayerEdited={false}
    query="{{ baseUrl.value }}/jobs/d94539fe-c890-491e-bacb-9ec64dced58d/"
    resourceName="REST-WithoutResource"
    resourceTypeOverride=""
  />
  <Include src="./modalCodeEditorCondicao.rsx" />
  <Include src="./modalCodeEditorRegra.rsx" />
  <Include src="./modalFrame3.rsx" />
  <Include src="./modalFrame4.rsx" />
  <Frame
    id="$main5"
    enableFullBleed={false}
    isHiddenOnDesktop={false}
    isHiddenOnMobile={false}
    padding="8px 12px"
    sticky={null}
    type="main"
  >
    <Container
      id="container4"
      footerPadding="4px 12px"
      headerPadding="4px 12px"
      heightType="fixed"
      padding="12px"
      showBody={true}
    >
      <Header>
        <Text
          id="containerTitle2"
          value="#### Container title"
          verticalAlign="center"
        />
      </Header>
      <View id="a1a7d" viewKey="View 1">
        <Include src="./tabbedContainer2.rsx" />
        <Navigation
          id="navigation2"
          data={'["Geral", "Integrações", "Relatórios","Permissões"]'}
          highlightByIndex={
            '{{ ["Geral", "Integrações", "Relatórios","Permissões"][tabbedContainer2.currentViewIndex] === item }}'
          }
          labels="{{ item.title || item }}"
          orientation="vertical"
          retoolFileObject={{ ordered: [] }}
          style={{
            highlightBackground: "rgba(2, 87, 54, 0)",
            fontSize: "h6Font",
            fontWeight: "h6Font",
            fontFamily: "h6Font",
            highlightText: "#0d0d0dff",
          }}
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
            pluginId="tabbedContainer2"
            type="widget"
            waitMs="0"
            waitType="debounce"
          />
        </Navigation>
      </View>
    </Container>
  </Frame>
</Screen>
