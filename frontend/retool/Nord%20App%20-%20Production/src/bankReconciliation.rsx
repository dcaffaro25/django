<Screen
  id="bankReconciliation"
  _customShortcuts={[]}
  _hashParams={[]}
  _searchParams={[]}
  browserTitle=""
  title={null}
  urlSlug=""
  uuid="a8eb5eea-246c-45c0-9ec7-18d75c3ad43b"
>
  <RESTQuery
    id="OFXTransaction_import"
    body={'{\n  "files":{{ fileDropzoneOFX.value }}\n}'}
    bodyType="raw"
    cookies={'[{"key":"","value":""}]'}
    headers={
      '[{"key":"Content-Type","value":"application/json"},{"key":"authorization","value":"token {{ currentUser.value.token }}"}]'
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
    id="BankAccount_get"
    cacheKeyTtl={300}
    cookies={'[{"key":"","value":""}]'}
    enableCaching={true}
    headers={
      '[{"key":"Content-Type","value":"application/json"},{"key":"authorization","value":"token {{ currentUser.value.token }}"}]'
    }
    isHidden={false}
    isMultiplayerEdited={false}
    query="{{ baseUrl.value }}/{{ tenant_subdomain.value }}/api/bank_accounts/"
    queryDisabled="{{ tenant_subdomain.value == null }}"
    resourceName="REST-WithoutResource"
    resourceTypeOverride=""
  />
  <RESTQuery
    id="Bank_get"
    cookies={'[{"key":"","value":""}]'}
    headers={
      '[{"key":"Content-Type","value":"application/json"},{"key":"authorization","value":"token {{ currentUser.value.token }}"}]'
    }
    isHidden={false}
    isMultiplayerEdited={false}
    query="{{ baseUrl.value }}/{{ tenant_subdomain.value }}/api/banks/"
    queryDisabled="{{ tenant_subdomain.value == null }}"
    resourceName="REST-WithoutResource"
    resourceTypeOverride=""
  />
  <Function
    id="transformOFX"
    funcBody={include("../lib/transformOFX.js", "string")}
    runBehavior="debounced"
  />
  <State
    id="manageBanks"
    value={
      '{\n"userToken": {{ currentUser.value.token }},\n"baseUrl": {{ baseUrl.value }},\n"endpoint_path": "api/banks/",\n"tenant": 4,\n"current_record": [],\n"nome_plural": "Bancos",\n"nome_singular": "Banco",\n"masculino":true,\n"form_key": "name",\n"show_value": "name",\n"menu_visible": true,\n"modal_list_show": false,\n"modal_addedit_show": false,\n"form_fields": \n{\n"name":{\n    "default_value":"teste",\n    "disabled":false},\n"country":{\n    "default_value":"Brasil",\n    "disabled":false}\n}\n}'
    }
  />
  <JavascriptQuery
    id="updateInput"
    notificationDuration={4.5}
    resourceName="JavascriptQuery"
    showSuccessToaster={false}
  />
  <State
    id="manageBankAccounts"
    value={
      '{\n"endpoint_path": "api/bank_accounts/",\n"auxiliar_endpoints": ["api/entities/", "api/banks/", "api/currencies/"],\n"tenant": {{ tenant_subdomain.value }},\n"current_record": [],\n"nome_plural": "Contas Bancárias",\n"nome_singular": "Conta Bancária",\n"masculino":false,\n"form_key": "name",\n"show_value": "name",\n"menu_visible": true,\n"modal_list_show": false,\n"modal_addedit_show": false,\n"form_fields": \n{\n"name":{\n    "default_value":"teste",\n    "disabled":true}\n}\n}'
    }
  />
  <RESTQuery
    id="OFXTransaction_import2"
    _additionalScope={["content"]}
    body="{{ content }}"
    bodyType="raw"
    cookies={'[{"key":"","value":""}]'}
    headers={
      '[{"key":"Content-Type","value":"application/json"},{"key":"authorization","value":"token {{ currentUser.value.token }}"}]'
    }
    isHidden={false}
    isMultiplayerEdited={false}
    query="{{ baseUrl.value }}/{{ tenant_subdomain.value }}/api/bank_transactions/finalize_ofx_import/"
    queryDisabled="{{ tenant_subdomain.value == null }}"
    resourceName="REST-WithoutResource"
    resourceTypeOverride=""
    runWhenModelUpdates={false}
    type="POST"
  />
  <RESTQuery
    id="BankTransactions_get"
    cookies={'[{"key":"","value":""}]'}
    headers={
      '[{"key":"Content-Type","value":"application/json"},{"key":"Authorization","value":"Token {{ currentUser.value.token }}"}]'
    }
    isHidden={false}
    isMultiplayerEdited={false}
    query="{{ baseUrl.value }}/{{ tenant_subdomain.value }}/api/bank_transactions/?unreconciled=true"
    queryDisabled="{{ tenant_subdomain.value == null }}"
    queryTimeout="100000"
    resourceName="REST-WithoutResource"
    resourceTypeOverride=""
  />
  <RESTQuery
    id="AccountingTransaction_import"
    body={
      '[{"key":"file","value":"{{ fileDropzoneBook.value[0] }}","operation":"binary"}]'
    }
    bodyType="form-data"
    cookies={'[{"key":"","value":""}]'}
    headers={
      '[{"key":"content-type","value":"application/json"},{"key":"authorization","value":"token {{ currentUser.value.token }}"}]'
    }
    isHidden={false}
    isMultiplayerEdited={false}
    query="{{ baseUrl.value }}/{{ tenant_subdomain.value }}/api/transactions/bulk_import/"
    queryDisabled="{{ tenant_subdomain.value == null }}"
    resourceName="REST-WithoutResource"
    resourceTypeOverride=""
    runWhenModelUpdates={false}
    type="POST"
  />
  <RESTQuery
    id="BookTransactions_get"
    cookies={'[{"key":"","value":""}]'}
    headers={
      '[{"key":"content-type","value":"application/json"},{"key":"authorization","value":"token {{ currentUser.value.token }}"}]'
    }
    isHidden={false}
    isMultiplayerEdited={false}
    query="{{ baseUrl.value }}/{{ tenant_subdomain.value }}/api/journal_entries/unmatched/"
    queryDisabled="{{ tenant_subdomain.value == null }}"
    queryTimeout="600000"
    resourceName="REST-WithoutResource"
    resourceTypeOverride=""
  />
  <RESTQuery
    id="Reconciliation_propose"
    body="{{ BankReconciliationParameters.value }}"
    bodyType="raw"
    cookies={'[{"key":"","value":""}]'}
    headers={
      '[{"key":"Content-Type","value":"application/json"},{"key":"authorization","value":"token {{ currentUser.value.token }}"}]'
    }
    isHidden={false}
    isMultiplayerEdited={false}
    query="{{ baseUrl.value }}/{{ tenant_subdomain.value }}/api/bank_transactions/match_many_to_many/"
    queryDisabled="{{ tenant_subdomain.value == null }}"
    resourceName="REST-WithoutResource"
    resourceTypeOverride=""
    runWhenModelUpdates={false}
    type="POST"
  />
  <RESTQuery
    id="OFXTransaction_import3"
    _additionalScope={["content"]}
    body="{{ content }}"
    bodyType="raw"
    cookies={'[{"key":"","value":""}]'}
    headers={
      '[{"key":"Content-Type","value":"application/json"},{"key":"authorization","value":"token {{ currentUser.value.token }}"}]'
    }
    isHidden={false}
    isMultiplayerEdited={false}
    query="{{ baseUrl.value }}/{{ tenant_subdomain.value }}/api/bank_transactions/finalize_ofx_import2/"
    queryDisabled="{{ tenant_subdomain.value == null }}"
    resourceName="REST-WithoutResource"
    resourceTypeOverride=""
    runWhenModelUpdates={false}
    type="POST"
  />
  <RESTQuery
    id="Transactions_get3"
    body="{{ BankReconciliationParameters2.value }}"
    bodyType="raw"
    cookies={'[{"key":"","value":""}]'}
    headers={
      '[{"key":"Content-Type","value":"application/json"},{"key":"authorization","value":"token {{ currentUser.value.token }}"}]'
    }
    isHidden={false}
    isMultiplayerEdited={false}
    query="{{ baseUrl.value }}/{{ tenant_subdomain.value }}/api/bank_transactions/match_many_to_many_with_set2/"
    queryDisabled="{{ tenant_subdomain.value == null }}"
    queryTimeout="600000"
    resourceName="REST-WithoutResource"
    resourceTypeOverride=""
    runWhenModelUpdates={false}
    type="POST"
  />
  <Function
    id="groupedBankTransactions"
    funcBody={include("../lib/groupedBankTransactions.js", "string")}
    runBehavior="debounced"
  />
  <Function
    id="groupedTransactions"
    funcBody={include("../lib/groupedTransactions.js", "string")}
    runBehavior="debounced"
  />
  <Function
    id="ReconciliationParameters"
    funcBody={include("../lib/ReconciliationParameters.js", "string")}
    runBehavior="debounced"
  />
  <RESTQuery
    id="MatchRecords_post"
    _additionalScope={["content"]}
    body="{{ content }}"
    bodyType="raw"
    cookies={'[{"key":"","value":""}]'}
    headers={
      '[{"key":"Content-Type","value":"application/json"},{"key":"authorization","value":"token {{ currentUser.value.token }}"}]'
    }
    isHidden={false}
    isMultiplayerEdited={false}
    query="{{ baseUrl.value }}/{{ tenant_subdomain.value }}/api/bank_transactions/finalize_reconciliation_matches/"
    queryDisabled="{{ tenant_subdomain.value == null }}"
    queryTimeout="600000"
    resourceName="REST-WithoutResource"
    resourceTypeOverride=""
    runWhenModelUpdates={false}
    type="POST"
  />
  <RESTQuery
    id="Conciliation_get"
    cookies={'[{"key":"","value":""}]'}
    headers={
      '[{"key":"content-type","value":"application/json"},{"key":"authorization","value":"token {{ currentUser.value.token }}"}]'
    }
    isHidden={false}
    isMultiplayerEdited={false}
    query="{{ baseUrl.value }}/{{ tenant_subdomain.value }}/api/reconciliation/summaries/"
    queryDisabled="{{ tenant_subdomain.value == null }}"
    queryTimeout="100000"
    resourceName="REST-WithoutResource"
    resourceTypeOverride=""
  />
  <State
    id="ReconciliationMatches"
    value="{{ Transactions_get3.data.suggestions }}"
  />
  <RESTQuery
    id="Transactions_get4"
    body="{{ BankReconciliationParameters2.value }}"
    bodyType="raw"
    cookies={'[{"key":"","value":""}]'}
    headers={
      '[{"key":"Content-Type","value":"application/json"},{"key":"authorization","value":"token {{ currentUser.value.token }}"}]'
    }
    isHidden={false}
    isMultiplayerEdited={false}
    query="{{ baseUrl.value }}/{{ tenant_subdomain.value }}/api/bank_transactions/match_many_to_many_with_set2/"
    queryDisabled="{{ tenant_subdomain.value == null }}"
    queryTimeout="100000"
    resourceName="REST-WithoutResource"
    resourceTypeOverride=""
    runWhenModelUpdates={false}
    type="POST"
  />
  <JavascriptQuery
    id="VisibleBookIds"
    isMultiplayerEdited={false}
    notificationDuration={4.5}
    query={include("../lib/VisibleBookIds.js", "string")}
    resourceName="JavascriptQuery"
    showSuccessToaster={false}
  />
  <State id="ReconParameters" />
  <JavascriptQuery
    id="VisibleBankIds"
    isMultiplayerEdited={false}
    notificationDuration={4.5}
    query={include("../lib/VisibleBankIds.js", "string")}
    resourceName="JavascriptQuery"
    showSuccessToaster={false}
  />
  <RESTQuery
    id="Conciliation_delete"
    body="{{
  (table56.selectedRows?.length > 0
    ? table56.selectedRows.map(row => row.reconciliation_id)
    : [Conciliation_selected.value]
  )
}}"
    bodyType="raw"
    headers={
      '[{"key":"Content-Type","value":"application/json"},{"key":"authorization","value":"token {{ currentUser.value.token }}"}]'
    }
    isMultiplayerEdited={false}
    query="{{ baseUrl.value }}/{{ tenant_subdomain.value }}/api/reconciliation/bulk_delete/"
    resourceName="REST-WithoutResource"
    resourceTypeOverride=""
    runWhenModelUpdates={false}
    type="DELETE"
  >
    <Event
      event="success"
      method="trigger"
      params={{}}
      pluginId="Conciliation_get"
      type="datasource"
      waitMs="0"
      waitType="debounce"
    />
  </RESTQuery>
  <State id="Conciliation_selected" />
  <RESTQuery
    id="Entity_get"
    cacheKeyTtl={300}
    cookies={'[{"key":"","value":""}]'}
    enableCaching={true}
    headers={
      '[{"key":"Content-Type","value":"application/json"},{"key":"authorization","value":"token {{ currentUser.value.token }}"}]'
    }
    isHidden={false}
    isMultiplayerEdited={false}
    query="{{ baseUrl.value }}/{{ tenant_subdomain.value }}/api/entities-mini/"
    queryDisabled="{{ tenant_subdomain.value == null }}"
    queryTimeout="100000"
    resourceName="REST-WithoutResource"
    resourceTypeOverride=""
  />
  <RESTQuery
    id="Reconciliate_get"
    body="{{ BankReconciliationParameters2.value }}"
    bodyType="raw"
    cookies={'[{"key":"","value":""}]'}
    headers={
      '[{"key":"Content-Type","value":"application/json"},{"key":"authorization","value":"token {{ currentUser.value.token }}"}]'
    }
    isHidden={false}
    isMultiplayerEdited={false}
    query="{{ baseUrl.value }}/{{ tenant_subdomain.value }}/api/reconciliation-tasks/start/"
    queryDisabled="{{ tenant_subdomain.value == null }}"
    queryTimeout="600000"
    resourceName="REST-WithoutResource"
    resourceTypeOverride=""
    runWhenModelUpdates={false}
    type="POST"
  />
  <RESTQuery
    id="ReconciliationTasks_get"
    cacheKeyTtl={300}
    cookies={'[{"key":"","value":""}]'}
    enableCaching={true}
    headers={
      '[{"key":"Content-Type","value":"application/json"},{"key":"authorization","value":"token {{ currentUser.value.token }}"}]'
    }
    isHidden={false}
    isMultiplayerEdited={false}
    query="{{ baseUrl.value }}/{{ tenant_subdomain.value }}/api/reconciliation-tasks/5/status/"
    queryDisabled="{{ tenant_subdomain.value == null }}"
    queryTimeout="100000"
    resourceName="REST-WithoutResource"
    resourceTypeOverride=""
  />
  <RESTQuery
    id="Reconciliation_execute"
    _additionalScope={["payload"]}
    body="{{ payload}}"
    bodyType="raw"
    cookies={'[{"key":"","value":""}]'}
    headers={
      '[{"key":"authorization","value":"token {{ currentUser.value.token }}"},{"key":"Content-Type","value":"application/json"}]'
    }
    isHidden={false}
    isMultiplayerEdited={false}
    query="{{ baseUrl.value }}/{{ tenant_subdomain.value }}/api/reconciliation-tasks/start/"
    queryDisabled="{{ tenant_subdomain.value == null }}"
    queryTimeout="600"
    resourceName="REST-WithoutResource"
    resourceTypeOverride=""
    runWhenModelUpdates={false}
    type="POST"
  />
  <RESTQuery
    id="Queue_get"
    cookies={'[{"key":"","value":""}]'}
    headers={
      '[{"key":"Content-Type","value":"application/json"},{"key":"Authorization","value":"token {{ currentUser.value.token }}"}]'
    }
    isHidden={false}
    isMultiplayerEdited={false}
    query="{{ baseUrl.value }}/{{ tenant_subdomain.value }}/api/reconciliation-tasks/queued/?hours_ago={{ buttonGroupLegacy1.value }}"
    queryDisabled="{{ tenant_subdomain.value == null }}"
    queryTimeout="100000"
    resourceName="REST-WithoutResource"
    resourceTypeOverride=""
  />
  <RESTQuery
    id="QueueCount_get"
    cookies={'[{"key":"","value":""}]'}
    headers={
      '[{"key":"Content-Type","value":"application/json"},{"key":"authorization","value":"token {{ currentUser.value.token }}"}]'
    }
    isHidden={false}
    isMultiplayerEdited={false}
    query="{{ baseUrl.value }}/{{ tenant_subdomain.value }}/api/reconciliation-tasks/task_counts/?hours_ago={{ buttonGroupLegacy1.value }}
