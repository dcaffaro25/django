<GlobalFunctions>
  <State id="app_building" value="false" />
  <JavascriptQuery
    id="redirect_login"
    isMultiplayerEdited={false}
    query={include("./lib/redirect_login.js", "string")}
    resourceName="JavascriptQuery"
    resourceTypeOverride=""
  />
  <State id="currentUser" value="" />
  <RESTQuery
    id="clientes"
    headers={
      '[{"key":"Content-Type","value":"application/json"},{"key":"authorization","value":"Token {{ currentUser.value.token }}"}]'
    }
    isHidden={false}
    isMultiplayerEdited={false}
    query="{{ baseUrl.value }}/api/core/companies/"
    queryDisabled="{{ currentUser.value == null }}"
    resourceName="REST-WithoutResource"
    resourceTypeOverride=""
  />
  <RESTQuery
    id="accounts"
    headers={
      '[{"key":"content-type","value":"application/json"},{"key":"authorization","value":"Token {{ currentUser.value.token }}"}]'
    }
    isHidden={false}
    isMultiplayerEdited={false}
    query="{{ baseUrl.value }}/{{ tenant_subdomain.value }}/api/accounts/"
    queryDisabled="{{ currentUser.value == null || SelectedTenant.value == null }}"
    queryTimeout="20000"
    resourceName="REST-WithoutResource"
    resourceTypeOverride=""
  />
  <JavascriptQuery
    id="query4"
    isHidden={false}
    notificationDuration={4.5}
    resourceName="JavascriptQuery"
    showSuccessToaster={false}
  />
  <State id="tenant_subdomain" />
  <State id="SelectedTenant" value="" />
  <RESTQuery
    id="currencies"
    headers={
      '[{"key":"content-type","value":"application/json"},{"key":"authorization","value":"Token {{ currentUser.value.token }}"}]'
    }
    isHidden={false}
    isMultiplayerEdited={false}
    query="{{ baseUrl.value }}/api/core/currencies/"
    queryDisabled="{{ currentUser.value == null }}"
    resourceName="REST-WithoutResource"
    resourceTypeOverride=""
  />
  <State id="ListViewUpdatedValue" />
  <EmbeddingQuery
    id="container1ChangeHandler"
    isHidden={false}
    notificationDuration={4.5}
    resourceName="EmbeddingQuery"
    showSuccessToaster={false}
  />
  <State id="variable5" value="false" />
  <State id="SelectedBank" />
  <RESTQuery
    id="bulk_import_template"
    cookies={'[{"key":"","value":""}]'}
    headers={
      '[{"key":"content-type","value":"application/json"},{"key":"authorization","value":"Token {{ currentUser.value.token }}"}]'
    }
    isHidden={false}
    isMultiplayerEdited={false}
    query="{{ baseUrl.value }}/{{ ClienteDropDown.selectedItem.id }}/api/core/bulk-import-template/"
    queryTimeout="600000"
    resourceName="REST-WithoutResource"
    resourceTypeOverride=""
    runWhenModelUpdates={false}
  >
    <Event
      event="success"
      method="run"
      params={{ map: { src: "" } }}
      pluginId=""
      type="script"
      waitMs="0"
      waitType="debounce"
    />
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
    id="financial_index_get"
    headers={
      '[{"key":"content-type","value":"application/json"},{"key":"authorization","value":"Token {{ currentUser.value.token }}"}]'
    }
    isHidden={false}
    isMultiplayerEdited={false}
    query="{{ baseUrl.value }}/api/core/financial_indices/"
    resourceName="REST-WithoutResource"
    resourceTypeOverride=""
    runWhenModelUpdates={false}
  />
  <RESTQuery
    id="companies_new"
    body="{{ formTenant.data }}"
    bodyType="raw"
    headers={'[{"key":"Content-Type","value":"application/json"}]'}
    isMultiplayerEdited={false}
    resourceDisplayName="Geral - Production"
    resourceName="ea36f3b9-bc6a-4e1b-a40b-e1014f87e105"
    runWhenModelUpdates={false}
    type="POST"
  >
    <Event
      event="success"
      method="trigger"
      params={{}}
      pluginId="clientes"
      type="datasource"
      waitMs="0"
      waitType="debounce"
    />
    <Event
      event="success"
      method="hide"
      params={{}}
      pluginId="modalFrame9"
      type="widget"
      waitMs="0"
      waitType="debounce"
    />
  </RESTQuery>
  <RESTQuery
    id="OFXTransaction_import4"
    body={'{\n  "files":{{ fileDropzoneOFX2.value }}\n}'}
    bodyType="raw"
    cookies={'[{"key":"","value":""}]'}
    headers={
      '[{"key":"Content-Type","value":"application/json"},{"key":"authorization","value":"Token {{ currentUser.value.token }}"}]'
    }
    isHidden={false}
    isMultiplayerEdited={false}
    query="{{ baseUrl.value }}/{{ tenant_subdomain.value }}/api/bank_transactions/import_ofx/"
    queryDisabled="{{ tenant_subdomain.value == null }}"
    resourceName="REST-WithoutResource"
    resourceTypeOverride=""
    runWhenModelUpdates={false}
    type="POST"
  />
  <RESTQuery
    id="OFXTransaction_import6"
    _additionalScope={["content"]}
    body="{{ content }}"
    bodyType="raw"
    cookies={'[{"key":"","value":""}]'}
    headers={
      '[{"key":"Content-Type","value":"application/json"},{"key":"authorization","value":"Token {{ currentUser.value.token }}"}]'
    }
    isHidden={false}
    isMultiplayerEdited={false}
    query="{{ baseUrl.value }}/{{ tenant_subdomain.value }}/api/bank_transactions/import_ofx_transactions/"
    queryDisabled="{{ tenant_subdomain.value == null }}"
    resourceName="REST-WithoutResource"
    resourceTypeOverride=""
    runWhenModelUpdates={false}
    type="POST"
  />
  <Function
    id="transformOFX2"
    funcBody={include("./lib/transformOFX2.js", "string")}
    runBehavior="debounced"
  />
  <RESTQuery
    id="companies_edit"
    body="{{ formTenant.data }}"
    bodyType="raw"
    headers={
      '[{"key":"Content-Type","value":"application/json"},{"key":"authorization","value":"Token {{ currentUser.value.token }}"}]'
    }
    isMultiplayerEdited={false}
    query="{{ baseUrl.value }}/api/core/companies/{{ SelectedTenant.value.id }}/"
    resourceName="REST-WithoutResource"
    resourceTypeOverride=""
    runWhenModelUpdates={false}
    type="PUT"
  >
    <Event
      event="success"
      method="trigger"
      params={{}}
      pluginId="clientes"
      type="datasource"
      waitMs="0"
      waitType="debounce"
    />
    <Event
      event="success"
      method="hide"
      params={{}}
      pluginId="modalFrame9"
      type="widget"
      waitMs="0"
      waitType="debounce"
    />
  </RESTQuery>
  <RESTQuery
    id="user_change_password"
    body={
      '[{"key":"old_password","value":"{{ password2.value }}"},{"key":"new_password","value":"{{ password3.value }}"}]'
    }
    bodyType="json"
    cookies="[]"
    headers={
      '[{"key":"Content-Type","value":"application/json"},{"key":"Authorization","value":"Token {{ currentUser.value.token }}"},{"key":"","value":""}]'
    }
    isMultiplayerEdited={false}
    query="https://server-production-e754.up.railway.app/change-password/"
    resourceName="REST-WithoutResource"
    resourceTypeOverride=""
    runWhenModelUpdates={false}
    type="PUT"
  >
    <Event
      event="success"
      method="hide"
      params={{}}
      pluginId="modalChangePassword"
      type="widget"
      waitMs="0"
      waitType="debounce"
    />
    <Event
      enabled={'{{ url.href.split("/").pop() == "login" }}'}
      event="success"
      method="openPage"
      params={{
        options: { map: { passDataWith: "urlParams" } },
        pageName: "home",
      }}
      pluginId=""
      type="util"
      waitMs="0"
      waitType="debounce"
    />
  </RESTQuery>
  <RESTQuery
    id="users_get"
    headers={
      '[{"key":"content-type","value":"application/json"},{"key":"authorization","value":"token {{ currentUser.value.token }}"}]'
    }
    isHidden={false}
    isMultiplayerEdited={false}
    query="{{ baseUrl.value }}/api/core/users/"
    resourceName="REST-WithoutResource"
    resourceTypeOverride=""
  />
  <RESTQuery
    id="user_admin_reset"
    body={
      '[{"key":"username","value":"{{ select20.selectedItem.username}}"},{"key":"new_password","value":"{{ password3.value }}"}]'
    }
    bodyType="json"
    cookies="[]"
    headers={
      '[{"key":"Authorization","value":"Token {{ currentUser.value.token }}"},{"key":"Content-Type","value":"application/json"}]'
    }
    isMultiplayerEdited={false}
    query="https://server-production-e754.up.railway.app/force-reset-password/"
    resourceName="REST-WithoutResource"
    resourceTypeOverride=""
    runWhenModelUpdates={false}
    type="POST"
  >
    <Event
      event="success"
      method="hide"
      params={{}}
      pluginId="modalChangePassword"
      type="widget"
      waitMs="0"
      waitType="debounce"
    />
    <Event
      enabled={'{{ url.href.split("/").pop() == "login" }}'}
      event="success"
      method="openPage"
      params={{
        options: { map: { passDataWith: "urlParams" } },
        pageName: "home",
      }}
      pluginId=""
      type="util"
      waitMs="0"
      waitType="debounce"
    />
  </RESTQuery>
  <RESTQuery
    id="user_logout"
    body="[]"
    bodyType="json"
    cookies="[]"
    headers={
      '[{"key":"Authorization","value":"Token {{ currentUser.value.token }}"},{"key":"Content-Type","value":"application/json"}]'
    }
    isMultiplayerEdited={false}
    query="https://server-production-e754.up.railway.app/logout"
    resourceName="REST-WithoutResource"
    resourceTypeOverride=""
    runWhenModelUpdates={false}
    type="POST"
  >
    <Event
      event="success"
      method="setValue"
      params={{ map: { value: '""' } }}
      pluginId="currentUser"
      type="state"
      waitMs="0"
      waitType="debounce"
    />
    <Event
      event="success"
      method="openPage"
      params={{
        options: { map: { passDataWith: "urlParams" } },
        pageName: "login",
      }}
      pluginId=""
      type="util"
      waitMs="0"
      waitType="debounce"
    />
    <Event
      event="success"
      method="setValue"
      params={{ key: "currentUser", newValue: '""' }}
      pluginId=""
      type="localStorage"
      waitMs="0"
      waitType="debounce"
    />
  </RESTQuery>
  <State id="SelectedUserMode" />
  <RESTQuery
    id="users_edit"
    body="{{ form19.data }}"
    bodyType="raw"
    headers={
      '[{"key":"Authorization","value":"Token {{ currentUser.value.token }}"},{"key":"Content-Type","value":"application/json"}]'
    }
    isMultiplayerEdited={false}
    query="{{ baseUrl.value }}/api/core/users/{{ usernameInput2.selectedItem.id }}"
    resourceName="REST-WithoutResource"
    resourceTypeOverride=""
    runWhenModelUpdates={false}
    type="PUT"
  >
    <Event
      event="success"
      method="trigger"
      params={{}}
      pluginId="users_get"
      type="datasource"
      waitMs="0"
      waitType="debounce"
    />
    <Event
      event="success"
      method="hide"
      params={{}}
      pluginId="modalNewUser"
      type="widget"
      waitMs="0"
      waitType="debounce"
    />
  </RESTQuery>
  <RESTQuery
    id="users_new"
    body="{{ form19.data }}"
    bodyType="raw"
    headers={
      '[{"key":"Authorization","value":"Token {{ currentUser.value.token }}"},{"key":"Content-Type","value":"application/json"}]'
    }
    isMultiplayerEdited={false}
    query="{{ baseUrl.value }}/users/create/"
    resourceName="REST-WithoutResource"
    resourceTypeOverride=""
    runWhenModelUpdates={false}
    type="POST"
  >
    <Event
      event="success"
      method="trigger"
      params={{}}
      pluginId="users_get"
      type="datasource"
      waitMs="0"
      waitType="debounce"
    />
    <Event
      event="success"
      method="hide"
      params={{}}
      pluginId="modalNewUser"
      type="widget"
      waitMs="0"
      waitType="debounce"
    />
  </RESTQuery>
  <State id="ErrorMessage" />
  <RESTQuery
    id="bulk_import_preview5"
    body={
      '[{"key":"file","value":"{{ fileButton1.value[0] }}","operation":"binary"},{"key":"commit","value":"False","operation":"text"},{"key":"company_id","value":"4","operation":"text"}]'
    }
    bodyType="form-data"
    cookies={'[{"key":"","value":""}]'}
    headers={
      '[{"key":"content-type","value":"application/json"},{"key":"authorization","value":"token {{ currentUser.value.token }}"}]'
    }
    isHidden={false}
    isMultiplayerEdited={false}
    query="{{ baseUrl.value }}/api/core/bulk-import/?"
    queryDisabled="{{ tenant_subdomain.value == null }}"
    queryTimeout="120000"
    resourceName="REST-WithoutResource"
    resourceTypeOverride=""
    runWhenModelUpdates={false}
    type="POST"
  />
  <RESTQuery
    id="bulk_import_execute2"
    body={
      '[{"key":"file","value":"{{ fileButton1.value[0] }}","operation":"binary"},{"key":"commit","value":"true","operation":"text"},{"key":"company_id","value":"4","operation":"text"}]'
    }
    bodyType="form-data"
    cookies={'[{"key":"","value":""}]'}
    headers={
      '[{"key":"content-type","value":"application/json"},{"key":"authorization","value":"token {{ currentUser.value.token }}"}]'
    }
    isHidden={false}
    isMultiplayerEdited={false}
    query="{{ baseUrl.value }}/api/core/bulk-import/"
    queryDisabled="{{ tenant_subdomain.value == null }}"
    queryTimeout="600000"
    resourceName="REST-WithoutResource"
    resourceTypeOverride=""
    runWhenModelUpdates={false}
    type="POST"
  >
    <Event
      event="success"
      method="hide"
      params={{}}
      pluginId="modalGeneralImport"
      type="widget"
      waitMs="0"
      waitType="debounce"
    />
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
  <State id="baseUrl" value="https://server-production-e754.up.railway.app" />
  <State
    id="queryHeaders"
    value={
      '{Content-Type: "application/json",\nAuthorization: "Token {{ currentUser.value.token }}"}'
    }
  />
  <RESTQuery
    id="bulk_import_preview6"
    body={
      '[{"key":"file","value":"{{ fileButton1.value[0] }}","operation":"binary"},{"key":"commit","value":"False","operation":"text"},{"key":"company_id","value":"4","operation":"text"}]'
    }
    bodyType="form-data"
    cookies={'[{"key":"","value":""}]'}
    headers={
      '[{"key":"content-type","value":"application/json"},{"key":"authorization","value":"token {{ currentUser.value.token }}"}]'
    }
    isHidden={false}
    isMultiplayerEdited={false}
    query="{{ baseUrl.value }}/api/core/bulk-import-preview/?"
    queryDisabled="{{ tenant_subdomain.value == null }}"
    queryTimeout="600000"
    resourceName="REST-WithoutResource"
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
  <RetoolAIQuery
    id="llmChat1_query2"
    action="chatResponseGeneration"
    chatHistory="{{ llmChat1.messageHistory }}"
    chatInput="{{ llmChat1.lastMessage }}"
    defaultModelInitialized={true}
    resourceDisplayName="retool_ai"
    resourceName="retool_ai"
  />
  <RetoolAIQuery
    id="llmChat2_query1"
    action="chatResponseGeneration"
    chatHistory="{{ llmChat2.messageHistory }}"
    chatInput="{{ llmChat2.lastMessage }}"
    resourceDisplayName="retool_ai"
    resourceName="retool_ai"
  />
  <RESTQuery
    id="embedding_missing_counts"
    headers={
      '[{"key":"content-type","value":"application/json"},{"key":"authorization","value":"token {{ currentUser.value.token }}"}]'
    }
    isHidden={false}
    isMultiplayerEdited={false}
    query="{{ baseUrl.value }}/{{ SelectedTenant.value.subdomain }}/embeddings/missing-counts/"
    queryDisabled={
      '{{ currentUser.value == null || SelectedTenant.value== "" || SelectedTenant.value ==null }}'
    }
    queryRefreshTime="30000"
    queryTimeout="6000"
    resourceName="REST-WithoutResource"
    resourceTypeOverride=""
    watchedParams={["SelectedTenant.id"]}
  />
  <RESTQuery
    id="embeddings_backfill"
    _additionalScope={[]}
    bodyType="raw"
    cookies={'[{"key":"","value":""}]'}
    headers={
      '[{"key":"authorization","value":"token {{ currentUser.value.token }}"},{"key":"Content-Type","value":"application/json"}]'
    }
    isHidden={false}
    isMultiplayerEdited={false}
    query="{{ baseUrl.value }}/{{ SelectedTenant.value.subdomain }}/embeddings/backfill/"
    queryDisabled="{{ tenant_subdomain.value == null }}"
    queryTimeout="600"
    resourceName="REST-WithoutResource"
    resourceTypeOverride=""
    runWhenModelUpdates={false}
    successMessage="{{ JSON.stringify(self.data) }}"
    type="POST"
  />
  <State id="authToken" value={'""'} />
  <State id="authExpiresAt" value="15" />
  <JavascriptQuery
    id="restoreSessionOnLoad"
    isMultiplayerEdited={false}
    notificationDuration={4.5}
    resourceName="JavascriptQuery"
    runWhenPageLoads={true}
    showSuccessToaster={false}
  />
  <RESTQuery
    id="bulk_import_ETL"
    body={
      '[{"key":"file","value":"{{ fileButton2.value[0] }}","operation":"binary"},{"key":"commit","value":"False","operation":"text"},{"key":"company_id","value":"4","operation":"text"}]'
    }
    bodyType="form-data"
    cookies={'[{"key":"","value":""}]'}
    headers={
      '[{"key":"content-type","value":"application/json"},{"key":"authorization","value":"token {{ currentUser.value.token }}"}]'
    }
    isHidden={false}
    isMultiplayerEdited={false}
    query="{{ baseUrl.value }}/api/core/etl/preview/"
    queryDisabled="{{ tenant_subdomain.value == null }}"
    queryTimeout="600000"
    resourceName="REST-WithoutResource"
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
</GlobalFunctions>