"
    queryDisabled="{{ tenant_subdomain.value == null }}"
    queryTimeout="100000"
    resourceName="REST-WithoutResource"
    resourceTypeOverride=""
  />
  <State
    id="colorTagStatusQueue"
    value={
      '{{{ \n        "running": theme.warning,\n        "completed": theme.success,\n        "queued": "n.a.",\n        "failed": theme.danger,\n    }}}'
    }
  />
  <RESTQuery
    id="ReconConfig_get"
    cookies={'[{"key":"","value":""}]'}
    headers={
      '[{"key":"Content-Type","value":"application/json"},{"key":"authorization","value":"token {{ currentUser.value.token }}"}]'
    }
    isHidden={false}
    isMultiplayerEdited={false}
    query="{{ baseUrl.value }}/{{ tenant_subdomain.value }}/api/reconciliation_configs/"
    queryDisabled="{{ tenant_subdomain.value == null }}"
    queryTimeout="100000"
    resourceName="REST-WithoutResource"
    resourceTypeOverride=""
  >
    <Event
      event="success"
      method="trigger"
      params={{}}
      pluginId="ReconCounts_compute"
      type="datasource"
      waitMs="0"
      waitType="debounce"
    />
  </RESTQuery>
  <State id="selectedReconConfig" />
  <State id="ReconConfig_mode" />
  <RESTQuery
    id="ml_model_train"
    _additionalScope={["payload"]}
    body="{{ payload }}"
    bodyType="raw"
    cookies={'[{"key":"","value":""}]'}
    headers={
      '[{"key":"Content-Type","value":"application/json"},{"key":"authorization","value":"token {{ currentUser.value.token }}"}]'
    }
    isHidden={false}
    isMultiplayerEdited={false}
    query="{{ baseUrl.value }}/{{ tenant_subdomain.value }}/ml-models/train/"
    queryDisabled="{{ tenant_subdomain.value == null }}"
    queryTimeout="600000"
    resourceDisplayName="Tenant Specific - Production"
    resourceName="db4d0175-aa88-429c-ba3f-f4bbd2c875e3"
    resourceTypeOverride=""
    runWhenModelUpdates={false}
    type="POST"
  />
  <RESTQuery
    id="ml_model_get"
    cookies={'[{"key":"","value":""}]'}
    headers={
      '[{"key":"Content-Type","value":"application/json"},{"key":"authorization","value":"token {{ currentUser.value.token }}"}]'
    }
    isHidden={false}
    isMultiplayerEdited={false}
    query="{{ baseUrl.value }}/{{ tenant_subdomain.value }}/ml-models/1/"
    queryDisabled="{{ tenant_subdomain.value == null }}"
    queryTimeout="100000"
    resourceName="REST-WithoutResource"
    resourceTypeOverride=""
  />
  <RESTQuery
    id="ReconConfig_run"
    body="{{ form16.data }}"
    bodyType="raw"
    cookies={'[{"key":"","value":""}]'}
    headers={
      '[{"key":"Content-Type","value":"application/json"},{"key":"authorization","value":"token {{ currentUser.value.token }}"}]'
    }
    isHidden={false}
    isMultiplayerEdited={false}
    query="{{ baseUrl.value }}/{{ tenant_subdomain.value }}/api/reconciliation_configs/"
    queryDisabled="{{ tenant_subdomain.value == null }}"
    queryTimeout="100000"
    resourceName="REST-WithoutResource"
    resourceTypeOverride=""
    runWhenModelUpdates={false}
    type="POST"
  >
    <Event
      event="success"
      method="hide"
      params={{}}
      pluginId="modalNewEditReconShortcut"
      type="widget"
      waitMs="0"
      waitType="debounce"
    />
  </RESTQuery>
  <SqlTransformQuery
    id="check_login2"
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
    id="ml_model_predict"
    _additionalScope={["payload"]}
    body="{{ payload }}"
    bodyType="raw"
    cookies={'[{"key":"","value":""}]'}
    headers={
      '[{"key":"Content-Type","value":"application/json"},{"key":"Authorization","value":"Token {{ currentUser.value.token }}"}]'
    }
    isHidden={false}
    isMultiplayerEdited={false}
    query="{{ baseUrl.value }}/{{ tenant_subdomain.value }}/ml-models/predict/"
    queryDisabled="{{ tenant_subdomain.value == null }}"
    queryTimeout="600000"
    resourceName="REST-WithoutResource"
    resourceTypeOverride=""
    runWhenModelUpdates={false}
    type="POST"
  />
  <RESTQuery
    id="ReconConfig_new"
    body="{{ form16.data }}"
    bodyType="raw"
    cookies={'[{"key":"","value":""}]'}
    headers={
      '[{"key":"Content-Type","value":"application/json"},{"key":"authorization","value":"token {{ currentUser.value.token }}"}]'
    }
    isHidden={false}
    isMultiplayerEdited={false}
    query="{{ baseUrl.value }}/{{ tenant_subdomain.value }}/api/reconciliation_configs/"
    queryDisabled="{{ tenant_subdomain.value == null }}"
    queryTimeout="100000"
    resourceName="REST-WithoutResource"
    resourceTypeOverride=""
    runWhenModelUpdates={false}
    type="POST"
  >
    <Event
      event="success"
      method="hide"
      params={{}}
      pluginId="modalNewEditReconShortcut"
      type="widget"
      waitMs="0"
      waitType="debounce"
    />
    <Event
      event="success"
      method="trigger"
      params={{}}
      pluginId="ReconConfig_get"
      type="datasource"
      waitMs="0"
      waitType="debounce"
    />
  </RESTQuery>
  <RESTQuery
    id="ReconConfig_edit"
    body="{{ form16.data }}"
    bodyType="raw"
    cookies={'[{"key":"","value":""}]'}
    headers={
      '[{"key":"Content-Type","value":"application/json"},{"key":"authorization","value":"token {{ currentUser.value.token }}"}]'
    }
    isHidden={false}
    isMultiplayerEdited={false}
    query="{{ baseUrl.value }}/{{ tenant_subdomain.value }}/api/reconciliation_configs/{{ selectedReconConfig.value.id }}/"
    queryDisabled="{{ tenant_subdomain.value == null }}"
    queryTimeout="100000"
    resourceName="REST-WithoutResource"
    resourceTypeOverride=""
    runWhenModelUpdates={false}
    type="PUT"
  >
    <Event
      event="success"
      method="hide"
      params={{}}
      pluginId="modalNewEditReconShortcut"
      type="widget"
      waitMs="0"
      waitType="debounce"
    />
    <Event
      event="success"
      method="trigger"
      params={{}}
      pluginId="ReconConfig_get"
      type="datasource"
      waitMs="0"
      waitType="debounce"
    />
  </RESTQuery>
  <State id="stateRuleCounts" />
  <JavascriptQuery
    id="ReconCounts_compute"
    isMultiplayerEdited={false}
    notificationDuration={4.5}
    query={include("../lib/ReconCounts_compute.js", "string")}
    resourceName="JavascriptQuery"
    showSuccessToaster={false}
  />
  <JavascriptQuery
    id="ReconCounts_compute2"
    notificationDuration={4.5}
    query={include("../lib/ReconCounts_compute2.js", "string")}
    resourceName="JavascriptQuery"
    showSuccessToaster={false}
  />
  <RESTQuery
    id="Conciliation_get3"
    cookies={'[{"key":"","value":""}]'}
    headers={
      '[{"key":"content-type","value":"application/json"},{"key":"authorization","value":"token {{ currentUser.value.token }}"}]'
    }
    isHidden={false}
    isMultiplayerEdited={false}
    query="{{ baseUrl.value }}/{{ tenant_subdomain.value }}/api/reconciliation/summaries/"
    queryDisabled="{{ tenant_subdomain.value == null }}"
    queryTimeout="100000"
    resourceName="REST-WithoutResource"
    resourceTypeOverride=""
  />
  <RESTQuery
    id="JournalEntries_get2"
    cookies={'[{"key":"","value":""}]'}
    headers={
      '[{"key":"content-type","value":"application/json"},{"key":"authorization","value":"token {{ currentUser.value.token }}"}]'
    }
    isHidden={false}
    isMultiplayerEdited={false}
    query="{{ baseUrl.value }}/{{ tenant_subdomain.value }}/api/journal_entries/?unreconciled=true"
    queryDisabled="{{ tenant_subdomain.value == null }}"
    queryTimeout="600000"
    resourceName="REST-WithoutResource"
    resourceTypeOverride=""
  />
  <RESTQuery
    id="Chat_ask"
    body={
      '{\n  "model": "llama3.2:1b-instruct-q4_K_M",\n  "prompt": "Explain like I\'m five: what is 1+1?",\n  "stream": false,\n  "keep_alive": "30m",\n  "options": {\n    "num_predict": 32,\n    "temperature": 0.1,\n    "top_p": 0.9,\n    "num_thread": 8\n  }\n}'
    }
    bodyType="raw"
    cookies={'[{"key":"","value":""}]'}
    headers={
      '[{"key":"content-type","value":"application/json"},{"key":"authorization","value":"token {{ currentUser.value.token }}"}]'
    }
    isHidden={false}
    isMultiplayerEdited={false}
    query="https://chat-service-production-d54a.up.railway.app/api/generate/"
    queryDisabled="{{ tenant_subdomain.value == null }}"
    queryTimeout="600000"
    resourceName="REST-WithoutResource"
    resourceTypeOverride=""
    runWhenModelUpdates={false}
    type="POST"
  />
  <RESTQuery
    id="Chat_ask3"
    body={
      '{\n      "query": "bancária",\n      "k_each": 8,\n      "company_id": 4,\n      "min_similarity": 0.1,\n      "model": "nomic-embed-text"\n    }'
    }
    bodyType="raw"
    cookies={'[{"key":"","value":""}]'}
    headers={
      '[{"key":"content-type","value":"application/json"},{"key":"authorization","value":"token {{ currentUser.value.token }}"}]'
    }
    isHidden={false}
    isMultiplayerEdited={false}
    query="{{ baseUrl.value }}/4/embeddings/search/?"
    queryDisabled="{{ tenant_subdomain.value == null }}"
    queryTimeout="600000"
    resourceName="REST-WithoutResource"
    resourceTypeOverride=""
    runWhenModelUpdates={false}
    type="POST"
  />
  <RetoolAIQuery
    id="llmChat1_query1"
    action="chatResponseGeneration"
    chatHistory="{{ llmChat1.messageHistory }}"
    chatInput="{{ llmChat1.lastMessage }}"
    customTemperature="0.2"
    defaultModelInitialized={true}
    dynamicModelName="Teste"
    resourceDisplayName="retool_ai"
    resourceName="retool_ai"
  />
  <Function
    id="transformer10"
    funcBody={include("../lib/transformer10.js", "string")}
  />
  <RetoolAIQuery
    id="llmChat2_query2"
    action="chatResponseGeneration"
    chatHistory="{{ llmChat2.messageHistory }}"
    chatInput="{{ llmChat2.lastMessage }}"
    resourceDisplayName="retool_ai"
    resourceName="retool_ai"
  />
  <RetoolAIQuery
    id="llmChat4_query1"
    action="chatResponseGeneration"
    chatHistory="{{ llmChat4.messageHistory }}"
    chatInput="{{ llmChat4.lastMessage }}"
    resourceDisplayName="retool_ai"
    resourceName="retool_ai"
  />
  <RetoolAIQuery
    id="llmChat4_query2"
    action="chatResponseGeneration"
    chatHistory="{{ llmChat4.messageHistory }}"
    chatInput="{{ llmChat4.lastMessage }}"
    resourceDisplayName="retool_ai"
    resourceName="retool_ai"
  />
  <RESTQuery
    id="Chat_ask2"
    body={
      '{\n  "model": "llama3.2:3b-instruct-q4_K_M",\n  "prompt": {{ JSON.stringify(llmChat4.messageHistory) }},\n  "stream": false,\n  "keep_alive": "30m",\n  "options": {\n    "num_predict": {{ ChatLength.value}},\n    "temperature": 0.2,\n    "top_p": 0.9,\n    "num_thread": 32\n  },\n  "mode": {{buttonGroupLegacy2.value}}\n}'
    }
    bodyType="raw"
    cookies={'[{"key":"","value":""}]'}
    enableTransformer={true}
    headers={
      '[{"key":"content-type","value":"application/json"},{"key":"authorization","value":"token {{ currentUser.value.token }}"}]'
    }
    isHidden={false}
    isMultiplayerEdited={false}
    query="{{ baseUrl.value }}/api/chat/ask/"
    queryDisabled="{{ tenant_subdomain.value == null }}"
    queryTimeout="600000"
    resourceName="REST-WithoutResource"
    resourceTypeOverride=""
    runWhenModelUpdates={false}
    transformer="const response = {{ data.response || 'world' }}

return response"
    type="POST"
  />
  <RESTQuery
    id="Reconciliation_get"
    _additionalScope={["payload"]}
    bodyType="raw"
    cookies={'[{"key":"","value":""}]'}
    headers={
      '[{"key":"authorization","value":"token {{ currentUser.value.token }}"},{"key":"Content-Type","value":"application/json"}]'
    }
    isHidden={false}
    isMultiplayerEdited={false}
    query="{{ baseUrl.value }}/{{ tenant_subdomain.value }}/api/reconciliation-tasks/{{ selectedReconRecord.value }} /fresh-suggestions/?limit=10000"
    queryDisabled="{{ tenant_subdomain.value == null }}"
    queryTimeout="600"
    resourceName="REST-WithoutResource"
    resourceTypeOverride=""
    successMessage="{{ JSON.stringify(self.data) }}"
    transformer=""
  />
  <State id="selectedReconRecord" />
  <RESTQuery
    id="BankTransactions_getMatched"
    cookies={'[{"key":"","value":""}]'}
    headers={
      '[{"key":"Content-Type","value":"application/json"},{"key":"Authorization","value":"Token {{ currentUser.value.token }}"}]'
    }
    isHidden={false}
    isMultiplayerEdited={false}
    query="{{ baseUrl.value }}/{{ tenant_subdomain.value }}/api/bank_transactions/?unreconciled=true"
    queryDisabled="{{ tenant_subdomain.value == null }}"
    queryTimeout="100000"
    resourceName="REST-WithoutResource"
    resourceTypeOverride=""
  />
  <RESTQuery
    id="ReconPipe_get"
    cookies={'[{"key":"","value":""}]'}
    headers={
      '[{"key":"Content-Type","value":"application/json"},{"key":"authorization","value":"token {{ currentUser.value.token }}"}]'
    }
    isHidden={false}
    isMultiplayerEdited={false}
    query="{{ baseUrl.value }}/{{ tenant_subdomain.value }}/api/reconciliation-pipelines/"
    queryDisabled="{{ tenant_subdomain.value == null }}"
    queryTimeout="100000"
    resourceName="REST-WithoutResource"
    resourceTypeOverride=""
  >
    <Event
      event="success"
      method="trigger"
      params={{}}
      pluginId="ReconCounts_compute"
      type="datasource"
      waitMs="0"
      waitType="debounce"
    />
  </RESTQuery>
  <RESTQuery
    id="Reconciliate_cancel"
    bodyType="raw"
    cookies={'[{"key":"","value":""}]'}
    headers={
      '[{"key":"Content-Type","value":"application/json"},{"key":"authorization","value":"token {{ currentUser.value.token }}"}]'
    }
    isHidden={false}
    isMultiplayerEdited={false}
    query="{{ baseUrl.value }}/{{ tenant_subdomain.value }}/api/reconciliation-tasks/{{ selectedReconRecord.value }}/cancel/"
    queryDisabled="{{ tenant_subdomain.value == null }}"
    queryTimeout="600000"
    resourceName="REST-WithoutResource"
    resourceTypeOverride=""
    runWhenModelUpdates={false}
    type="POST"
  />
  <RESTQuery
    id="BankSuggestions_get"
    _additionalScope={["payload"]}
    body="{{ payload}}"
    bodyType="raw"
    cookies={'[{"key":"","value":""}]'}
    headers={
      '[{"key":"authorization","value":"token {{ currentUser.value.token }}"},{"key":"Content-Type","value":"application/json"}]'
    }
    isHidden={false}
    isMultiplayerEdited={false}
    query="{{ baseUrl.value }}/{{ tenant_subdomain.value }}/api/bank_transactions/suggest_matches/"
    queryDisabled="{{ tenant_subdomain.value == null }}"
    queryTimeout="6000"
    resourceName="REST-WithoutResource"
    resourceTypeOverride=""
    runWhenModelUpdates={false}
    type="POST"
  />
  <RESTQuery
    id="createSuggestionsQuery"
    _additionalScope={["payload"]}
    body="{{ payload}}"
    bodyType="raw"
    confirmationMessage="teste"
    cookies={'[{"key":"","value":""}]'}
    headers={
      '[{"key":"authorization","value":"token {{ currentUser.value.token }}"},{"key":"Content-Type","value":"application/json"}]'
    }
    isHidden={false}
    isMultiplayerEdited={false}
    query="{{ baseUrl.value }}/{{ tenant_subdomain.value }}/api/bank_transactions/create_suggestions/"
    queryDisabled="{{ tenant_subdomain.value == null }}"
    queryTimeout="6000"
    requireConfirmation={true}
    resourceName="REST-WithoutResource"
    resourceTypeOverride=""
    runWhenModelUpdates={false}
    type="POST"
  />
  <Include src="./drawerAIChat.rsx" />
  <Include src="./modalFrame16.rsx" />
  <Include src="./modalFrame5.rsx" />
  <Include src="./modalImportOFX.rsx" />
  <Include src="./modalManualConciliation.rsx" />
  <Include src="./modalNewEditReconPipe.rsx" />
  <Include src="./modalNewEditReconShortcut.rsx" />
  <Include src="./modalReconCeleryQueue.rsx" />
  <Include src="./modalReconciled.rsx" />
  <Include src="./modalReconShortcuts.rsx" />
  <Frame
    id="$main8"
    enableFullBleed={false}
    isHiddenOnDesktop={false}
    isHiddenOnMobile={false}
    padding="8px 12px"
    sticky={null}
    type="main"
  >
    <Container
      id="tabbedContainer6"
      currentViewKey="{{ self.viewKeys[0] }}"
      enableFullBleed={true}
      footerPadding="4px 12px"
      headerPadding="4px 12px"
      heightType="fixed"
      overflowType="hidden"
      padding="12px"
      showBody={true}
      showBorder={false}
      showHeader={true}
      style={{ map: { background: "canvas" } }}
    >
      <Header>
        <Tabs
          id="tabs6"
          itemMode="static"
          navigateContainer={true}
          style={{
            fontSize: "h4Font",
            fontWeight: "h4Font",
            fontFamily: "h4Font",
          }}
          styleVariant="lineBottom"
          targetContainerId="tabbedContainer6"
          value="{{ self.values[0] }}"
        >
          <Option id="00030" value="Tab 1" />
          <Option id="00031" value="Tab 2" />
          <Option id="00032" value="Tab 3" />
        </Tabs>
      </Header>
      <View id="00030" viewKey="Transações Não Conciliadas">
        <Container
          id="group89"
          footerPadding="4px 12px"
          headerPadding="4px 12px"
          margin="0"
          padding="0"
          showBody={true}
          showBorder={false}
          style={{ map: { background: "rgba(255, 255, 255, 0)" } }}
        >
          <View id="00030" viewKey="View 1">
            <Container
              id="container28"
              enableFullBleed={true}
              footerPadding="4px 12px"
              headerPadding="4px 12px"
              heightType="fixed"
              overflowType="hidden"
              padding="12px"
              showBody={true}
              showBorder={false}
              showHeader={true}
              style={{ map: { headerBackground: "canvas" } }}
            >
              <Header>
                <Container
                  id="group100"
                  _gap="0px"
                  _justify="space-between"
                  _type="stack"
                  footerPadding="4px 12px"
                  headerPadding="4px 12px"
                  margin="0"
                  padding="0"
                  showBody={true}
                  showBorder={false}
                  style={{ map: { background: "rgba(255, 255, 255, 0)" } }}
                >
                  <View id="00030" viewKey="View 1">
                    <Text
                      id="containerTitle29"
                      value="#### Transações Pendentes de Conciliação"
                      verticalAlign="center"
                    />
                    <Button
                      id="button61"
                      style={{}}
                      styleVariant="outline"
                      text="Refreash All"
                    >
                      <Event
                        event="click"
                        method="run"
                        params={{
                          map: {
                            src: "BankTransactions_get.trigger();\nBookTransactions_get.trigger();\nReconciliation_get.trigger();",
                          },
                        }}
                        pluginId=""
                        type="script"
                        waitMs="0"
                        waitType="debounce"
                      />
                    </Button>
                  </View>
                </Container>
              </Header>
              <View id="00030" viewKey="View 1">
                <Container
                  id="group22"
                  _flexWrap={true}
                  _gap="0px"
                  footerPadding="4px 12px"
                  headerPadding="4px 12px"
                  margin="0"
                  padding="0"
                  showBody={true}
                  showBorder={false}
                  style={{ map: { background: "canvas" } }}
                >
                  <View id="c9c98" viewKey="View 1">
                    <Container
                      id="group98"
                      footerPadding="4px 12px"
                      headerPadding="4px 12px"
                      margin="0"
                      padding="0"
                      showBody={true}
                      showBorder={false}
                      style={{ map: { background: "rgba(255, 255, 255, 0)" } }}
                    >
                      <View id="00030" viewKey="View 1">
                        <Form
                          id="form21"
                          footerPadding="4px 12px"
                          headerPadding="4px 12px"
                          initialData={
                            '{"filterBankMinAmount": "",\n"filterBankMaxAmount": ""}'
                          }
                          padding="12px"
                          resetAfterSubmit={true}
                          showBody={true}
                        >
                          <Header>
                            <Text
                              id="formTitle36"
                              value="#### Form title"
                              verticalAlign="center"
                            />
                          </Header>
                          <Body>
                            <Include src="./group83.rsx" />
                          </Body>
                          <Footer>
                            <Button
                              id="formButton24"
                              submit={true}
                              submitTargetId="form21"
                              text="Submit"
                            />
                          </Footer>
                        </Form>
                        <Container
                          id="container29"
                          enableFullBleed={true}
                          footerPadding="4px 12px"
                          headerPadding="4px 12px"
                          heightType="fixed"
                          overflowType="hidden"
                          padding="12px"
                          showBody={true}
                          showHeader={true}
                        >
                          <Header>
                            <Text
                              id="containerTitle30"
                              value="#### Transações Banco"
                              verticalAlign="center"
                            />
                          </Header>
                          <View id="00030" viewKey="View 1">
                            <Table
                              id="tableBank"
                              actionsOverflowPosition={1}
                              cellSelection="none"
                              clearChangesetOnSave={true}
                              data="{{ BankTransactions_get.data }}"
                              defaultFilters={{
                                0: {
                                  id: "2f325",
                                  columnId: "ed9f5",
                                  operator: "isAfter",
                                  value:
                                    "{{ filterReconDateRange2.value.start }}",
                                  disabled: false,
                                },
                                1: {
                                  id: "542f5",
                                  columnId: "ed9f5",
                                  operator: "isBefore",
                                  value:
                                    "{{ filterReconDateRange2.value.end }}",
                                  disabled: false,
                                },
                                2: {
                                  id: "0c79c",
                                  columnId: "2478a",
                                  operator: ">=",
                                  value: "{{ filterBankMinAmount.value }}",
                                  disabled: false,
                                },
                                3: {
                                  id: "16626",
                                  columnId: "2478a",
                                  operator: "<=",
                                  value: "{{filterBankMaxAmount.value }}",
                                  disabled: false,
                                },
                              }}
                              defaultSelectedRow={{
                                mode: "index",
                                indexType: "display",
                                index: 0,
                              }}
                              emptyMessage="No rows found"
                              enableSaveActions={true}
                              searchTerm="{{ filterReconSearch2.value }}"
                              showBorder={true}
                              showFooter={true}
                              showHeader={true}
                              showSummaryRow={true}
                              style={{ headerBackground: "canvas" }}
                              toolbarPosition="bottom"
                            >
                              <Column
                                id="f4f61"
                                alignment="right"
                                editable={false}
                                editableOptions={{ showStepper: true }}
                                format="decimal"
                                formatOptions={{
                                  showSeparators: true,
                                  notation: "standard",
                                }}
                                groupAggregationMode="sum"
                                key="id"
                                label="ID"
                                placeholder="Enter value"
                                position="center"
                                size={84.09375}
                                summaryAggregationMode="sum"
                              />
                              <Column
                                id="5046b"
                                alignment="left"
                                editableOptions={{ showStepper: true }}
                                format="string"
                                formatOptions={{
                                  showSeparators: true,
                                  notation: "standard",
                                }}
                                groupAggregationMode="sum"
                                key="entity"
                                label="Entity"
                                placeholder="Enter value"
                                position="center"
                                size={120.4375}
                                summaryAggregationMode="none"
                                valueOverride="{{
  Entity_get.data.find(
    acc => acc.id === item
  )?.name
}}"
                              />
                              <Column
                                id="c831b"
                                alignment="left"
                                editableOptions={{ showStepper: true }}
                                format="string"
                                formatOptions={{
                                  showSeparators: true,
                                  notation: "standard",
                                }}
                                groupAggregationMode="sum"
                                key="bank_account"
                                label="Bank account"
                                placeholder="Enter value"
                                position="center"
                                size={123.15625}
                                summaryAggregationMode="none"
                                valueOverride="{{
  BankAccount_get.data.find(
    acc => acc.id === item
  )?.name
}}"
                              />
                              <Column
                                id="ed9f5"
                                alignment="left"
                                format="date"
                                groupAggregationMode="none"
                                key="date"
                                label="Date"
                                placeholder="Enter value"
                                position="center"
                                size={90.75}
                                summaryAggregationMode="none"
                              />
                              <Column
                                id="2478a"
                                alignment="right"
                                editableOptions={{ showStepper: true }}
                                format="decimal"
                                formatOptions={{
                                  showSeparators: true,
                                  notation: "standard",
                                }}
                                groupAggregationMode="sum"
                                key="amount"
                                label="Amount"
                                placeholder="Enter value"
                                position="center"
                                size={112.484375}
                                summaryAggregationMode="sum"
                              />
                              <Column
                                id="a9670"
                                alignment="left"
                                cellTooltipMode="overflow"
                                format="string"
                                groupAggregationMode="none"
                                key="description"
                                label="Description"
                                placeholder="Enter value"
                                position="center"
                                size={413}
                                summaryAggregationMode="none"
                              />
                              <Column
                                id="9e089"
                                alignment="left"
                                format="string"
                                groupAggregationMode="none"
                                key="status"
                                label="Status"
                                placeholder="Enter value"
                                position="center"
                                size={94.375}
                                summaryAggregationMode="none"
                              />
                              <Action
                                id="06f73"
                                icon="bold/travel-map-location-target-1"
                                label="Sugerir"
                              >
                                <Event
                                  event="clickAction"
                                  method="run"
                                  params={{
                                    map: {
                                      src: "// Retool JS script\n\nconst payload = {\n  bank_transaction_ids: [currentSourceRow.id],\n  max_suggestions_per_bank: 5,\n  min_confidence: 0.3,\n  min_match_count: 1,\n};\n\nBankSuggestions_get.trigger({\n  additionalScope: { payload }, // inside the query use {{ payload }}\n});\n\nmodalFrame16.show();",
                                    },
                                  }}
                                  pluginId=""
                                  type="script"
                                  waitMs="0"
                                  waitType="debounce"
                                />
                              </Action>
                              <ToolbarButton
                                id="1a"
                                icon="bold/interface-text-formatting-filter-2"
                                label="Filter"
                                type="filter"
                              />
                              <ToolbarButton
                                id="3c"
                                icon="bold/interface-download-button-2"
                                label="Download"
                                type="custom"
                              >
                                <Event
                                  event="clickToolbar"
                                  method="exportData"
                                  pluginId="tableBank"
                                  type="widget"
                                  waitMs="0"
                                  waitType="debounce"
                                />
                              </ToolbarButton>
                              <ToolbarButton
                                id="4d"
                                icon="bold/interface-arrows-round-left"
                                label="Refresh"
                                type="custom"
                              >
                                <Event
                                  event="clickToolbar"
                                  method="refresh"
                                  pluginId="tableBank"
                                  type="widget"
                                  waitMs="0"
                                  waitType="debounce"
                                />
                              </ToolbarButton>
                              <Event
                                event="selectRow"
                                method="run"
                                params={{
                                  ordered: [
                                    {
                                      src: '//tableBook.clearSelection();\n//Transactions_get3.trigger();\n\n(() => {\n  const bankRows = tableBank.selectedRow.data;\n  const bookRows = tableBook.selectedRow.data;\n\n  if (!bankRows || !bookRows) {\n    return { error: "Please select records in both tables." };\n  }\n\n  const toArray = val => Array.isArray(val) ? val : [val];\n\n  const bankCombo = toArray(bankRows);\n  const bookCombo = toArray(bookRows);\n\n  const bank_transaction_details = bankCombo.map(tx => ({\n    id: tx.id,\n    date: tx.date,\n    amount: tx.amount,\n    description: tx.memo,\n    bank_account: tx.bank_account\n      ? {\n          id: tx.bank_account.id,\n          name: tx.bank_account.name,\n        }\n      : null,\n    entity: tx.entity ? tx.entity.id : null,\n    currency: tx.currency?.id || null,\n  }));\n\n  const journal_entry_details = bookCombo.map(entry => ({\n    id: entry.id,\n    date: entry.transaction?.date,\n    amount: entry.amount,\n    description: entry.transaction?.description,\n    account: entry.account\n      ? {\n          id: entry.account.id,\n          account_code: entry.account.account_code,\n          name: entry.account.name,\n        }\n      : null,\n    entity: entry.entity\n      ? {\n          id: entry.entity.id,\n          name: entry.entity.name,\n        }\n      : null,\n    transaction: entry.transaction\n      ? {\n          id: entry.transaction.id,\n          description: entry.transaction.description,\n          date: entry.transaction.date,\n        }\n      : null,\n  }));\n\n  const sum = arr => arr.reduce((acc, val) => acc + Number(val.amount || 0), 0);\n  const sum_bank = sum(bankCombo);\n  const sum_book = sum(bookCombo);\n  const difference = sum_bank - sum_book;\n\n  const avgDateDiff = (() => {\n    const diffs = [];\n    bankCombo.forEach(tx => {\n      bookCombo.forEach(entry => {\n        const date1 = new Date(tx.date);\n        const date2 = new Date(entry.transaction?.date);\n        if (!isNaN(date1) && !isNaN(date2)) {\n          const diff = Math.abs((date1 - date2) / (1000 * 3600 * 24));\n          diffs.push(diff);\n        }\n      });\n    });\n    if (diffs.length === 0) return 0;\n    return diffs.reduce((a, b) => a + b, 0) / diffs.length;\n  })();\n\n  const bank_summary = bankCombo\n    .map(tx => `ID: ${tx.id}, Date: ${tx.date}, Amount: ${tx.amount}, Desc: ${tx.description}`)\n    .join("\\n");\n\n  const journal_summary = bookCombo\n    .map(entry => {\n      const acct = entry.account || {};\n      const direction = entry.debit_amount ? "DEBIT" : "CREDIT";\n      const amount = Number(entry.debit_amount || entry.credit_amount || 0);\n      return `ID: ${entry.transaction?.id}, Date: ${entry.transaction?.date}, JE: ${direction} ${amount} - (${acct.account_code}) ${acct.name}, Desc: ${entry.transaction?.description}`;\n    })\n    .join("\\n");\n\n  return {\n    match_type: "manual",\n    bank_transaction_details,\n    journal_entry_details,\n    bank_transaction_summary: bank_summary,\n    journal_entries_summary: journal_summary,\n    bank_ids: bankCombo.map(tx => tx.id),\n    journal_entries_ids: bookCombo.map(entry => entry.id),\n    sum_bank,\n    sum_book,\n    difference,\n    avg_date_diff: avgDateDiff,\n    confidence_score: 0.95 // arbitrary, since user selects manually\n  };\n})();\n',
                                    },
                                  ],
                                }}
                                pluginId=""
                                type="script"
                                waitMs="0"
                                waitType="debounce"
                              />
                              <Event
                                event="changeFilter"
                                method="trigger"
                                params={{}}
                                pluginId="VisibleBankIds"
                                type="datasource"
                                waitMs="0"
                                waitType="debounce"
                              />
                            </Table>
                          </View>
                        </Container>
                      </View>
                    </Container>
                    <Container
                      id="group99"
                      _direction="vertical"
                      _gap="0px"
                      _type="stack"
                      footerPadding="4px 12px"
                      headerPadding="4px 12px"
                      margin="0"
                      padding="0"
                      showBody={true}
                      showBorder={false}
                      style={{ map: { background: "rgba(255, 255, 255, 0)" } }}
                    >
                      <View id="00030" viewKey="View 1">
                        <Form
                          id="form22"
                          footerPadding="4px 12px"
                          headerPadding="4px 12px"
                          padding="12px"
                          requireValidation={true}
                          resetAfterSubmit={true}
                          showBody={true}
                        >
                          <Header>
                            <Text
                              id="formTitle37"
                              value="#### Form title"
                              verticalAlign="center"
                            />
                          </Header>
                          <Body>
                            <Include src="./group86.rsx" />
                          </Body>
                          <Footer>
                            <Button
                              id="formButton25"
                              submit={true}
                              submitTargetId="form22"
                              text="Submit"
                            />
                          </Footer>
                        </Form>
                        <Container
                          id="container30"
                          enableFullBleed={true}
                          footerPadding="4px 12px"
                          headerPadding="4px 12px"
                          heightType="fixed"
                          overflowType="hidden"
                          padding="12px"
                          showBody={true}
                          showHeader={true}
                        >
                          <Header>
                            <Text
                              id="containerTitle31"
                              value="#### Transações Book"
                              verticalAlign="center"
                            />
                          </Header>
                          <View id="00030" viewKey="View 1">
                            <Table
                              id="tableBook"
                              actionsOverflowPosition={1}
                              cellSelection="none"
                              clearChangesetOnSave={true}
                              data="{{ BookTransactions_get.data }}"
                              defaultFilters={{
                                0: {
                                  id: "8c18e",
                                  columnId: "87af3",
                                  operator: ">=",
                                  value:
                                    "{{ filterReconDateRange3.value.start }}",
                                  disabled: false,
                                },
                                1: {
                                  id: "6c5ec",
                                  columnId: "87af3",
                                  operator: "<=",
                                  value:
                                    "{{ filterReconDateRange3.value.end }}",
                                  disabled: false,
                                },
                                2: {
                                  id: "89287",
                                  columnId: "2a88d",
                                  operator: ">=",
                                  value: "{{ filterBookMinAmount.value }}",
                                  disabled: false,
                                },
                                3: {
                                  id: "a0408",
                                  columnId: "2a88d",
                                  operator: "<=",
                                  value: "{{ filterBookMaxAmount.value }}",
                                  disabled: false,
                                },
                              }}
                              defaultSelectedRow={{
                                mode: "index",
                                indexType: "display",
                                index: 0,
                              }}
                              emptyMessage="No rows found"
                              enableSaveActions={true}
                              headerTextWrap={true}
                              rowHeight="small"
                              searchTerm="{{ filterReconSearch3.value }}"
                              showBorder={true}
                              showFooter={true}
                              showHeader={true}
                              showSummaryRow={true}
                              style={{ headerBackground: "canvas" }}
                              toolbarPosition="bottom"
                            >
                              <Column
                                id="f4f61"
                                alignment="right"
                                editableOptions={{ showStepper: true }}
                                format="decimal"
                                formatOptions={{
                                  showSeparators: true,
                                  notation: "standard",
                                }}
                                groupAggregationMode="sum"
                                key="id"
                                label="ID"
                                placeholder="Enter value"
                                position="center"
                                size={75.375}
                                summaryAggregationMode="sum"
                              />
                              <Column
                                id="9fd97"
                                alignment="right"
                                editableOptions={{ showStepper: true }}
                                format="decimal"
                                formatOptions={{
                                  showSeparators: true,
                                  notation: "standard",
                                }}
                                groupAggregationMode="sum"
                                key="bank_account"
                                label="Bank account"
                                placeholder="Enter value"
                                position="center"
                                size={100}
                                summaryAggregationMode="sum"
                              />
                              <Column
                                id="87af3"
                                alignment="left"
                                format="date"
                                groupAggregationMode="none"
                                key="bank_date"
                                label="Bank date"
                                placeholder="Enter value"
                                position="center"
                                size={100}
                                summaryAggregationMode="none"
                              />
                              <Column
                                id="2a88d"
                                alignment="right"
                                editableOptions={{ showStepper: true }}
                                format="decimal"
                                formatOptions={{
                                  showSeparators: true,
                                  notation: "standard",
                                }}
                                groupAggregationMode="sum"
                                key="balance"
                                label="Amount"
                                placeholder="Enter value"
                                position="center"
                                size={116}
                                summaryAggregationMode="sum"
                              />
                              <Column
                                id="9f76a"
                                alignment="left"
                                format="date"
                                groupAggregationMode="none"
                                key="transaction_date"
                                label="Transaction date"
                                placeholder="Enter value"
                                position="center"
                                size={100}
                                summaryAggregationMode="none"
                              />
                              <Column
                                id="bb262"
                                alignment="left"
                                cellTooltipMode="overflow"
                                format="string"
                                groupAggregationMode="none"
                                key="description"
                                label="Description"
                                placeholder="Enter value"
                                position="center"
                                size={287.1875}
                                summaryAggregationMode="none"
                              />
                              <Column
                                id="0fc39"
                                alignment="left"
                                cellTooltipMode="overflow"
                                format="string"
                                groupAggregationMode="none"
                                key="transaction_description"
                                label="Transaction description"
                                placeholder="Enter value"
                                position="center"
                                size={343}
                                summaryAggregationMode="none"
                              />
                              <Action
                                id="0247d"
                                icon="bold/interface-edit-pencil"
                                label="Action 1"
                              />
                              <ToolbarButton
                                id="1a"
                                icon="bold/interface-text-formatting-filter-2"
                                label="Filter"
                                type="filter"
                              />
                              <ToolbarButton
                                id="3c"
                                icon="bold/interface-download-button-2"
                                label="Download"
                                type="custom"
                              >
                                <Event
                                  event="clickToolbar"
                                  method="exportData"
                                  pluginId="tableBook"
                                  type="widget"
                                  waitMs="0"
                                  waitType="debounce"
                                />
                              </ToolbarButton>
                              <ToolbarButton
                                id="4d"
                                icon="bold/interface-arrows-round-left"
                                label="Refresh"
                                type="custom"
                              >
                                <Event
                                  event="clickToolbar"
                                  method="refresh"
                                  pluginId="tableBook"
                                  type="widget"
                                  waitMs="0"
                                  waitType="debounce"
                                />
                              </ToolbarButton>
                              <Event
                                event="selectRow"
                                method="run"
                                params={{
                                  ordered: [
                                    {
                                      src: "//tableBank.clearSelection();\n//Transactions_get3.trigger();",
                                    },
                                  ],
                                }}
                                pluginId=""
                                type="script"
                                waitMs="0"
                                waitType="debounce"
                              />
                              <Event
                                event="changeFilter"
                                method="trigger"
                                params={{}}
                                pluginId="VisibleBookIds"
                                type="datasource"
                                waitMs="0"
                                waitType="debounce"
                              />
                            </Table>
                          </View>
                        </Container>
                      </View>
                    </Container>
                  </View>
                </Container>
              </View>
            </Container>
            <Container
              id="container32"
              footerPadding="4px 12px"
              headerPadding="4px 12px"
              padding="12px"
              showBody={true}
              showBorder={false}
              showHeader={true}
              style={{ background: "canvas", headerBackground: "canvas" }}
            >
              <Header>
                <Text
                  id="containerTitle33"
                  value="#### Sugestões"
                  verticalAlign="center"
                />
              </Header>
              <View id="00030" viewKey="View 1">
                <Form
                  id="form20"
                  footerPadding="4px 12px"
                  headerPadding="4px 12px"
                  padding="12px"
                  requireValidation={true}
                  resetAfterSubmit={true}
                  showBody={true}
                >
                  <Header>
                    <Text
                      id="formTitle35"
                      value="#### Form title"
                      verticalAlign="center"
                    />
                  </Header>
                  <Body>
                    <Container
                      id="group80"
                      _align="end"
                      _flexWrap={true}
                      _gap="0px"
                      _justify="space-between"
                      _type="stack"
                      footerPadding="4px 12px"
                      headerPadding="4px 12px"
                      margin="0"
                      padding="0"
                      showBody={true}
                      showBorder={false}
                      style={{ map: { background: "rgba(255, 255, 255, 0)" } }}
                    >
                      <View id="00030" viewKey="View 1">
                        <Include src="./group87.rsx" />
                        <Container
                          id="group81"
                          _gap="0px"
                          _justify="end"
                          _type="stack"
                          footerPadding="4px 12px"
                          headerPadding="4px 12px"
                          margin="0"
                          padding="0"
                          showBody={true}
                          showBorder={false}
                          style={{
                            map: { background: "rgba(255, 255, 255, 0)" },
                          }}
                        >
                          <View id="00030" viewKey="View 1">
                            <Button
                              id="button43"
                              iconBefore="bold/interface-favorite-star"
                              text="Atalhos"
                            >
                              <Event
                                event="click"
                                method="run"
                                params={{
                                  map: {
                                    src: "ReconCounts_compute.trigger();\nmodalReconShortcuts.show();",
                                  },
                                }}
                                pluginId=""
                                type="script"
                                waitMs="0"
                                waitType="debounce"
                              />
                            </Button>
                            <Button
                              id="btnQueueOpen"
                              iconBefore="bold/interface-page-controller-loading-3"
                              styleVariant="outline"
                              text="Execução"
                            >
                              <Event
                                event="click"
                                method="show"
                                params={{}}
                                pluginId="modalReconCeleryQueue"
                                type="widget"
                                waitMs="0"
                                waitType="debounce"
                              />
                            </Button>
                            <ButtonGroup2
                              id="buttonGroup2"
                              alignment="left"
                              overflowPosition={5}
                            >
                              <ButtonGroup2-Button
                                id="aac52"
                                hidden="true"
                                styleVariant="outline"
                                text="1-to-1"
                              >
                                <Event
                                  event="click"
                                  method="run"
                                  params={{
                                    map: {
                                      src: '// Step 1: Get displayed rows from tableBook\nconst visibleBooks = await tableBook.getDisplayedData();\nconst bookRows = Array.isArray(visibleBooks) ? visibleBooks : Object.values(visibleBooks);\nconst bookIds = bookRows.map(row => row.id);\n\n// Step 2: Get displayed rows from tableBank\nconst visibleBanks = await tableBank.getDisplayedData();\nconst bankRows = Array.isArray(visibleBanks) ? visibleBanks : Object.values(visibleBanks);\nconst bankIds = bankRows.map(row => row.id);\n\n// Step 3: Build the payload object\nconst payload = {\n  bank_ids: bankIds,\n  book_ids: bookIds,\n  //enforce_same_bank: switchSameBank.value,\n  //enforce_same_entity: switchSameEntity.value,\n  //max_bank_entries: BankToCombine.value,\n  //max_book_entries: BookToCombine.value,\n  //amount_tolerance: AmountTolerance.value,\n  max_group_size: 2,\n  amount_tolerance: 0,\n  date_tolerance_days: DateTolerance.value,\n  min_confidence: MinConfidence.value,\n  //max_suggestions: MaxSuggestions.value,\n  weight_date: 0.4,\n  weight_amount: 0.6,\n  strategy: "optimized"\n};\n\nconsole.log("Generated payload:", payload);\n\n// Step 4: Trigger the Transactions_get3 query with the payload\nReconciliation_execute.trigger({\n  additionalScope: {\n    payload: payload\n  }\n});\n\nQueueCount_get.trigger();\n',
                                    },
                                  }}
                                  pluginId=""
                                  type="script"
                                  waitMs="0"
                                  waitType="debounce"
                                />
                              </ButtonGroup2-Button>
                              <ButtonGroup2-Button
                                id="09b47"
                                hidden="true"
                                styleVariant="solid"
                                text="Propor Conciliação"
                              >
                                <Event
                                  event="click"
                                  method="run"
                                  params={{
                                    map: {
                                      src: "// Trigger two queries simultaneously, then trigger the third one after completion\nPromise.all([\n  VisibleBankIds.trigger(),\n  VisibleBookIds.trigger()\n]).then(([result1, result2]) => {\n  // You can access results here if needed:\n  console.log(result1, result2);\n\n  // Trigger the third query after both complete\n  Transactions_get3.trigger();\n}).catch(error => {\n  // Handle errors if either query fails\n  console.error('One of the queries failed:', error);\n});",
                                    },
                                  }}
                                  pluginId=""
                                  type="script"
                                  waitMs="0"
                                  waitType="debounce"
                                />
                              </ButtonGroup2-Button>
                              <ButtonGroup2-Button
                                id="f030b"
                                hidden="true"
                                styleVariant="transparent"
                                text="             |"
                              />
                              <ButtonGroup2-Button
                                id="57e82"
                                styleVariant="transparent"
                                text="Conciliar Manual"
                              >
                                <Event
                                  event="click"
                                  method="show"
                                  params={{}}
                                  pluginId="modalManualConciliation"
                                  type="widget"
                                  waitMs="0"
                                  waitType="debounce"
                                />
                              </ButtonGroup2-Button>
                              <ButtonGroup2-Button
                                id="cbe72"
                                styleVariant="outline"
                                text="Todos #1 100%"
                              >
                                <Event
                                  event="click"
                                  method="run"
                                  params={{
                                    ordered: [
                                      {
                                        src: '// ✅ Retrieve and normalize raw data\nlet rawData = ReconciliationMatches.value;\nconsole.log("Raw data:", rawData);\n\n// 2. Normalize to array\nlet allMatches = [];\nif (rawData?.suggestions && Array.isArray(rawData.suggestions)) {\n  allMatches = rawData.suggestions;\n} else if (Array.isArray(rawData)) {\n  allMatches = rawData;\n} else {\n  try {\n    allMatches = JSON.parse(rawData);\n  } catch (e) {\n    console.error("Failed to parse rawData:", e);\n    allMatches = [];\n  }\n}\n\n// ✅ STEP 3: Filter 100% confidence matches\nconst filteredMatches = allMatches.filter(match => match.confidence_score === 1);\n\n// ✅ STEP 4: Count frequency of bank_ids\nconst bankIdFrequency = {};\nfilteredMatches.forEach(match => {\n  match.bank_ids.forEach(id => {\n    bankIdFrequency[id] = (bankIdFrequency[id] || 0) + 1;\n  });\n});\n\n// ✅ STEP 5: Keep only unique bank_ids matches\nconst uniqueMatches = filteredMatches.filter(match =>\n  match.bank_ids.every(id => bankIdFrequency[id] === 1)\n);\n\nconsole.log("Unique Matches:", uniqueMatches);\n\n// ✅ STEP 6: Build payload\nconst transformedItem = {\n  matches: uniqueMatches.map(match => ({\n    bank_transaction_ids: match.bank_ids,\n    journal_entry_ids: match.journal_entries_ids,\n  })),\n  adjustment_side: "bank",\n  reference: "Reconciliation batch 1",\n  notes: "Matched using high confidence scores",\n};\n\nconsole.log("Transformed Payload:", transformedItem);\n\n// ✅ STEP 7: Trigger POST + Handle response\nif (transformedItem.matches.length > 0) {\n  MatchRecords_post.trigger({\n    additionalScope: {\n      content: transformedItem,\n    },\n    onSuccess: () => {\n      // Remove matched items from ReconciliationMatches\n      const matchedIds = new Set(uniqueMatches.map(m => m.id));\n      ReconciliationMatches.setValue(\n        ReconciliationMatches.value.filter(item => !matchedIds.has(item.id))\n      );\n\n      console.log(`✅ ${uniqueMatches.length} matches applied and removed.`);\n    },\n    onFailure: (error) => {\n      console.error("❌ Failed to apply matches:", error);\n    }\n  });\n} else {\n  console.log("⚠️ No unique matches to apply.");\n}',
                                      },
                                    ],
                                  }}
                                  pluginId=""
                                  type="script"
                                  waitMs="0"
                                  waitType="debounce"
                                />
                              </ButtonGroup2-Button>
                            </ButtonGroup2>
                          </View>
                        </Container>
                      </View>
                    </Container>
                  </Body>
                  <Footer>
                    <Button
                      id="formButton23"
                      submit={true}
                      submitTargetId="form20"
                      text="Submit"
                    />
                  </Footer>
                </Form>
                <Container
                  id="container31"
                  enableFullBleed={true}
                  footerPadding="4px 12px"
                  headerPadding="4px 12px"
                  heightType="fixed"
                  overflowType="hidden"
                  padding="12px"
                  showBody={true}
                  showHeader={true}
                >
                  <Header>
                    <Text
                      id="containerTitle32"
                      value="#### Sugestões"
                      verticalAlign="center"
                    />
                  </Header>
                  <View id="00030" viewKey="View 1">
                    <Table
                      id="table29"
                      actionsOverflowPosition={1}
                      cellSelection="none"
                      clearChangesetOnSave={true}
                      data="{{ Reconciliation_get.data?.suggestions }}"
                      defaultFilters={{
                        0: {
                          id: "78d0c",
                          columnId: "7b95a",
                          operator: ">=",
                          value: "{{ filterReconGlobalScore.value }}",
                          disabled: false,
                        },
                        1: {
                          id: "c4177",
                          columnId: "5ecd5",
                          operator: ">=",
                          value: "{{ filterReconAmountScore.value }}",
                          disabled: false,
                        },
                        2: {
                          id: "b4242",
                          columnId: "e6e58",
                          operator: ">=",
                          value: "{{ filterReconDateScore.value }}",
                          disabled: false,
                        },
                        3: {
                          id: "7447b",
                          columnId: "7b729",
                          operator: ">=",
                          value: "{{ filterReconDescrScore.value }}",
                          disabled: false,
                        },
                        4: {
                          id: "6e27e",
                          columnId: "5978f",
                          operator: ">=",
                          value: "{{ filterReconDateRange.value.start }}",
                          disabled: false,
                        },
                        5: {
                          id: "4fb19",
                          columnId: "19cb4",
                          operator: "<=",
                          value: "{{ filterReconDateRange.value.end }}",
                          disabled: false,
                        },
                      }}
                      defaultSelectedRow={{
                        mode: "index",
                        indexType: "display",
                        index: 0,
                      }}
                      dynamicRowHeights={true}
                      emptyMessage="No rows found"
                      enableSaveActions={true}
                      rowHeight="small"
                      rowSelection="multiple"
                      searchTerm="{{ filterReconSearch.value }}"
                      showBorder={true}
                      showColumnBorders={true}
                      showFooter={true}
                      showHeader={true}
                      style={{ headerBackground: "canvas" }}
                      toolbarPosition="bottom"
                    >
                      <Column
                        id="7b95a"
                        alignment="right"
                        editableOptions={{ showStepper: true }}
                        format="percent"
                        formatOptions={{
                          showSeparators: true,
                          notation: "standard",
                        }}
                        groupAggregationMode="average"
                        key="confidence_score"
                        label="Score"
                        placeholder="Enter value"
                        position="left"
                        size={58.1875}
                        summaryAggregationMode="none"
                      />
                      <Column
                        id="5ecd5"
                        alignment="right"
                        editableOptions={{ showStepper: true }}
                        format="percent"
                        formatOptions={{
                          showSeparators: true,
                          notation: "standard",
                        }}
                        groupAggregationMode="average"
                        key="component_scores"
                        label="Amount Score"
                        placeholder="Enter value"
                        position="center"
                        referenceId="amount_score"
                        size={96.203125}
                        summaryAggregationMode="none"
                        valueOverride="{{ item.amount_score }}"
                      />
                      <Column
                        id="e6e58"
                        alignment="right"
                        editableOptions={{ showStepper: true }}
                        format="percent"
                        formatOptions={{
                          showSeparators: true,
                          notation: "standard",
                        }}
                        groupAggregationMode="average"
                        key="component_scores"
                        label="Date Score"
                        placeholder="Enter value"
                        position="center"
                        referenceId="date_score"
                        size={78.8125}
                        summaryAggregationMode="none"
                        valueOverride="{{ item.date_score }}"
                      />
                      <Column
                        id="7b729"
                        alignment="right"
                        editableOptions={{ showStepper: true }}
                        format="percent"
                        formatOptions={{
                          showSeparators: true,
                          notation: "standard",
                        }}
                        groupAggregationMode="average"
                        key="component_scores"
                        label="Desc Score"
                        placeholder="Enter value"
                        position="center"
                        referenceId="description_score"
                        size={80.71875}
                        summaryAggregationMode="none"
                        valueOverride="{{ item.description_score }}"
                      />
                      <Column
                        id="a9a83"
                        alignment="left"
                        format="string"
                        groupAggregationMode="none"
                        key="match_type"
                        label="Match type"
                        placeholder="Enter value"
                        position="center"
                        size={99.21875}
                        summaryAggregationMode="none"
                      />
                      <Column
                        id="29a3d"
                        alignment="left"
                        cellTooltipMode="overflow"
                        format="tags"
                        formatOptions={{ automaticColors: true }}
                        groupAggregationMode="none"
                        key="bank_ids"
                        label="Bank ids"
                        placeholder="Select options"
                        position="center"
                        size={165.75}
                        summaryAggregationMode="none"
                      />
                      <Column
                        id="c7afa"
                        alignment="left"
                        cellTooltipMode="overflow"
                        format="tags"
                        formatOptions={{ automaticColors: true }}
                        groupAggregationMode="none"
                        key="journal_entries_ids"
                        label="Journal entries ids"
                        placeholder="Select options"
                        position="center"
                        size={171.828125}
                        summaryAggregationMode="none"
                      />
                      <Column
                        id="73b03"
                        alignment="left"
                        editableOptions={{ spellCheck: false }}
                        format="markdown"
                        groupAggregationMode="none"
                        label="Bank Lines"
                        placeholder="Enter value"
                        position="center"
                        referenceId="bank_lines_md"
                        size={403}
                        summaryAggregationMode="none"
                        valueOverride={
                          '{{\n(() => {\n  const bank = currentSourceRow.bank_lines || "";\n  const book = currentSourceRow.book_lines || "";\n\n  const escapeRegex = (s) =>\n    s.replace(/[.*+?^${}()|[\\]\\\\]/g, "\\\\$&");\n\n  const tokenize = (str) => {\n    if (!str) return [];\n    const lower = str.toLowerCase();\n\n    const wordTokens = lower\n      .split(/[^a-z0-9áéíóúâêîôûãõç]+/i)\n      .filter(w => w && /[a-záéíóúâêîôûãõç]/i.test(w));\n\n    const dateTokens = lower.match(/\\d{4}-\\d{2}-\\d{2}/g) || [];\n\n    const amountTokens =\n      lower.match(/-?\\d{1,3}(?:[.,]\\d{3})*(?:[.,]\\d{2})/g) || [];\n\n    return Array.from(new Set([...wordTokens, ...dateTokens, ...amountTokens]));\n  };\n\n  const tokensBank = tokenize(bank);\n  const tokensBook = tokenize(book);\n\n  const commons = Array.from(\n    new Set(tokensBank.filter(t => tokensBook.includes(t) && t.length > 2))\n  ).sort((a, b) => b.length - a.length);\n\n  const highlight = (text) => {\n    let out = text || "";\n    commons.forEach((t) => {\n      const re = new RegExp(escapeRegex(t), "gi");\n      out = out.replace(re, (match) => `**${match}**`);\n    });\n    return out;\n  };\n\n  return highlight(bank);\n})()\n}}\n'
                        }
                      />
                      <Column
                        id="797d6"
                        alignment="left"
                        editableOptions={{ spellCheck: false }}
                        format="markdown"
                        groupAggregationMode="none"
                        label="Book Lines"
                        placeholder="Enter value"
                        position="center"
                        referenceId="book_lines_md"
                        size={593}
                        summaryAggregationMode="none"
                        valueOverride={
                          '{{\n(() => {\n  const bank = currentSourceRow.bank_lines || "";\n  const book = currentSourceRow.book_lines || "";\n\n  const escapeRegex = (s) =>\n    s.replace(/[.*+?^${}()|[\\]\\\\]/g, "\\\\$&");\n\n  const tokenize = (str) => {\n    if (!str) return [];\n    const lower = str.toLowerCase();\n\n    // palavras com pelo menos 1 letra\n    const wordTokens = lower\n      .split(/[^a-z0-9áéíóúâêîôûãõç]+/i)\n      .filter(w => w && /[a-záéíóúâêîôûãõç]/i.test(w));\n\n    // datas tipo 2025-06-30\n    const dateTokens = lower.match(/\\d{4}-\\d{2}-\\d{2}/g) || [];\n\n    // valores tipo -883.60, 4.384,18 etc\n    const amountTokens =\n      lower.match(/-?\\d{1,3}(?:[.,]\\d{3})*(?:[.,]\\d{2})/g) || [];\n\n    return Array.from(new Set([...wordTokens, ...dateTokens, ...amountTokens]));\n  };\n\n  const tokensBank = tokenize(bank);\n  const tokensBook = tokenize(book);\n\n  // tokens em comum, maiores primeiro\n  const commons = Array.from(\n    new Set(tokensBank.filter(t => tokensBook.includes(t) && t.length > 2))\n  ).sort((a, b) => b.length - a.length);\n\n  const highlight = (text) => {\n    let out = text || "";\n    commons.forEach((t) => {\n      const re = new RegExp(escapeRegex(t), "gi");\n      out = out.replace(re, (match) => `**${match}**`);\n    });\n    return out;\n  };\n\n  return highlight(book);\n})()\n}}\n'
                        }
                      />
                      <Column
                        id="a8275"
                        alignment="left"
                        cellTooltipMode="overflow"
                        format="string"
                        groupAggregationMode="none"
                        hidden="true"
                        key="bank_lines"
                        label="Bank lines"
                        placeholder="Enter value"
                        position="center"
                        size={390.140625}
                        summaryAggregationMode="none"
                      />
                      <Column
                        id="f628c"
                        alignment="left"
                        cellTooltipMode="overflow"
                        format="multilineString"
                        groupAggregationMode="none"
                        hidden="true"
                        key="book_lines"
                        label="Book lines"
                        placeholder="Enter value"
                        position="center"
                        size={974.875}
                        summaryAggregationMode="none"
                      />
                      <Column
                        id="ffda6"
                        alignment="left"
                        cellTooltipMode="overflow"
                        format="json"
                        groupAggregationMode="none"
                        key="bank_stats"
                        label="Bank stats"
                        placeholder="Enter value"
                        position="center"
                        size={375}
                        summaryAggregationMode="none"
                      />
                      <Column
                        id="dc06a"
                        alignment="left"
                        cellTooltipMode="overflow"
                        format="json"
                        groupAggregationMode="none"
                        key="book_stats"
                        label="Book stats"
                        placeholder="Enter value"
                        position="center"
                        size={369}
                        summaryAggregationMode="none"
                      />
                      <Column
                        id="e3bae"
                        alignment="right"
                        editableOptions={{ showStepper: true }}
                        format="decimal"
                        formatOptions={{
                          showSeparators: true,
                          notation: "standard",
                        }}
                        groupAggregationMode="sum"
                        key="abs_amount_diff"
                        label="Abs amount diff"
                        placeholder="Enter value"
                        position="center"
                        size={106.265625}
                        summaryAggregationMode="none"
                      />
                      <Column
                        id="acb93"
                        alignment="left"
                        cellTooltipMode="overflow"
                        format="json"
                        groupAggregationMode="none"
                        hidden="true"
                        key="component_scores"
                        label="Component scores"
                        placeholder="Enter value"
                        position="center"
                        size={937.59375}
                        summaryAggregationMode="none"
                      />
                      <Column
                        id="a2542"
                        alignment="left"
                        cellTooltipMode="overflow"
                        format="json"
                        groupAggregationMode="none"
                        key="confidence_weights"
                        label="Confidence weights"
                        placeholder="Enter value"
                        position="center"
                        size={290.40625}
                        summaryAggregationMode="none"
                      />
                      <Column
                        id="0cd90"
                        alignment="left"
                        cellTooltipMode="overflow"
                        format="json"
                        groupAggregationMode="none"
                        key="match_parameters"
                        label="Match parameters"
                        placeholder="Enter value"
                        position="center"
                        size={431.59375}
                        summaryAggregationMode="none"
                      />
                      <Column
                        id="06159"
                        alignment="left"
                        cellTooltipMode="overflow"
                        format="json"
                        groupAggregationMode="none"
                        key="extra"
                        label="Extra"
                        placeholder="Enter value"
                        position="center"
                        size={513.8125}
                        summaryAggregationMode="none"
                      />
                      <Column
                        id="5978f"
                        alignment="left"
                        format="string"
                        groupAggregationMode="none"
                        label="Min Date"
                        placeholder="Enter value"
                        position="center"
                        referenceId="minDate"
                        size={100}
                        summaryAggregationMode="none"
                        valueOverride="{{ Math.min(moment(currentSourceRow.bank_stats.min_date),moment(currentSourceRow.book_stats.min_date)) }}"
                      />
                      <Column
                        id="19cb4"
                        alignment="left"
                        format="string"
                        groupAggregationMode="none"
                        label="Max Date"
                        placeholder="Enter value"
                        position="center"
                        referenceId="maxDate"
                        size={100}
                        summaryAggregationMode="none"
                        valueOverride="{{ Math.max(moment(currentSourceRow.bank_stats.min_date),moment(currentSourceRow.book_stats.min_date)) }}"
                      />
                      <Action
                        id="5a131"
                        icon="bold/interface-lock"
                        label="Match"
                      >
                        <Event
                          event="clickAction"
                          method="run"
                          params={{
                            ordered: [
                              {
                                src: 'const selectedRows = table29.selectedSourceRows?.length > 0 \n  ? table29.selectedSourceRows \n  : [currentSourceRow]; // fallback\n\n// Build the matches array\nconst transformedItem = {\n  matches: selectedRows.map(row => ({\n    bank_transaction_ids: row.bank_ids,\n    journal_entry_ids: row.journal_entries_ids\n  })),\n  adjustment_side: "bank",\n  reference: "Reconciliation batch 1",\n  notes: "Matched using high confidence scores"\n};\n\n// Flatten all selected bank and book IDs\nconst allSelectedBankIds = new Set(\n  selectedRows.flatMap(row => row.bank_ids || [])\n);\nconst allSelectedBookIds = new Set(\n  selectedRows.flatMap(row => row.journal_entries_ids || [])\n);\n\n// Trigger the API\nMatchRecords_post.trigger({\n  additionalScope: { content: transformedItem },\n  onSuccess: (res) => {\n  console.groupCollapsed(\'[MatchRecords_post] Success\');\n  console.log(\'Response:\', res);\n  console.groupEnd();\n\n  const created = Array.isArray(res?.created) ? res.created : [];\n  const problems = Array.isArray(res?.problems) ? res.problems : [];\n\n  // Collect IDs that were actually consumed by successful reconciliations\n  const usedBankIds = new Set();\n  const usedBookIds = new Set();\n  for (const r of created) {\n    (r.bank_ids_used || []).forEach(id => usedBankIds.add(Number(id)));\n    (r.journal_ids_used || []).forEach(id => usedBookIds.add(Number(id)));\n  }\n\n  // Collect IDs that we should drop because they are already reconciled\n  const already = problems.filter(p => p?.reason === \'already_reconciled\');\n  const alreadyBankIds = new Set();\n  const alreadyBookIds = new Set();\n  for (const p of already) {\n    (p.bank_ids || []).forEach(id => alreadyBankIds.add(Number(id)));\n    // backend may return journal_ids or journal_entry_ids depending on call path\n    (p.journal_ids || p.journal_entry_ids || []).forEach(id => alreadyBookIds.add(Number(id)));\n  }\n\n  // Union of IDs to remove\n  const removeBankIds = new Set([...usedBankIds, ...alreadyBankIds]);\n  const removeBookIds = new Set([...usedBookIds, ...alreadyBookIds]);\n\n  const before = ReconciliationMatches.value || [];\n  const updated = before.filter(item => {\n    const bankIds = item.bank_ids || [];\n    const bookIds = item.journal_entries_ids || item.journal_entry_ids || [];\n    const bankOverlap = bankIds.some(id => removeBankIds.has(Number(id)));\n    const bookOverlap = bookIds.some(id => removeBookIds.has(Number(id)));\n    return !(bankOverlap || bookOverlap);\n  });\n\n  console.log(\'[Reconciliation] Filtered matches:\', updated);\n\n  ReconciliationMatches.setValue(updated);\n  table29.clearSelection();\n    BankTransactions_get.trigger();\nBookTransactions_get.trigger();\nReconciliation_get.trigger();\n  const removedCount = before.length - updated.length;\n  const createdCount = created.length;\n  const alreadyCount = already.length;\n\n  utils.showNotification({\n    title: "Matches processed",\n    description: `Created: ${createdCount} • Removed from list: ${removedCount} (already reconciled: ${alreadyCount})`,\n    intent: "success"\n  });\n}\n});',
                              },
                            ],
                          }}
                          pluginId=""
                          type="script"
                          waitMs="0"
                          waitType="debounce"
                        />
                        <Event
                          event="clickAction"
                          method="trigger"
                          params={{}}
                          pluginId="Conciliation_get"
                          type="datasource"
                          waitMs="0"
                          waitType="debounce"
                        />
                      </Action>
                      <ToolbarButton
                        id="1a"
                        icon="bold/interface-text-formatting-filter-2"
                        label="Filter"
                        type="filter"
                      />
                      <ToolbarButton
                        id="3c"
                        icon="bold/interface-download-button-2"
                        label="Download"
                        type="custom"
                      >
                        <Event
                          event="clickToolbar"
                          method="exportData"
                          pluginId="table29"
                          type="widget"
                          waitMs="0"
                          waitType="debounce"
                        />
                      </ToolbarButton>
                      <ToolbarButton
                        id="4d"
                        icon="bold/interface-arrows-round-left"
                        label="Refresh"
                        type="custom"
                      >
                        <Event
                          event="clickToolbar"
                          method="refresh"
                          pluginId="table29"
                          type="widget"
                          waitMs="0"
                          waitType="debounce"
                        />
                      </ToolbarButton>
                    </Table>
                  </View>
                </Container>
              </View>
            </Container>
          </View>
        </Container>
      </View>
      <View id="00031" viewKey="Transações Conciliadas">
        <Container
          id="group90"
          footerPadding="4px 12px"
          headerPadding="4px 12px"
          margin="0"
          padding="0"
          showBody={true}
          showBorder={false}
          style={{ map: { background: "rgba(255, 255, 255, 0)" } }}
        >
          <View id="00030" viewKey="View 1">
            <Container
              id="container36"
              footerPadding="4px 12px"
              headerPadding="4px 12px"
              padding="12px"
              showBody={true}
              showBorder={false}
              showHeader={true}
              style={{ background: "canvas", headerBackground: "canvas" }}
            >
              <Header>
                <Text
                  id="containerTitle38"
                  value="### Conciliação"
                  verticalAlign="center"
                />
              </Header>
              <View id="00030" viewKey="View 1">
                <Form
                  id="form26"
                  footerPadding="4px 12px"
                  headerPadding="4px 12px"
                  padding="12px"
                  requireValidation={true}
                  resetAfterSubmit={true}
                  showBody={true}
                >
                  <Header>
                    <Text
                      id="formTitle41"
                      value="#### Form title"
                      verticalAlign="center"
                    />
                  </Header>
                  <Body>
                    <Container
                      id="group94"
                      _align="end"
                      _flexWrap={true}
                      _gap="0px"
                      _justify="space-between"
                      _type="stack"
                      footerPadding="4px 12px"
                      headerPadding="4px 12px"
                      margin="0"
                      padding="0"
                      showBody={true}
                      showBorder={false}
                      style={{ map: { background: "rgba(255, 255, 255, 0)" } }}
                    >
                      <View id="00030" viewKey="View 1">
                        <Include src="./group96.rsx" />
                      </View>
                    </Container>
                  </Body>
                  <Footer>
                    <Button
                      id="formButton28"
                      submit={true}
                      submitTargetId="form26"
                      text="Submit"
                    />
                  </Footer>
                </Form>
                <Container
                  id="container37"
                  enableFullBleed={true}
                  footerPadding="4px 12px"
                  headerPadding="4px 12px"
                  heightType="fixed"
                  overflowType="hidden"
                  padding="12px"
                  showBody={true}
                  showHeader={true}
                >
                  <Header>
                    <Text
                      id="containerTitle37"
                      value="#### Sugestões"
                      verticalAlign="center"
                    />
                  </Header>
                  <View id="00030" viewKey="View 1">
                    <Table
                      id="table56"
                      actionsOverflowPosition={1}
                      cellSelection="none"
                      clearChangesetOnSave={true}
                      data="{{ Conciliation_get.data }}"
                      defaultFilters={{
                        0: {
                          id: "6a8af",
                          columnId: "3117c",
                          operator: ">=",
                          value: "{{ filterReconMinAmount.value }}",
                          disabled: false,
                        },
                        1: {
                          id: "6b898",
                          columnId: "3117c",
                          operator: "<=",
                          value: "{{ filterReconMaxAmount.value }}",
                          disabled: false,
                        },
                        2: {
                          id: "23e6c",
                          columnId: "60685",
                          operator: ">=",
                          value: "{{ filterReconDateRange6.value.start }}",
                          disabled: false,
                        },
                        3: {
                          id: "c7297",
                          columnId: "26e5b",
                          operator: "<=",
                          value: "{{ filterReconDateRange6.value.end }}",
                          disabled: false,
                        },
                      }}
                      defaultSelectedRow={{
                        mode: "index",
                        indexType: "display",
                        index: 0,
                      }}
                      dynamicRowHeights={true}
                      emptyMessage="No rows found"
                      enableSaveActions={true}
                      rowHeight="small"
                      rowSelection="multiple"
                      searchTerm="{{ filterReconSearch6.value }}"
                      showBorder={true}
                      showColumnBorders={true}
                      showFooter={true}
                      showHeader={true}
                      style={{ headerBackground: "canvas" }}
                      toolbarPosition="bottom"
                    >
                      <Column
                        id="5d338"
                        alignment="right"
                        editableOptions={{ showStepper: true }}
                        format="decimal"
                        formatOptions={{
                          showSeparators: true,
                          notation: "standard",
                        }}
                        groupAggregationMode="sum"
                        key="reconciliation_id"
                        label="Reconciliation ID"
                        placeholder="Enter value"
                        position="center"
                        size={100}
                        summaryAggregationMode="none"
                      />
                      <Column
                        id="d4cdc"
                        alignment="left"
                        cellTooltipMode="overflow"
                        format="tags"
                        formatOptions={{ automaticColors: true }}
                        groupAggregationMode="none"
                        key="bank_ids"
                        label="Bank ids"
                        placeholder="Select options"
                        position="center"
                        size={100}
                        summaryAggregationMode="none"
                      />
                      <Column
                        id="2a5b6"
                        alignment="left"
                        format="string"
                        groupAggregationMode="none"
                        key="bank_description"
                        label="Bank description"
                        placeholder="Enter value"
                        position="center"
                        size={328}
                        summaryAggregationMode="none"
                      />
                      <Column
                        id="05d29"
                        alignment="left"
                        cellTooltipMode="overflow"
                        format="tags"
                        formatOptions={{ automaticColors: true }}
                        groupAggregationMode="none"
                        key="book_ids"
                        label="Book ids"
                        placeholder="Select options"
                        position="center"
                        size={100}
                        summaryAggregationMode="none"
                      />
                      <Column
                        id="f2169"
                        alignment="left"
                        cellTooltipMode="overflow"
                        format="multilineString"
                        groupAggregationMode="none"
                        key="book_description"
                        label="Book description"
                        placeholder="Enter value"
                        position="center"
                        size={376}
                        summaryAggregationMode="none"
                      />
                      <Column
                        id="3117c"
                        alignment="right"
                        editableOptions={{ showStepper: true }}
                        format="decimal"
                        formatOptions={{
                          showSeparators: true,
                          notation: "standard",
                        }}
                        groupAggregationMode="sum"
                        key="bank_sum_value"
                        label="Bank sum value"
                        placeholder="Enter value"
                        position="center"
                        size={100}
                        summaryAggregationMode="none"
                      />
                      <Column
                        id="999d5"
                        alignment="right"
                        editableOptions={{ showStepper: true }}
                        format="decimal"
                        formatOptions={{
                          showSeparators: true,
                          notation: "standard",
                        }}
                        groupAggregationMode="sum"
                        key="book_sum_value"
                        label="Book sum value"
                        placeholder="Enter value"
                        position="center"
                        size={100}
                        summaryAggregationMode="none"
                      />
                      <Column
                        id="dae31"
                        alignment="left"
                        format="date"
                        groupAggregationMode="none"
                        key="bank_avg_date"
                        label="Bank avg date"
                        placeholder="Enter value"
                        position="center"
                        size={100}
                        summaryAggregationMode="none"
                      />
                      <Column
                        id="0a519"
                        alignment="left"
                        format="date"
                        groupAggregationMode="none"
                        key="book_avg_date"
                        label="Book avg date"
                        placeholder="Enter value"
                        position="center"
                        size={100}
                        summaryAggregationMode="none"
                      />
                      <Column
                        id="5f335"
                        alignment="left"
                        format="tag"
                        formatOptions={{ automaticColors: true }}
                        groupAggregationMode="none"
                        key="reference"
                        label="Reference"
                        placeholder="Select option"
                        position="center"
                        size={168}
                        summaryAggregationMode="none"
                        valueOverride="{{ _.startCase(item) }}"
                      />
                      <Column
                        id="29da8"
                        alignment="left"
                        cellTooltipMode="overflow"
                        format="multilineString"
                        groupAggregationMode="none"
                        key="notes"
                        label="Notes"
                        placeholder="Enter value"
                        position="center"
                        size={202}
                        summaryAggregationMode="none"
                      />
                      <Column
                        id="ee15a"
                        alignment="right"
                        editableOptions={{ showStepper: true }}
                        format="decimal"
                        formatOptions={{
                          showSeparators: true,
                          notation: "standard",
                        }}
                        groupAggregationMode="sum"
                        key="difference"
                        label="Difference"
                        placeholder="Enter value"
                        position="center"
                        size={100}
                        summaryAggregationMode="none"
                      />
                      <Column
                        id="da4d7"
                        alignment="left"
                        cellTooltipMode="overflow"
                        format="tags"
                        formatOptions={{ automaticColors: true }}
                        groupAggregationMode="none"
                        key="bank_amounts"
                        label="Bank amounts"
                        placeholder="Select options"
                        position="center"
                        size={93}
                        summaryAggregationMode="none"
                      />
                      <Column
                        id="4d91b"
                        alignment="left"
                        cellTooltipMode="overflow"
                        format="tags"
                        formatOptions={{ automaticColors: true }}
                        groupAggregationMode="none"
                        key="book_amounts"
                        label="Book amounts"
                        placeholder="Select options"
                        position="center"
                        size={0}
                        summaryAggregationMode="none"
                      />
                      <Column
                        id="60685"
                        alignment="left"
                        format="date"
                        groupAggregationMode="none"
                        key="min_date"
                        label="Min date"
                        placeholder="Enter value"
                        position="center"
                        size={0}
                        summaryAggregationMode="none"
                      />
                      <Column
                        id="26e5b"
                        alignment="left"
                        format="date"
                        groupAggregationMode="none"
                        key="max_date"
                        label="Max date"
                        placeholder="Enter value"
                        position="center"
                        size={0}
                        summaryAggregationMode="none"
                      />
                      <Action
                        id="5a131"
                        icon="bold/interface-delete-bin-2"
                        label="Unmatch"
                      >
                        <Event
                          event="clickAction"
                          method="run"
                          params={{
                            ordered: [
                              {
                                src: "  Conciliation_selected.setValue(currentSourceRow.reconciliation_id);\nConciliation_delete.trigger();\nBankTransactions_get.trigger();\nBookTransactions_get.trigger();\n\n",
                              },
                            ],
                          }}
                          pluginId=""
                          type="script"
                          waitMs="0"
                          waitType="debounce"
                        />
                        <Event
                          event="clickAction"
                          method="trigger"
                          params={{}}
                          pluginId="Conciliation_get"
                          type="datasource"
                          waitMs="0"
                          waitType="debounce"
                        />
                      </Action>
                      <ToolbarButton
                        id="1a"
                        icon="bold/interface-text-formatting-filter-2"
                        label="Filter"
                        type="filter"
                      />
                      <ToolbarButton
                        id="3c"
                        icon="bold/interface-download-button-2"
                        label="Download"
                        type="custom"
                      >
                        <Event
                          event="clickToolbar"
                          method="exportData"
                          pluginId="table56"
                          type="widget"
                          waitMs="0"
                          waitType="debounce"
                        />
                      </ToolbarButton>
                      <ToolbarButton
                        id="4d"
                        icon="bold/interface-arrows-round-left"
                        label="Refresh"
                        type="custom"
                      >
                        <Event
                          event="clickToolbar"
                          method="refresh"
                          pluginId="table56"
                          type="widget"
                          waitMs="0"
                          waitType="debounce"
                        />
                      </ToolbarButton>
                    </Table>
                  </View>
                </Container>
              </View>
            </Container>
          </View>
        </Container>
      </View>
    </Container>
    <JSONEditor
      id="BankReconciliationParameters"
      hidden="true"
      value={
        '{\n            "bank_ids": {{ tableBank.displayedData.map(row => row.id) }},\n            "book_filters": {},\n            "enforce_same_bank": {{  switchSameBank.value }}, \n            "enforce_same_entity": {{  switchSameEntity.value }},\n            "max_bank_entries": {{ BankToCombine.value }},\n            "max_book_entries": {{ BookToCombine.value }},\n            "amount_tolerance": {{AmountTolerance.value}},\n            "date_tolerance_days": {{ DateTolerance.value }},\n            "min_confidence": {{ MinConfidence.value }},\n            "max_suggestions": {{ MaxSuggestions.value }},\n            "weight_date": 0.4,\n            "weight_amount": 0.6\n        }'
      }
    />
    <Table
      id="tableBook3"
      actionsOverflowPosition={1}
      cellSelection="none"
      clearChangesetOnSave={true}
      data="{{ BookTransactions_get.data }}"
      defaultFilters={{
        0: {
          ordered: [
            { id: "ba54f" },
            { columnId: "0b2a2" },
            { operator: "isNot" },
            { value: "Matched" },
            { disabled: false },
          ],
        },
      }}
      defaultSelectedRow={{ mode: "index", indexType: "display", index: 0 }}
      emptyMessage="No rows found"
      enableSaveActions={true}
      headerTextWrap={true}
      hidden="true"
      linkedFilterId="filterBook"
      rowHeight="small"
      rowSelection="{{ toggleAllowRowSelection.value ? 'multiple' : 'none' }}"
      showBorder={true}
      showFooter={true}
      showHeader={true}
      style={{ headerBackground: "canvas" }}
      toolbarPosition="bottom"
    >
      <Column
        id="f4f61"
        alignment="right"
        editableOptions={{ showStepper: true }}
        format="decimal"
        formatOptions={{ showSeparators: true, notation: "standard" }}
        groupAggregationMode="sum"
        key="id"
        label="ID"
        placeholder="Enter value"
        position="center"
        size={57.375}
        summaryAggregationMode="none"
      />
      <Column
        id="87af3"
        alignment="left"
        format="date"
        groupAggregationMode="none"
        key="bank_date"
        label="Bank date"
        placeholder="Enter value"
        position="center"
        size={100}
        summaryAggregationMode="none"
      />
      <Column
        id="bb262"
        alignment="left"
        cellTooltipMode="overflow"
        format="string"
        groupAggregationMode="none"
        key="description"
        label="Description"
        placeholder="Enter value"
        position="center"
        size={287.1875}
        summaryAggregationMode="none"
      />
      <Column
        id="2a88d"
        alignment="left"
        editableOptions={{ showStepper: true }}
        format="tag"
        formatOptions={{ automaticColors: true }}
        groupAggregationMode="sum"
        key="balance"
        label="Balance"
        placeholder="Select option"
        position="center"
        size={84}
        summaryAggregationMode="none"
        valueOverride="{{ item === 0  ? 'balanced' : (abs(item) <10 ? '<10' : '>10') }}"
      />
      <Column
        id="0b2a2"
        alignment="center"
        format="icon"
        formatOptions={{
          icon: '{{ item ===\'Matched\'? "/icon:bold/interface-validation-check" : (item === \'Pending\'? "/icon:bold/interface-delete-1" :"/icon:bold/interface-alert-warning-circle-alternate") }}',
          color:
            "{{ item ==='Matched'? theme.success : (item === 'Pending'? theme.danger :'yellow') }}",
        }}
        groupAggregationMode="none"
        key="reconciliation_status"
        label="Reconciliation status"
        placeholder="Select option"
        position="right"
        size={98.25}
        summaryAggregationMode="none"
        valueOverride="{{ _.startCase(item) }}"
      />
      <Column
        id="1f961"
        alignment="right"
        editableOptions={{ showStepper: true }}
        format="decimal"
        formatOptions={{ showSeparators: true, notation: "standard" }}
        groupAggregationMode="sum"
        key="company"
        label="Company"
        placeholder="Enter value"
        position="center"
        size={100}
        summaryAggregationMode="none"
      />
      <Column
        id="8d159"
        alignment="left"
        format="date"
        groupAggregationMode="none"
        key="transaction_date"
        label="Transaction date"
        placeholder="Enter value"
        position="center"
        size={100}
        summaryAggregationMode="none"
      />
      <Column
        id="aa0e3"
        alignment="left"
        format="string"
        groupAggregationMode="none"
        key="transaction_description"
        label="Transaction description"
        placeholder="Enter value"
        position="center"
        size={100}
        summaryAggregationMode="none"
      />
      <Column
        id="6411b"
        alignment="right"
        editableOptions={{ showStepper: true }}
        format="decimal"
        formatOptions={{ showSeparators: true, notation: "standard" }}
        groupAggregationMode="sum"
        key="transaction_value"
        label="Transaction value"
        placeholder="Enter value"
        position="center"
        size={100}
        summaryAggregationMode="none"
      />
      <Column
        id="fdedd"
        alignment="right"
        editableOptions={{ showStepper: true }}
        format="decimal"
        formatOptions={{ showSeparators: true, notation: "standard" }}
        groupAggregationMode="sum"
        key="bank_account"
        label="Bank account"
        placeholder="Enter value"
        position="center"
        size={100}
        summaryAggregationMode="none"
      />
      <Action id="0247d" icon="bold/interface-edit-pencil" label="Action 1" />
      <ToolbarButton
        id="1a"
        icon="bold/interface-text-formatting-filter-2"
        label="Filter"
        type="filter"
      />
      <ToolbarButton
        id="3c"
        icon="bold/interface-download-button-2"
        label="Download"
        type="custom"
      >
        <Event
          event="clickToolbar"
          method="exportData"
          pluginId="tableBook3"
          type="widget"
          waitMs="0"
          waitType="debounce"
        />
      </ToolbarButton>
      <ToolbarButton
        id="4d"
        icon="bold/interface-arrows-round-left"
        label="Refresh"
        type="custom"
      >
        <Event
          event="clickToolbar"
          method="refresh"
          pluginId="tableBook3"
          type="widget"
          waitMs="0"
          waitType="debounce"
        />
      </ToolbarButton>
      <Event
        event="selectRow"
        method="run"
        params={{
          ordered: [
            {
              src: "//tableBank.clearSelection();\n//Transactions_get3.trigger();",
            },
          ],
        }}
        pluginId=""
        type="script"
        waitMs="0"
        waitType="debounce"
      />
      <Event
        event="changeFilter"
        method="trigger"
        params={{}}
        pluginId="VisibleBookIds"
        type="datasource"
        waitMs="0"
        waitType="debounce"
      />
    </Table>
    <JSONEditor
      id="BankReconciliationParameters2"
      hidden="true"
      value="{{  ReconciliationParameters.value }}"
    />
    <Container
      id="group79"
      footerPadding="4px 12px"
      headerPadding="4px 12px"
      margin="0"
      padding="0"
      showBody={true}
      showBorder={false}
      style={{ map: { background: "rgba(255, 255, 255, 0)" } }}
    >
      <View id="00030" viewKey="View 1">
        <Button id="button45" text="Train Model">
          <Event
            event="click"
            method="run"
            params={{
              map: {
                src: '\n\n// Step 3: Build the payload object\nconst payload = {\n  "company_id": 4,\n  "model_name": "journal",\n  "training_fields": ["description", "amount"],\n  "prediction_fields": ["description", "amount"],\n  "records_per_account": 100\n};\n\nconsole.log("Generated payload:", payload);\n\n// Step 4: Trigger the Transactions_get3 query with the payload\nml_model_train.trigger({\n  additionalScope: {\n    payload: payload\n  }\n});\n\n',
              },
            }}
            pluginId=""
            type="script"
            waitMs="0"
            waitType="debounce"
          />
        </Button>
        <Button id="button46" text="Predict Model">
          <Event
            event="click"
            method="run"
            params={{
              map: {
                src: '\n\n// Step 3: Build the payload object\nconst payload = {\n  "model_id": 3,\n  "transaction": {\n    "description": "Valéria",\n    "amount": 1500.00\n  },\n  "top_n": 100\n};\n\nconsole.log("Generated payload:", payload);\n\n// Step 4: Trigger the Transactions_get3 query with the payload\nml_model_predict.trigger({\n  additionalScope: {\n    payload: payload\n  }\n});\n\n',
              },
            }}
            pluginId=""
            type="script"
            waitMs="0"
            waitType="debounce"
          />
        </Button>
      </View>
    </Container>
    <Table
      id="tableBank3"
      cellSelection="none"
      clearChangesetOnSave={true}
      data="{{ BankTransactions_get.data }}"
      defaultFilters={{
        0: {
          ordered: [
            { id: "2f325" },
            { columnId: "ed9f5" },
            { operator: "isAfter" },
            { value: "{{ dateRangeBank.value.start }}" },
            { disabled: false },
          ],
        },
        1: {
          ordered: [
            { id: "542f5" },
            { columnId: "ed9f5" },
            { operator: "isBefore" },
            { value: "{{ dateRangeBank.value.end }}" },
            { disabled: false },
          ],
        },
        2: {
          id: "69209",
          columnId: "c831b",
          operator: "isOneOf",
          value: "",
          disabled: false,
        },
        3: {
          ordered: [
            { id: "057fc" },
            { columnId: "fd9d5" },
            { operator: "isNot" },
            { value: "Matched" },
            { disabled: false },
          ],
        },
        4: {
          ordered: [
            { id: "0c79c" },
            { columnId: "2478a" },
            { operator: ">=" },
            { value: "{{ minBankAmount.value }}" },
            { disabled: false },
          ],
        },
        5: {
          ordered: [
            { id: "16626" },
            { columnId: "2478a" },
            { operator: "<=" },
            { value: "{{ maxBankAmount.value }}" },
            { disabled: false },
          ],
        },
      }}
      defaultSelectedRow={{ mode: "index", indexType: "display", index: 0 }}
      emptyMessage="No rows found"
      enableSaveActions={true}
      hidden="true"
      linkedFilterId="filterBank"
      rowSelection="{{ toggleAllowRowSelection.value ? 'multiple' : 'none' }}"
      showBorder={true}
      showFooter={true}
      showHeader={true}
      style={{ headerBackground: "canvas" }}
      toolbarPosition="bottom"
    >
      <Column
        id="f4f61"
        alignment="right"
        editable={false}
        editableOptions={{ showStepper: true }}
        format="decimal"
        formatOptions={{ showSeparators: true, notation: "standard" }}
        groupAggregationMode="sum"
        key="id"
        label="ID"
        placeholder="Enter value"
        position="center"
        size={75.09375}
        summaryAggregationMode="none"
      />
      <Column
        id="a9670"
        alignment="left"
        cellTooltipMode="overflow"
        format="string"
        groupAggregationMode="none"
        key="description"
        label="Description"
        placeholder="Enter value"
        position="center"
        size={194}
        summaryAggregationMode="none"
      />
      <Column
        id="c831b"
        alignment="left"
        editableOptions={{ showStepper: true }}
        format="string"
        formatOptions={{ showSeparators: true, notation: "standard" }}
        groupAggregationMode="sum"
        key="bank_account"
        label="Bank account"
        placeholder="Enter value"
        position="center"
        size={93.15625}
        summaryAggregationMode="none"
        valueOverride="{{
  BankAccount_get.data.find(
    acc => acc.id === item
  )?.name
}}"
      />
      <Column
        id="ed9f5"
        alignment="left"
        format="date"
        groupAggregationMode="none"
        key="date"
        label="Date"
        placeholder="Enter value"
        position="center"
        size={90.75}
        summaryAggregationMode="none"
      />
      <Column
        id="2478a"
        alignment="right"
        editableOptions={{ showStepper: true }}
        format="decimal"
        formatOptions={{ showSeparators: true, notation: "standard" }}
        groupAggregationMode="sum"
        key="amount"
        label="Amount"
        placeholder="Enter value"
        position="center"
        size={92.484375}
        summaryAggregationMode="none"
      />
      <Column
        id="9e089"
        alignment="left"
        format="string"
        groupAggregationMode="none"
        key="status"
        label="Status"
        placeholder="Enter value"
        position="center"
        size={94.375}
        summaryAggregationMode="none"
      />
      <Column
        id="5046b"
        alignment="left"
        editableOptions={{ showStepper: true }}
        format="string"
        formatOptions={{ showSeparators: true, notation: "standard" }}
        groupAggregationMode="sum"
        key="entity"
        label="Entity"
        placeholder="Enter value"
        position="center"
        size={120.4375}
        summaryAggregationMode="none"
        valueOverride="{{
  Entity_get.data.find(
    acc => acc.id === item
  )?.name
}}"
      />
      <Column
        id="fd9d5"
        alignment="center"
        format="icon"
        formatOptions={{
          icon: '{{ item ===\'Matched\'? "/icon:bold/interface-validation-check" : (item === \'Pending\'? "/icon:bold/interface-delete-1" :"/icon:bold/interface-alert-warning-circle-alternate") }}',
          color:
            "{{ item ==='Matched'? theme.success : (item === 'Pending'? theme.danger :'yellow') }}",
        }}
        groupAggregationMode="none"
        key="reconciliation_status"
        label="Reconciliation status"
        placeholder="Select option"
        position="right"
        size={133.234375}
        summaryAggregationMode="none"
        valueOverride="{{ _.startCase(item) }}"
      />
      <Column
        id="af99b"
        alignment="left"
        format="boolean"
        groupAggregationMode="none"
        key="is_deleted"
        label="Is deleted"
        placeholder="Enter value"
        position="center"
        size={100}
        summaryAggregationMode="none"
      />
      <Column
        id="36e2e"
        alignment="right"
        editableOptions={{ showStepper: true }}
        format="decimal"
        formatOptions={{ showSeparators: true, notation: "standard" }}
        groupAggregationMode="sum"
        key="company"
        label="Company"
        placeholder="Enter value"
        position="center"
        summaryAggregationMode="none"
      />
      <Column
        id="179f3"
        alignment="left"
        format="tag"
        formatOptions={{ automaticColors: true }}
        groupAggregationMode="none"
        key="entity_name"
        label="Entity name"
        placeholder="Select option"
        position="center"
        summaryAggregationMode="none"
        valueOverride="{{ _.startCase(item) }}"
      />
      <Column
        id="d03c9"
        alignment="right"
        editableOptions={{ showStepper: true }}
        format="decimal"
        formatOptions={{ showSeparators: true, notation: "standard" }}
        groupAggregationMode="sum"
        key="currency"
        label="Currency"
        placeholder="Enter value"
        position="center"
        summaryAggregationMode="none"
      />
      <Column
        id="dba8b"
        alignment="left"
        format="string"
        groupAggregationMode="none"
        key="updated_at"
        label="Updated at"
        placeholder="Enter value"
        position="center"
        summaryAggregationMode="none"
      />
      <Column
        id="bcde7"
        alignment="right"
        editableOptions={{ showStepper: true }}
        format="decimal"
        formatOptions={{ showSeparators: true, notation: "standard" }}
        groupAggregationMode="sum"
        key="updated_by"
        label="Updated by"
        placeholder="Enter value"
        position="center"
        summaryAggregationMode="none"
      />
      <ToolbarButton
        id="1a"
        icon="bold/interface-text-formatting-filter-2"
        label="Filter"
        type="filter"
      />
      <ToolbarButton
        id="3c"
        icon="bold/interface-download-button-2"
        label="Download"
        type="custom"
      >
        <Event
          event="clickToolbar"
          method="exportData"
          pluginId="tableBank"
          type="widget"
          waitMs="0"
          waitType="debounce"
        />
      </ToolbarButton>
      <ToolbarButton
        id="4d"
        icon="bold/interface-arrows-round-left"
        label="Refresh"
        type="custom"
      >
        <Event
          event="clickToolbar"
          method="refresh"
          pluginId="tableBank"
          type="widget"
          waitMs="0"
          waitType="debounce"
        />
      </ToolbarButton>
      <Event
        event="selectRow"
        method="run"
        params={{
          ordered: [
            {
              src: '//tableBook.clearSelection();\n//Transactions_get3.trigger();\n\n(() => {\n  const bankRows = tableBank.selectedRow.data;\n  const bookRows = tableBook3.selectedRow.data;\n\n  if (!bankRows || !bookRows) {\n    return { error: "Please select records in both tables." };\n  }\n\n  const toArray = val => Array.isArray(val) ? val : [val];\n\n  const bankCombo = toArray(bankRows);\n  const bookCombo = toArray(bookRows);\n\n  const bank_transaction_details = bankCombo.map(tx => ({\n    id: tx.id,\n    date: tx.date,\n    amount: tx.amount,\n    description: tx.memo,\n    bank_account: tx.bank_account\n      ? {\n          id: tx.bank_account.id,\n          name: tx.bank_account.name,\n        }\n      : null,\n    entity: tx.entity ? tx.entity.id : null,\n    currency: tx.currency?.id || null,\n  }));\n\n  const journal_entry_details = bookCombo.map(entry => ({\n    id: entry.id,\n    date: entry.transaction?.date,\n    amount: entry.amount,\n    description: entry.transaction?.description,\n    account: entry.account\n      ? {\n          id: entry.account.id,\n          account_code: entry.account.account_code,\n          name: entry.account.name,\n        }\n      : null,\n    entity: entry.entity\n      ? {\n          id: entry.entity.id,\n          name: entry.entity.name,\n        }\n      : null,\n    transaction: entry.transaction\n      ? {\n          id: entry.transaction.id,\n          description: entry.transaction.description,\n          date: entry.transaction.date,\n        }\n      : null,\n  }));\n\n  const sum = arr => arr.reduce((acc, val) => acc + Number(val.amount || 0), 0);\n  const sum_bank = sum(bankCombo);\n  const sum_book = sum(bookCombo);\n  const difference = sum_bank - sum_book;\n\n  const avgDateDiff = (() => {\n    const diffs = [];\n    bankCombo.forEach(tx => {\n      bookCombo.forEach(entry => {\n        const date1 = new Date(tx.date);\n        const date2 = new Date(entry.transaction?.date);\n        if (!isNaN(date1) && !isNaN(date2)) {\n          const diff = Math.abs((date1 - date2) / (1000 * 3600 * 24));\n          diffs.push(diff);\n        }\n      });\n    });\n    if (diffs.length === 0) return 0;\n    return diffs.reduce((a, b) => a + b, 0) / diffs.length;\n  })();\n\n  const bank_summary = bankCombo\n    .map(tx => `ID: ${tx.id}, Date: ${tx.date}, Amount: ${tx.amount}, Desc: ${tx.description}`)\n    .join("\\n");\n\n  const journal_summary = bookCombo\n    .map(entry => {\n      const acct = entry.account || {};\n      const direction = entry.debit_amount ? "DEBIT" : "CREDIT";\n      const amount = Number(entry.debit_amount || entry.credit_amount || 0);\n      return `ID: ${entry.transaction?.id}, Date: ${entry.transaction?.date}, JE: ${direction} ${amount} - (${acct.account_code}) ${acct.name}, Desc: ${entry.transaction?.description}`;\n    })\n    .join("\\n");\n\n  return {\n    match_type: "manual",\n    bank_transaction_details,\n    journal_entry_details,\n    bank_transaction_summary: bank_summary,\n    journal_entries_summary: journal_summary,\n    bank_ids: bankCombo.map(tx => tx.id),\n    journal_entries_ids: bookCombo.map(entry => entry.id),\n    sum_bank,\n    sum_book,\n    difference,\n    avg_date_diff: avgDateDiff,\n    confidence_score: 0.95 // arbitrary, since user selects manually\n  };\n})();\n',
            },
          ],
        }}
        pluginId=""
        type="script"
        waitMs="0"
        waitType="debounce"
      />
      <Event
        event="changeFilter"
        method="trigger"
        params={{}}
        pluginId="VisibleBankIds"
        type="datasource"
        waitMs="0"
        waitType="debounce"
      />
    </Table>
    <ToggleButton
      id="switchAIChat"
      horizontalAlign="stretch"
      iconForFalse="bold/interface-arrows-button-left"
      iconForTrue="bold/interface-arrows-button-right"
      iconPosition="right"
      styleVariant="outline"
      text="AI Chat"
    />
    <Container
      id="group78"
      footerPadding="4px 12px"
      headerPadding="4px 12px"
      margin="0"
      padding="0"
      showBody={true}
      showBorder={false}
      style={{ map: { background: "rgba(255, 255, 255, 0)" } }}
    >
      <View id="00030" viewKey="View 1">
        <Button id="button42" text="Train Model">
          <Event
            event="click"
            method="run"
            params={{
              map: {
                src: '\n\n// Step 3: Build the payload object\nconst payload = {\n  "company_id": 4,\n  "model_name": "categorization",\n  "training_fields": ["description", "amount"],\n  "prediction_fields": ["description", "amount"],\n  "records_per_account": 1\n};\n\nconsole.log("Generated payload:", payload);\n\n// Step 4: Trigger the Transactions_get3 query with the payload\nml_model_train.trigger({\n  additionalScope: {\n    payload: payload\n  }\n});\n\n',
              },
            }}
            pluginId=""
            type="script"
            waitMs="0"
            waitType="debounce"
          />
        </Button>
        <Button id="button44" text="Predict Model">
          <Event
            event="click"
            method="run"
            params={{
              map: {
                src: '\n\n// Step 3: Build the payload object\nconst payload = {\n  "model_id": 1,\n  "transaction": {\n    "description": "Valéria",\n    "amount": 1500.00\n  },\n  "top_n": 100\n};\n\nconsole.log("Generated payload:", payload);\n\n// Step 4: Trigger the Transactions_get3 query with the payload\nml_model_predict.trigger({\n  additionalScope: {\n    payload: payload\n  }\n});\n\n',
              },
            }}
            pluginId=""
            type="script"
            waitMs="0"
            waitType="debounce"
          />
        </Button>
      </View>
    </Container>
    <NumberInput
      id="currency1"
      currency="USD"
      format="currency"
      inputValue={0}
      labelPosition="top"
      placeholder="Enter value"
      showSeparators={true}
      showStepper={true}
      value={0}
    />
  </Frame>
</Screen>
