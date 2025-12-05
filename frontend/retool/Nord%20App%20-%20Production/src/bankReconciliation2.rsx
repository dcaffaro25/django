<Screen
  id="bankReconciliation2"
  _customShortcuts={[]}
  _hashParams={[]}
  _searchParams={[]}
  browserTitle=""
  title={null}
  urlSlug=""
  uuid="2b1eb443-a36a-4869-9c82-d7e4a6964d00"
>
  <State
    id="manageBanks3"
    value={
      '{\n"endpoint_path": "api/banks/",\n"tenant": {{ tenant_subdomain.value}},\n"current_record": [],\n"nome_plural": "Bancos",\n"nome_singular": "Banco",\n"masculino":true,\n"form_key": "name",\n"show_value": "name",\n"menu_visible": true,\n"modal_list_show": false,\n"modal_addedit_show": false,\n"form_fields": \n{\n"name":{\n    "default_value":"teste",\n    "disabled":false},\n"country":{\n    "default_value":"Brasil",\n    "disabled":false}\n}\n}'
    }
  />
  <State
    id="ReconciliationMatches2"
    value="{{ Transactions_get7.data.suggestions }}"
  />
  <RESTQuery
    id="AccountingTransaction_template2"
    cookies={'[{"key":"","value":""}]'}
    headers="[]"
    isHidden={false}
    isMultiplayerEdited={false}
    query="/{{ tenant_subdomain.value }}/api/transactions/download_import_template/"
    queryDisabled="{{ tenant_subdomain.value == null }}"
    resourceDisplayName="Tenant Specific"
    resourceName="e4a763c9-4f5e-4f5a-99f7-6a33454d4577"
    resourceTypeOverride=""
  />
  <Function
    id="groupedBankTransactions2"
    funcBody={include("../lib/groupedBankTransactions2.js", "string")}
    runBehavior="debounced"
  />
  <Function
    id="ReconciliationParameters2"
    funcBody={include("../lib/ReconciliationParameters2.js", "string")}
    runBehavior="debounced"
  />
  <State id="Conciliation_selected2" />
  <JavascriptQuery
    id="VisibleBankIds2"
    isMultiplayerEdited={false}
    notificationDuration={4.5}
    query={include("../lib/VisibleBankIds2.js", "string")}
    resourceName="JavascriptQuery"
    showSuccessToaster={false}
  />
  <RESTQuery
    id="Transactions_get5"
    cookies={'[{"key":"","value":""}]'}
    headers="[]"
    isHidden={false}
    isMultiplayerEdited={false}
    query="/{{ tenant_subdomain.value }}/api/transactions"
    queryDisabled="{{ tenant_subdomain.value == null }}"
    queryTimeout="600000"
    resourceDisplayName="Tenant Specific"
    resourceName="e4a763c9-4f5e-4f5a-99f7-6a33454d4577"
    resourceTypeOverride=""
  />
  <RESTQuery
    id="Transactions_get6"
    body="{{ BankReconciliationParameters3.value }}"
    bodyType="raw"
    cookies={'[{"key":"","value":""}]'}
    headers={'[{"key":"Content-Type","value":"application/json"}]'}
    isHidden={false}
    isMultiplayerEdited={false}
    query="/{{ tenant_subdomain.value }}/api/bank_transactions/match_many_to_many/"
    queryDisabled="{{ tenant_subdomain.value == null }}"
    resourceDisplayName="Tenant Specific"
    resourceName="e4a763c9-4f5e-4f5a-99f7-6a33454d4577"
    resourceTypeOverride=""
    runWhenModelUpdates={false}
    type="POST"
  />
  <RESTQuery
    id="BankTransactions_get2"
    cookies={'[{"key":"","value":""}]'}
    headers={'[{"key":"Content-Type","value":"application/json"}]'}
    isHidden={false}
    isMultiplayerEdited={false}
    query="/{{ tenant_subdomain.value }}/api/bank_transactions/"
    queryDisabled="{{ tenant_subdomain.value == null }}"
    resourceDisplayName="Tenant Specific"
    resourceName="e4a763c9-4f5e-4f5a-99f7-6a33454d4577"
    resourceTypeOverride=""
  />
  <RESTQuery
    id="BankAccount_get2"
    cacheKeyTtl={300}
    cookies={'[{"key":"","value":""}]'}
    enableCaching={true}
    headers={'[{"key":"Content-Type","value":"application/json"}]'}
    isHidden={false}
    isMultiplayerEdited={false}
    query="/{{ tenant_subdomain.value }}/api/bank_accounts/"
    queryDisabled="{{ tenant_subdomain.value == null }}"
    resourceDisplayName="Tenant Specific"
    resourceName="e4a763c9-4f5e-4f5a-99f7-6a33454d4577"
    resourceTypeOverride=""
  />
  <RESTQuery
    id="Transactions_get7"
    body="{{ BankReconciliationParameters4.value }}"
    bodyType="raw"
    cookies={'[{"key":"","value":""}]'}
    headers={'[{"key":"Content-Type","value":"application/json"}]'}
    isHidden={false}
    isMultiplayerEdited={false}
    query="/{{ tenant_subdomain.value }}/api/bank_transactions/match_many_to_many_with_set2/"
    queryDisabled="{{ tenant_subdomain.value == null }}"
    queryTimeout="600000"
    resourceDisplayName="Tenant Specific"
    resourceName="e4a763c9-4f5e-4f5a-99f7-6a33454d4577"
    resourceTypeOverride=""
    runWhenModelUpdates={false}
    type="POST"
  />
  <State
    id="manageBankAccounts2"
    value={
      '{\n"endpoint_path": "api/bank_accounts/",\n"auxiliar_endpoints": ["api/entities/", "api/banks/", "api/currencies/"],\n"tenant": {{ tenant_subdomain.value }},\n"current_record": [],\n"nome_plural": "Contas Bancárias",\n"nome_singular": "Conta Bancária",\n"masculino":false,\n"form_key": "name",\n"show_value": "name",\n"menu_visible": true,\n"modal_list_show": false,\n"modal_addedit_show": false,\n"form_fields": \n{\n"name":{\n    "default_value":"teste",\n    "disabled":true}\n}\n}'
    }
  />
  <RESTQuery
    id="Conciliation_get2"
    cookies={'[{"key":"","value":""}]'}
    headers="[]"
    isHidden={false}
    isMultiplayerEdited={false}
    query="/{{ tenant_subdomain.value }}/api/reconciliation"
    queryDisabled="{{ tenant_subdomain.value == null }}"
    resourceDisplayName="Tenant Specific"
    resourceName="e4a763c9-4f5e-4f5a-99f7-6a33454d4577"
    resourceTypeOverride=""
  />
  <RESTQuery
    id="Transactions_get8"
    body="{{ BankReconciliationParameters4.value }}"
    bodyType="raw"
    cookies={'[{"key":"","value":""}]'}
    headers={'[{"key":"Content-Type","value":"application/json"}]'}
    isHidden={false}
    isMultiplayerEdited={false}
    query="/{{ tenant_subdomain.value }}/api/bank_transactions/match_many_to_many_with_set2/"
    queryDisabled="{{ tenant_subdomain.value == null }}"
    queryTimeout="100000"
    resourceDisplayName="Tenant Specific"
    resourceName="e4a763c9-4f5e-4f5a-99f7-6a33454d4577"
    resourceTypeOverride=""
    runWhenModelUpdates={false}
    type="POST"
  />
  <RESTQuery
    id="OFXTransaction_import5"
    _additionalScope={["content"]}
    body="{{ content }}"
    bodyType="raw"
    cookies={'[{"key":"","value":""}]'}
    headers={'[{"key":"Content-Type","value":"application/json"}]'}
    isHidden={false}
    isMultiplayerEdited={false}
    query="/{{ tenant_subdomain.value }}/api/bank_transactions/finalize_ofx_import/"
    queryDisabled="{{ tenant_subdomain.value == null }}"
    resourceDisplayName="Tenant Specific"
    resourceName="e4a763c9-4f5e-4f5a-99f7-6a33454d4577"
    resourceTypeOverride=""
    runWhenModelUpdates={false}
    type="POST"
  />
  <RESTQuery
    id="MatchRecords_post2"
    _additionalScope={["content"]}
    body="{{ content }}"
    bodyType="raw"
    cookies={'[{"key":"","value":""}]'}
    headers={'[{"key":"Content-Type","value":"application/json"}]'}
    isHidden={false}
    isMultiplayerEdited={false}
    query="/{{ tenant_subdomain.value }}/api/bank_transactions/finalize_reconciliation_matches/"
    queryDisabled="{{ tenant_subdomain.value == null }}"
    queryTimeout="100000"
    resourceDisplayName="Tenant Specific"
    resourceName="e4a763c9-4f5e-4f5a-99f7-6a33454d4577"
    resourceTypeOverride=""
    runWhenModelUpdates={false}
    type="POST"
  />
  <JavascriptQuery
    id="updateInput2"
    notificationDuration={4.5}
    resourceName="JavascriptQuery"
    showSuccessToaster={false}
  />
  <JavascriptQuery
    id="VisibleBookIds2"
    isMultiplayerEdited={false}
    notificationDuration={4.5}
    query={include("../lib/VisibleBookIds2.js", "string")}
    resourceName="JavascriptQuery"
    showSuccessToaster={false}
  />
  <RESTQuery
    id="AccountingTransaction_import2"
    body={
      '[{"key":"file","value":"{{ fileDropzoneBook2.value[0] }}","operation":"binary"}]'
    }
    bodyType="form-data"
    cookies={'[{"key":"","value":""}]'}
    headers="[]"
    isHidden={false}
    isMultiplayerEdited={false}
    query="/{{ tenant_subdomain.value }}/api/transactions/bulk_import/"
    queryDisabled="{{ tenant_subdomain.value == null }}"
    resourceDisplayName="Tenant Specific"
    resourceName="e4a763c9-4f5e-4f5a-99f7-6a33454d4577"
    resourceTypeOverride=""
    runWhenModelUpdates={false}
    type="POST"
  />
  <RESTQuery
    id="Entity_get2"
    cacheKeyTtl={300}
    cookies={'[{"key":"","value":""}]'}
    enableCaching={true}
    headers={'[{"key":"Content-Type","value":"application/json"}]'}
    isHidden={false}
    isMultiplayerEdited={false}
    query="/{{ tenant_subdomain.value }}/api/entities-mini/"
    queryDisabled="{{ tenant_subdomain.value == null }}"
    queryTimeout="100000"
    resourceDisplayName="Tenant Specific"
    resourceName="e4a763c9-4f5e-4f5a-99f7-6a33454d4577"
    resourceTypeOverride=""
  />
  <RESTQuery
    id="Conciliation_delete2"
    body="{{
  (table47.selectedRows?.length > 0
    ? table47.selectedRows.map(row => row.id)
    : [Conciliation_selected2.value.id]
  )
}}"
    bodyType="raw"
    headers={'[{"key":"Content-Type","value":"application/json"}]'}
    isMultiplayerEdited={false}
    query="/{{ tenant_subdomain.value }}/api/reconciliation/bulk_delete/"
    resourceDisplayName="Tenant Specific"
    resourceName="e4a763c9-4f5e-4f5a-99f7-6a33454d4577"
    runWhenModelUpdates={false}
    type="DELETE"
  >
    <Event
      event="success"
      method="trigger"
      params={{}}
      pluginId="Conciliation_get2"
      type="datasource"
      waitMs="0"
      waitType="debounce"
    />
  </RESTQuery>
  <State id="ReconParameters2" />
  <Function
    id="groupedTransactions2"
    funcBody={include("../lib/groupedTransactions2.js", "string")}
    runBehavior="debounced"
  />
  <RESTQuery
    id="Bank_get2"
    cookies={'[{"key":"","value":""}]'}
    headers={'[{"key":"Content-Type","value":"application/json"}]'}
    isHidden={false}
    isMultiplayerEdited={false}
    query="/{{ tenant_subdomain.value }}/api/banks/"
    queryDisabled="{{ tenant_subdomain.value == null }}"
    resourceDisplayName="Tenant Specific"
    resourceName="e4a763c9-4f5e-4f5a-99f7-6a33454d4577"
    resourceTypeOverride=""
  />
  <RESTQuery
    id="JournalEntries_get"
    cookies={'[{"key":"","value":""}]'}
    headers={'[{"key":"Content-Type","value":"application/json"}]'}
    isHidden={false}
    isMultiplayerEdited={false}
    query="/{{ tenant_subdomain.value }}/api/journal_entries/"
    queryDisabled="{{ tenant_subdomain.value == null }}"
    queryTimeout="100000"
    resourceDisplayName="Tenant Specific"
    resourceName="e4a763c9-4f5e-4f5a-99f7-6a33454d4577"
    resourceTypeOverride=""
  />
  <Include src="./modalFrame8.rsx" />
  <Include src="./modalImportTransactions2.rsx" />
  <Include src="./modalManualConciliation2.rsx" />
  <Frame
    id="$main11"
    enableFullBleed={false}
    isHiddenOnDesktop={false}
    isHiddenOnMobile={false}
    padding="8px 12px"
    sticky={null}
    type="main"
  >
    <Container
      id="group61"
      _direction="vertical"
      _flexWrap={true}
      _gap="0px"
      _type="stack"
      footerPadding="4px 12px"
      headerPadding="4px 12px"
      margin="0"
      padding="0"
      showBody={true}
      showBorder={false}
      style={{ ordered: [{ background: "rgba(255, 255, 255, 0)" }] }}
    >
      <View id="d5693" viewKey="View 1">
        <Container
          id="container19"
          _gap="0px"
          footerPadding="4px 12px"
          headerPadding="4px 12px"
          overflowType="hidden"
          padding="12px"
          showBody="{{ buttonShowDetailPendencias2.value }}"
          showHeader={true}
        >
          <Header>
            <Container
              id="group59"
              _align="center"
              _gap="0px"
              _justify="space-between"
              _type="stack"
              footerPadding="4px 12px"
              headerPadding="4px 12px"
              heightType="fixed"
              margin="0"
              overflowType="hidden"
              padding="0"
              showBody={true}
              showBorder={false}
              style={{ ordered: [{ background: "rgba(255, 255, 255, 0)" }] }}
            >
              <View id="c9c98" viewKey="View 1">
                <ButtonGroup2
                  id="buttonGroup6"
                  alignment="right"
                  overflowPosition={2}
                >
                  <ButtonGroup2-Button
                    id="e1f05"
                    icon="bold/interface-add-1"
                    iconPosition="left"
                    styleVariant="outline"
                    text="Banco"
                  >
                    <Event
                      event="click"
                      method="show"
                      params={{ ordered: [] }}
                      pluginId="modalImportOFX2"
                      type="widget"
                      waitMs="0"
                      waitType="debounce"
                    />
                  </ButtonGroup2-Button>
                  <ButtonGroup2-Button
                    id="6b1fc"
                    icon="bold/interface-add-1"
                    iconPosition="left"
                    styleVariant="outline"
                    text="Transações"
                  >
                    <Event
                      event="click"
                      method="show"
                      params={{ ordered: [] }}
                      pluginId="modalImportTransactions2"
                      type="widget"
                      waitMs="0"
                      waitType="debounce"
                    />
                  </ButtonGroup2-Button>
                </ButtonGroup2>
                <Container
                  id="group63"
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
                    ordered: [{ background: "rgba(255, 255, 255, 0)" }],
                  }}
                >
                  <View id="27d6c" viewKey="View 1">
                    <ToggleButton
                      id="toggleShowParametros2"
                      disabled="true"
                      horizontalAlign="stretch"
                      iconForFalse="bold/interface-edit-view"
                      iconForTrue="bold/interface-edit-view-off"
                      styleVariant="outline"
                      text="{{ self.value ? 'Parametros' : 'Parametros' }}"
                    />
                    <ToggleButton
                      id="toggleAllowRowSelection2"
                      horizontalAlign="stretch"
                      iconPosition="right"
                      styleVariant="outline"
                      text="{{ self.value ? 'Manual' : 'Auto' }}"
                    />
                  </View>
                </Container>
                <Container
                  id="group60"
                  _align="center"
                  _gap="0px"
                  _type="stack"
                  footerPadding="4px 12px"
                  headerPadding="4px 12px"
                  margin="0"
                  padding="0"
                  showBody={true}
                  showBorder={false}
                  style={{
                    ordered: [{ background: "rgba(255, 255, 255, 0)" }],
                  }}
                >
                  <View id="c9c98" viewKey="View 1">
                    <Text
                      id="containerTitle20"
                      value="#### Resumo das Pendências de Conciliação"
                      verticalAlign="center"
                    />
                    <ToggleButton
                      id="buttonShowDetailPendencias2"
                      horizontalAlign="stretch"
                      iconForFalse="bold/interface-arrows-button-down"
                      iconForTrue="bold/interface-arrows-button-up"
                      iconPosition="right"
                      style={{ ordered: [] }}
                      styleVariant="outline"
                    />
                  </View>
                </Container>
              </View>
            </Container>
          </Header>
          <View id="c9c98" viewKey="View 1">
            <Container
              id="group57"
              _gap="0px"
              footerPadding="4px 12px"
              headerPadding="4px 12px"
              heightType="fixed"
              margin="0"
              overflowType="hidden"
              padding="0"
              showBody={true}
              showBorder={false}
              style={{ ordered: [{ background: "rgba(255, 255, 255, 0)" }] }}
            >
              <View id="c9c98" viewKey="View 1">
                <Container
                  id="group52"
                  _align="center"
                  _gap="0px"
                  _justify="center"
                  _type="stack"
                  footerPadding="4px 12px"
                  headerPadding="4px 12px"
                  margin="0"
                  overflowType="hidden"
                  padding="0"
                  showBody={true}
                  showBorder={false}
                  style={{
                    ordered: [{ background: "rgba(255, 255, 255, 0)" }],
                  }}
                >
                  <View id="c9c98" viewKey="View 1">
                    <Container
                      id="group58"
                      _align="center"
                      _direction="vertical"
                      _gap="0px"
                      _type="stack"
                      footerPadding="4px 12px"
                      headerPadding="4px 12px"
                      heightType="fixed"
                      overflowType="hidden"
                      padding="0"
                      showBody={true}
                      showBorder={false}
                      style={{
                        ordered: [{ background: "rgba(255, 255, 255, 0)" }],
                      }}
                    >
                      <View id="c9c98" viewKey="View 1">
                        <Chart
                          id="barChart3"
                          barGap={0.4}
                          barMode="group"
                          clearOnEmptyData={true}
                          legendPosition="top"
                          selectedPoints="[]"
                          showAutoscale={true}
                          showResetView={true}
                          showToolbarAddOn={true}
                          showZoomIn={true}
                          showZoomOut={true}
                          stackedBarTotalsDataLabelPosition="none"
                          title={null}
                          xAxisRangeMax=""
                          xAxisRangeMin=""
                          xAxisScale="category"
                          xAxisShowTickLabels={true}
                          xAxisTickFormatMode="gui"
                          xAxisTitleStandoff={20}
                          yAxis2LineWidth={1}
                          yAxis2RangeMax=""
                          yAxis2RangeMin=""
                          yAxis2ShowTickLabels={true}
                          yAxis2TickFormatMode="gui"
                          yAxis2TitleStandoff={20}
                          yAxisRangeMax=""
                          yAxisRangeMin=""
                          yAxisShowTickLabels={true}
                          yAxisTickFormatMode="gui"
                          yAxisTitleStandoff={20}
                        >
                          <Series
                            id="0"
                            aggregationType="none"
                            colorArray={{ array: ["{{ theme.primary }}"] }}
                            colorArrayDropDown={{
                              array: ["{{ theme.primary }}"],
                            }}
                            colorInputMode="colorArrayDropDown"
                            connectorLineColor="#000000"
                            dataLabelPosition="inside"
                            datasourceMode="manual"
                            decreasingBorderColor="{{ theme.danger }}"
                            decreasingColor="{{ theme.danger }}"
                            filteredGroups={null}
                            filteredGroupsMode="source"
                            gradientColorArray={{
                              array: [
                                { array: ["0.0", "{{ theme.success }}"] },
                                { array: ["1.0", "{{ theme.primary }}"] },
                              ],
                            }}
                            groupBy={{ array: [] }}
                            groupByDropdownType="source"
                            groupByStyles={{}}
                            hoverTemplate="<b>%{x}</b><br>%{fullData.name}: %{y}<extra></extra>"
                            hoverTemplateArray="<b>%{x}</b><br>%{fullData.name}: %{y}<extra></extra>"
                            hoverTemplateMode="source"
                            increasingBorderColor="{{ theme.success }}"
                            increasingColor="{{ theme.success }}"
                            lineColor="{{ theme.primary }}"
                            lineDash="solid"
                            lineShape="linear"
                            lineUnderFillMode="none"
                            lineWidth={2}
                            markerBorderColor={null}
                            markerBorderWidth={0}
                            markerColor="{{ theme.primary }}"
                            markerSize={6}
                            markerSymbol="circle"
                            name="Banco"
                            showMarkers={false}
                            textTemplate="%{y}"
                            textTemplateMode="source"
                            type="bar"
                            waterfallBase={0}
                            waterfallMeasures={null}
                            waterfallMeasuresMode="source"
                            xData="{{ Object.keys(groupedBankTransactions2.value) }}"
                            xDataMode="manual"
                            yAxis="y"
                            yData="{{ Object.values(groupedBankTransactions2.value).map(g => g.total) }}"
                            yDataMode="manual"
                            zData={null}
                            zDataMode="manual"
                          />
                          <Series
                            id="1"
                            aggregationType="none"
                            colorArray={{ array: ["{{ theme.primary }}"] }}
                            colorArrayDropDown={{
                              array: ["{{ theme.primary }}"],
                            }}
                            colorInputMode="colorArrayDropDown"
                            connectorLineColor="#000000"
                            dataLabelPosition="none"
                            datasourceMode="manual"
                            decreasingBorderColor="{{ theme.danger }}"
                            decreasingColor="{{ theme.danger }}"
                            filteredGroups={null}
                            filteredGroupsMode="source"
                            gradientColorArray={{
                              array: [
                                { array: ["0.0", "{{ theme.success }}"] },
                                { array: ["1.0", "{{ theme.primary }}"] },
                              ],
                            }}
                            groupBy={{ array: [] }}
                            groupByDropdownType="source"
                            groupByStyles={{}}
                            hidden={false}
                            hiddenMode="manual"
                            hoverTemplate="<b>%{x}</b><br>%{fullData.name}: %{y}<extra></extra>"
                            hoverTemplateArray="<b>%{x}</b><br>%{fullData.name}: %{y}<extra></extra>"
                            hoverTemplateMode="source"
                            increasingBorderColor="{{ theme.success }}"
                            increasingColor="{{ theme.success }}"
                            lineColor="{{ theme.primary }}"
                            lineDash="solid"
                            lineShape="linear"
                            lineUnderFillMode="none"
                            lineWidth={2}
                            markerBorderColor={null}
                            markerBorderWidth={0}
                            markerColor="{{ theme.tertiary }}"
                            markerSize={6}
                            markerSymbol="circle"
                            name="Contabilidade"
                            showMarkers={false}
                            textTemplateMode="manual"
                            type="bar"
                            waterfallBase={0}
                            waterfallMeasures={null}
                            waterfallMeasuresMode="source"
                            xData="{{ Object.keys(groupedTransactions2.value) }}"
                            xDataMode="manual"
                            yAxis="y"
                            yData="{{ Object.values(groupedTransactions2.value).map(g => g.total) }}"
                            yDataMode="manual"
                            zData={null}
                            zDataMode="manual"
                          />
                          <Event
                            enabled="{{ barChart3.selectedPoints[0] && toggleButton5.value }}"
                            event="select"
                            method="setValue"
                            params={{
                              ordered: [
                                {
                                  value: {
                                    ordered: [
                                      {
                                        start:
                                          '{{ (() => { \n  const key = barChart3.selectedPoints[0].x; \n  if(key.includes("W")) { \n    const [year, weekPart] = key.split("-W"), y = parseInt(year), w = parseInt(weekPart); \n    const simple = new Date(y, 0, 1 + (w - 1) * 7), dow = simple.getDay() || 7, start = new Date(simple); \n    dow <= 4 ? start.setDate(simple.getDate() - simple.getDay() + 1) : start.setDate(simple.getDate() + 8 - simple.getDay()); \n    return start.toISOString().slice(0,10); \n  } else if(key.includes("Q")) { \n    const [year, q] = key.split("-Q"), y = parseInt(year), qtr = parseInt(q), startMonth = (qtr - 1) * 3; \n    return new Date(y, startMonth, 1).toISOString().slice(0,10); \n  } else if(key.split("-").length === 2) { \n    const [year, month] = key.split("-"), y = parseInt(year), m = parseInt(month) - 1; \n    return new Date(y, m, 1).toISOString().slice(0,10); \n  } else { \n    const y = parseInt(key); \n    return new Date(y, 0, 1).toISOString().slice(0,10); \n  } \n})() }}',
                                      },
                                      {
                                        end: '{{ (() => { \n  const key = barChart3.selectedPoints[0].x; \n  if(key.includes("W")) { \n    const [year, weekPart] = key.split("-W"), y = parseInt(year), w = parseInt(weekPart); \n    const simple = new Date(y, 0, 1 + (w - 1) * 7), dow = simple.getDay() || 7, start = new Date(simple); \n    dow <= 4 ? start.setDate(simple.getDate() - simple.getDay() + 1) : start.setDate(simple.getDate() + 8 - simple.getDay()); \n    const end = new Date(start); end.setDate(start.getDate() + 6); \n    return end.toISOString().slice(0,10); \n  } else if(key.includes("Q")) { \n    const [year, q] = key.split("-Q"), y = parseInt(year), qtr = parseInt(q), startMonth = (qtr - 1) * 3, endMonth = startMonth + 2; \n    return new Date(y, endMonth + 1, 0).toISOString().slice(0,10); \n  } else if(key.split("-").length === 2) { \n    const [year, month] = key.split("-"), y = parseInt(year), m = parseInt(month) - 1; \n    return new Date(y, m + 1, 0).toISOString().slice(0,10); \n  } else { \n    const y = parseInt(key); \n    return new Date(y, 11, 31).toISOString().slice(0,10); \n  } \n})() }}\n',
                                      },
                                    ],
                                  },
                                },
                              ],
                            }}
                            pluginId="dateRange3"
                            type="widget"
                            waitMs="0"
                            waitType="debounce"
                          />
                        </Chart>
                        <Container
                          id="group51"
                          _gap="0px"
                          _type="stack"
                          footerPadding="4px 12px"
                          headerPadding="4px 12px"
                          heightType="fixed"
                          margin="0"
                          overflowType="hidden"
                          padding="0"
                          showBody={true}
                          showBorder={false}
                          style={{
                            ordered: [{ background: "rgba(255, 255, 255, 0)" }],
                          }}
                        >
                          <View id="c9c98" viewKey="View 1">
                            <ToggleButton
                              id="toggleButton4"
                              horizontalAlign="stretch"
                              iconPosition="right"
                              style={{ ordered: [] }}
                              styleVariant="outline"
                              text="{{ self.value ? 'sum' : 'count' }}"
                            />
                            <ToggleButton
                              id="toggleButton5"
                              horizontalAlign="stretch"
                              iconPosition="right"
                              style={{ ordered: [] }}
                              styleVariant="outline"
                              text="{{ self.value ? 'Dinâmico' : 'Estático' }}"
                            />
                            <SplitButton
                              id="splitButton2"
                              _colorByIndex={["", "", "", ""]}
                              _fallbackTextByIndex={["", "", "", ""]}
                              _imageByIndex={["", "", "", ""]}
                              _values={["", "", "", "Action 4"]}
                              itemMode="static"
                              overlayMaxHeight={375}
                              showSelectionIndicator={true}
                              style={{ ordered: [] }}
                              styleVariant="outline"
                            >
                              <Option id="ef6e0" label="week" />
                              <Option id="a266a" label="month" />
                              <Option id="abea1" label="quarter" />
                              <Option
                                id="a1bf2"
                                disabled={false}
                                hidden={false}
                                label="year"
                              />
                            </SplitButton>
                          </View>
                        </Container>
                      </View>
                    </Container>
                    <Container
                      id="group56"
                      _direction="vertical"
                      _gap="20px"
                      _type="stack"
                      footerPadding="4px 12px"
                      headerPadding="4px 12px"
                      padding="0"
                      showBody={true}
                      showBorder={false}
                      style={{
                        ordered: [{ background: "rgba(255, 255, 255, 0)" }],
                      }}
                    >
                      <View id="c9c98" viewKey="View 1">
                        <Statistic
                          id="statistic4"
                          currency="BRL"
                          formattingStyle="currency"
                          label="Bancos"
                          labelCaption="Não Conciliado"
                          positiveTrend="{{ self.value >= 0 }}"
                          secondaryCurrency="USD"
                          secondaryPositiveTrend="{{ self.secondaryValue >= 0 }}"
                          secondaryShowSeparators={true}
                          secondaryValue="{{ Object.values(groupedBankTransactions2.value).reduce((acc, group) => acc + group.count, 0) }}"
                          showSeparators={true}
                          value="{{ Object.values(groupedBankTransactions2.value).reduce((acc, group) => acc + group.total, 0) }}"
                        />
                        <Statistic
                          id="statistic5"
                          currency="BRL"
                          formattingStyle="currency"
                          label="Contabilidade"
                          labelCaption="Não Conciliado"
                          positiveTrend="{{ self.value >= 0 }}"
                          secondaryCurrency="USD"
                          secondaryPositiveTrend="{{ self.secondaryValue >= 0 }}"
                          secondaryShowSeparators={true}
                          secondaryValue="{{ Object.values(groupedTransactions2.value).reduce((acc, group) => acc + group.count, 0) }}"
                          showSeparators={true}
                          value="{{ Object.values(groupedTransactions2.value).reduce((acc, group) => acc + group.total, 0) }}"
                        />
                      </View>
                    </Container>
                  </View>
                </Container>
              </View>
            </Container>
          </View>
        </Container>
        <Container
          id="group62"
          _gap="0px"
          _type="stack"
          footerPadding="4px 12px"
          headerPadding="4px 12px"
          margin="0"
          padding="0"
          showBody={true}
          showBorder={false}
          style={{ ordered: [{ background: "rgba(255, 255, 255, 0)" }] }}
        >
          <View id="c9c98" viewKey="View 1">
            <Container
              id="container20"
              footerPadding="4px 12px"
              headerPadding="4px 12px"
              padding="12px"
              showBody={true}
            >
              <View id="c9c98" viewKey="View 1">
                <Container
                  id="group55"
                  _direction="vertical"
                  _flexWrap={true}
                  _gap="10px"
                  _type="stack"
                  footerPadding="4px 12px"
                  headerPadding="4px 12px"
                  margin="0"
                  padding="0"
                  showBody={true}
                  showBorder={false}
                  style={{
                    ordered: [{ background: "rgba(255, 255, 255, 0)" }],
                  }}
                >
                  <View id="c9c98" viewKey="View 1">
                    <Container
                      id="group53"
                      footerPadding="4px 12px"
                      headerPadding="4px 12px"
                      margin="0"
                      padding="0"
                      showBody={true}
                      showBorder={false}
                      style={{
                        ordered: [{ background: "rgba(255, 255, 255, 0)" }],
                      }}
                    >
                      <View id="c9c98" viewKey="View 1">
                        <Container
                          id="group50"
                          _flexWrap={true}
                          _gap="0px"
                          footerPadding="4px 12px"
                          headerPadding="4px 12px"
                          margin="0"
                          padding="0"
                          showBody={true}
                          showBorder={false}
                          style={{
                            ordered: [{ background: "rgba(255, 255, 255, 0)" }],
                          }}
                        >
                          <View id="c9c98" viewKey="View 1">
                            <Text
                              id="text39"
                              value="**Transações Banco**"
                              verticalAlign="center"
                            />
                            <Text
                              id="text40"
                              value="**Transações Book**"
                              verticalAlign="center"
                            />
                            <Table
                              id="tableBank2"
                              cellSelection="none"
                              clearChangesetOnSave={true}
                              data="{{ BankTransactions_get2.data }}"
                              defaultFilters={{
                                0: {
                                  ordered: [
                                    { id: "2f325" },
                                    { columnId: "ed9f5" },
                                    { operator: "isAfter" },
                                    {
                                      value: "{{ dateRangeBank2.value.start }}",
                                    },
                                    { disabled: false },
                                  ],
                                },
                                1: {
                                  ordered: [
                                    { id: "542f5" },
                                    { columnId: "ed9f5" },
                                    { operator: "isBefore" },
                                    { value: "{{ dateRangeBank2.value.end }}" },
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
                                    { value: "{{ minBankAmount2.value }}" },
                                    { disabled: false },
                                  ],
                                },
                                5: {
                                  ordered: [
                                    { id: "16626" },
                                    { columnId: "2478a" },
                                    { operator: "<=" },
                                    { value: "{{ maxBankAmount2.value }}" },
                                    { disabled: false },
                                  ],
                                },
                              }}
                              defaultSelectedRow={{
                                mode: "index",
                                indexType: "display",
                                index: 0,
                              }}
                              emptyMessage="No rows found"
                              enableSaveActions={true}
                              linkedFilterId=""
                              rowSelection="{{ toggleAllowRowSelection2.value ? 'multiple' : 'none' }}"
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
                                formatOptions={{
                                  showSeparators: true,
                                  notation: "standard",
                                }}
                                groupAggregationMode="sum"
                                key="id"
                                label="ID"
                                placeholder="Enter value"
                                position="center"
                                size={49.09375}
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
                                size={325}
                                summaryAggregationMode="none"
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
                                size={93.15625}
                                summaryAggregationMode="none"
                                valueOverride="{{
  BankAccount_get2.data.find(
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
  Entity_get2.data.find(
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
                                id="1bf1d"
                                alignment="left"
                                format="string"
                                groupAggregationMode="none"
                                key="transaction_type"
                                label="Transaction type"
                                placeholder="Enter value"
                                position="center"
                                size={100}
                                summaryAggregationMode="none"
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
                                  pluginId="tableBank2"
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
                                  pluginId="tableBank2"
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
                                      src: '//tableBook.clearSelection();\n//Transactions_get3.trigger();\n\n(() => {\n  const bankRows = tableBank2.selectedRow.data;\n  const bookRows = tableBook2.selectedRow.data;\n\n  if (!bankRows || !bookRows) {\n    return { error: "Please select records in both tables." };\n  }\n\n  const toArray = val => Array.isArray(val) ? val : [val];\n\n  const bankCombo = toArray(bankRows);\n  const bookCombo = toArray(bookRows);\n\n  const bank_transaction_details = bankCombo.map(tx => ({\n    id: tx.id,\n    date: tx.date,\n    amount: tx.amount,\n    description: tx.memo,\n    bank_account: tx.bank_account\n      ? {\n          id: tx.bank_account.id,\n          name: tx.bank_account.name,\n        }\n      : null,\n    entity: tx.entity ? tx.entity.id : null,\n    currency: tx.currency?.id || null,\n  }));\n\n  const journal_entry_details = bookCombo.map(entry => ({\n    id: entry.id,\n    date: entry.transaction?.date,\n    amount: entry.amount,\n    description: entry.transaction?.description,\n    account: entry.account\n      ? {\n          id: entry.account.id,\n          account_code: entry.account.account_code,\n          name: entry.account.name,\n        }\n      : null,\n    entity: entry.entity\n      ? {\n          id: entry.entity.id,\n          name: entry.entity.name,\n        }\n      : null,\n    transaction: entry.transaction\n      ? {\n          id: entry.transaction.id,\n          description: entry.transaction.description,\n          date: entry.transaction.date,\n        }\n      : null,\n  }));\n\n  const sum = arr => arr.reduce((acc, val) => acc + Number(val.amount || 0), 0);\n  const sum_bank = sum(bankCombo);\n  const sum_book = sum(bookCombo);\n  const difference = sum_bank - sum_book;\n\n  const avgDateDiff = (() => {\n    const diffs = [];\n    bankCombo.forEach(tx => {\n      bookCombo.forEach(entry => {\n        const date1 = new Date(tx.date);\n        const date2 = new Date(entry.transaction?.date);\n        if (!isNaN(date1) && !isNaN(date2)) {\n          const diff = Math.abs((date1 - date2) / (1000 * 3600 * 24));\n          diffs.push(diff);\n        }\n      });\n    });\n    if (diffs.length === 0) return 0;\n    return diffs.reduce((a, b) => a + b, 0) / diffs.length;\n  })();\n\n  const bank_summary = bankCombo\n    .map(tx => `ID: ${tx.id}, Date: ${tx.date}, Amount: ${tx.amount}, Desc: ${tx.description}`)\n    .join("\\n");\n\n  const journal_summary = bookCombo\n    .map(entry => {\n      const acct = entry.account || {};\n      const direction = entry.debit_amount ? "DEBIT" : "CREDIT";\n      const amount = Number(entry.debit_amount || entry.credit_amount || 0);\n      return `ID: ${entry.transaction?.id}, Date: ${entry.transaction?.date}, JE: ${direction} ${amount} - (${acct.account_code}) ${acct.name}, Desc: ${entry.transaction?.description}`;\n    })\n    .join("\\n");\n\n  return {\n    match_type: "manual",\n    bank_transaction_details,\n    journal_entry_details,\n    bank_transaction_summary: bank_summary,\n    journal_entries_summary: journal_summary,\n    bank_ids: bankCombo.map(tx => tx.id),\n    journal_entries_ids: bookCombo.map(entry => entry.id),\n    sum_bank,\n    sum_book,\n    difference,\n    avg_date_diff: avgDateDiff,\n    confidence_score: 0.95 // arbitrary, since user selects manually\n  };\n})();\n',
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
                                pluginId="VisibleBankIds2"
                                type="datasource"
                                waitMs="0"
                                waitType="debounce"
                              />
                            </Table>
                            <Table
                              id="tableBook2"
                              cellSelection="none"
                              clearChangesetOnSave={true}
                              data="{{ Transactions_get5.data }}"
                              defaultFilters={{
                                0: {
                                  ordered: [
                                    { id: "09a54" },
                                    { columnId: "ed9f5" },
                                    { operator: "isAfter" },
                                    {
                                      value: "{{ dateRangeBook2.value.start }}",
                                    },
                                    { disabled: false },
                                  ],
                                },
                                1: {
                                  ordered: [
                                    { id: "f23c6" },
                                    { columnId: "ed9f5" },
                                    { operator: "isBefore" },
                                    { value: "{{ dateRangeBook2.value.end }}" },
                                    { disabled: false },
                                  ],
                                },
                                2: {
                                  ordered: [
                                    { id: "ba54f" },
                                    { columnId: "0b2a2" },
                                    { operator: "isNot" },
                                    { value: "Matched" },
                                    { disabled: false },
                                  ],
                                },
                                3: {
                                  id: "72ee1",
                                  columnId: "2478a",
                                  operator: ">=",
                                  value: "{{  minBookAmount2.value}}",
                                  disabled: false,
                                },
                                4: {
                                  id: "fe7f2",
                                  columnId: "2478a",
                                  operator: "<=",
                                  value: "{{ maxBookAmount2.value }}",
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
                              rowSelection="{{ toggleAllowRowSelection2.value ? 'multiple' : 'none' }}"
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
                                formatOptions={{
                                  showSeparators: true,
                                  notation: "standard",
                                }}
                                groupAggregationMode="sum"
                                key="id"
                                label="ID"
                                placeholder="Enter value"
                                position="center"
                                size={63.765625}
                                summaryAggregationMode="none"
                              />
                              <Column
                                id="eb692"
                                alignment="left"
                                cellTooltipMode="overflow"
                                editableOptions={{ showStepper: true }}
                                format="tags"
                                formatOptions={{ automaticColors: true }}
                                groupAggregationMode="sum"
                                key="journal_entries_bank_accounts"
                                label="Bank Accounts"
                                placeholder="Select options"
                                position="center"
                                size={117.65625}
                                summaryAggregationMode="none"
                                valueOverride="{{
  Array.isArray(currentSourceRow.journal_entries_bank_accounts)
    ? currentSourceRow.journal_entries_bank_accounts.map(id =>
        BankAccount_get2.data.find(acc => acc.id === id)?.name || `ID: ${id}`
      )
    : [BankAccount_get2.data.find(acc => acc.id === currentSourceRow.journal_entries_bank_accounts)?.name || `ID: ${currentSourceRow.journal_entries_bank_accounts}`]
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
                                size={106.65625}
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
                                size={94.03125}
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
                                size={184.578125}
                                summaryAggregationMode="none"
                              />
                              <Column
                                id="04b19"
                                alignment="left"
                                format="tag"
                                formatOptions={{ automaticColors: true }}
                                groupAggregationMode="none"
                                key="state"
                                label="State"
                                placeholder="Select option"
                                position="center"
                                size={77.046875}
                                summaryAggregationMode="none"
                                valueOverride="{{ _.startCase(item) }}"
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
                                size={104.875}
                                summaryAggregationMode="none"
                                valueOverride="{{ item === 0  ? 'balanced' : (abs(item) <10 ? '<10' : '>10') }}"
                              />
                              <Column
                                id="fe9c2"
                                alignment="right"
                                editableOptions={{ showStepper: true }}
                                format="decimal"
                                formatOptions={{
                                  showSeparators: true,
                                  notation: "standard",
                                }}
                                groupAggregationMode="sum"
                                key="journal_entries_count"
                                label="Journal entries count"
                                placeholder="Enter value"
                                position="center"
                                size={135.640625}
                                summaryAggregationMode="none"
                              />
                              <Column
                                id="0219b"
                                alignment="left"
                                cellTooltipMode="overflow"
                                format="multilineString"
                                groupAggregationMode="none"
                                key="journal_entries_summary"
                                label="Summary"
                                placeholder="Enter value"
                                position="center"
                                size={592.578125}
                                summaryAggregationMode="none"
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
                                size={133.234375}
                                summaryAggregationMode="none"
                                valueOverride="{{ _.startCase(item) }}"
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
                                  pluginId="tableBook2"
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
                                  pluginId="tableBook2"
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
                                pluginId="VisibleBookIds2"
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
                      id="group54"
                      footerPadding="4px 12px"
                      headerPadding="4px 12px"
                      margin="0"
                      padding="0"
                      showBody={true}
                      showBorder={false}
                      style={{
                        ordered: [{ background: "rgba(255, 255, 255, 0)" }],
                      }}
                    >
                      <View id="c9c98" viewKey="View 1">
                        <ButtonGroup2
                          id="buttonGroup5"
                          alignment="right"
                          overflowPosition={5}
                        >
                          <ButtonGroup2-Button
                            id="aac52"
                            styleVariant="outline"
                            text="1-to-1"
                          >
                            <Event
                              event="click"
                              method="run"
                              params={{
                                map: {
                                  src: '// Step 1: Get displayed rows from tableBook\nconst visibleBooks = await tableBook2.getDisplayedData();\nconst bookRows = Array.isArray(visibleBooks) ? visibleBooks : Object.values(visibleBooks);\nconst bookIds = bookRows.map(row => row.id);\n\n// Step 2: Get displayed rows from tableBank\nconst visibleBanks = await tableBank2.getDisplayedData();\nconst bankRows = Array.isArray(visibleBanks) ? visibleBanks : Object.values(visibleBanks);\nconst bankIds = bankRows.map(row => row.id);\n\n// Step 3: Build the payload object\nconst payload = {\n  bank_ids: bankIds,\n  book_ids: bookIds,\n  //enforce_same_bank: switchSameBank.value,\n  //enforce_same_entity: switchSameEntity.value,\n  //max_bank_entries: BankToCombine.value,\n  //max_book_entries: BookToCombine.value,\n  //amount_tolerance: AmountTolerance.value,\n  max_group_size: 10,\n  amount_tolerance: 0,\n  date_tolerance_days: DateTolerance2.value,\n  min_confidence: MinConfidence2.value,\n  //max_suggestions: MaxSuggestions.value,\n  weight_date: 0.4,\n  weight_amount: 0.6,\n  strategy: "optimized"\n};\n\nconsole.log("Generated payload:", payload);\n\n// Step 4: Trigger the Transactions_get3 query with the payload\nTransactions_get7.trigger({\n  additionalScope: {\n    payload: payload\n  }\n});\n',
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
                            styleVariant="solid"
                            text="Propor Conciliação"
                          >
                            <Event
                              event="click"
                              method="run"
                              params={{
                                map: {
                                  src: "// Trigger two queries simultaneously, then trigger the third one after completion\nPromise.all([\n  VisibleBankIds2.trigger(),\n  VisibleBookIds2.trigger()\n]).then(([result1, result2]) => {\n  // You can access results here if needed:\n  console.log(result1, result2);\n\n  // Trigger the third query after both complete\n  Transactions_get7.trigger();\n}).catch(error => {\n  // Handle errors if either query fails\n  console.error('One of the queries failed:', error);\n});",
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
                              pluginId="modalManualConciliation2"
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
                                    src: '// ✅ Retrieve and normalize raw data\nlet rawData = ReconciliationMatches2.value;\nconsole.log("Raw data:", rawData);\n\n// 2. Normalize to array\nlet allMatches = [];\nif (rawData?.suggestions && Array.isArray(rawData.suggestions)) {\n  allMatches = rawData.suggestions;\n} else if (Array.isArray(rawData)) {\n  allMatches = rawData;\n} else {\n  try {\n    allMatches = JSON.parse(rawData);\n  } catch (e) {\n    console.error("Failed to parse rawData:", e);\n    allMatches = [];\n  }\n}\n\n// ✅ STEP 3: Filter 100% confidence matches\nconst filteredMatches = allMatches.filter(match => match.confidence_score === 1);\n\n// ✅ STEP 4: Count frequency of bank_ids\nconst bankIdFrequency = {};\nfilteredMatches.forEach(match => {\n  match.bank_ids.forEach(id => {\n    bankIdFrequency[id] = (bankIdFrequency[id] || 0) + 1;\n  });\n});\n\n// ✅ STEP 5: Keep only unique bank_ids matches\nconst uniqueMatches = filteredMatches.filter(match =>\n  match.bank_ids.every(id => bankIdFrequency[id] === 1)\n);\n\nconsole.log("Unique Matches:", uniqueMatches);\n\n// ✅ STEP 6: Build payload\nconst transformedItem = {\n  matches: uniqueMatches.map(match => ({\n    bank_transaction_ids: match.bank_ids,\n    journal_entry_ids: match.journal_entries_ids,\n  })),\n  adjustment_side: "bank",\n  reference: "Reconciliation batch 1",\n  notes: "Matched using high confidence scores",\n};\n\nconsole.log("Transformed Payload:", transformedItem);\n\n// ✅ STEP 7: Trigger POST + Handle response\nif (transformedItem.matches.length > 0) {\n  MatchRecords_post2.trigger({\n    additionalScope: {\n      content: transformedItem,\n    },\n    onSuccess: () => {\n      // Remove matched items from ReconciliationMatches\n      const matchedIds = new Set(uniqueMatches.map(m => m.id));\n      ReconciliationMatches2.setValue(\n        ReconciliationMatches2.value.filter(item => !matchedIds.has(item.id))\n      );\n\n      console.log(`✅ ${uniqueMatches.length} matches applied and removed.`);\n    },\n    onFailure: (error) => {\n      console.error("❌ Failed to apply matches:", error);\n    }\n  });\n} else {\n  console.log("⚠️ No unique matches to apply.");\n}',
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
                        <Table
                          id="table44"
                          actionsOverflowPosition={1}
                          cellSelection="none"
                          clearChangesetOnSave={true}
                          data="{{ ReconciliationMatches2.value }}"
                          defaultSelectedRow={{
                            mode: "index",
                            indexType: "display",
                            index: 0,
                          }}
                          emptyMessage="No rows found"
                          enableExpandableRows={true}
                          enableSaveActions={true}
                          rowHeight="medium"
                          rowSelection="multiple"
                          showBorder={true}
                          showFooter={true}
                          showHeader={true}
                          style={{ headerBackground: "canvas" }}
                          toolbarPosition="bottom"
                        >
                          <Include src="./table44ExpandedRow.rsx" />
                          <Column
                            id="a9a83"
                            alignment="left"
                            format="string"
                            groupAggregationMode="none"
                            key="match_type"
                            label="Match type"
                            placeholder="Enter value"
                            position="center"
                            size={84.484375}
                            summaryAggregationMode="none"
                          />
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
                            size={54.75}
                            summaryAggregationMode="none"
                          />
                          <Column
                            id="bb1f9"
                            alignment="left"
                            cellTooltipMode="overflow"
                            format="string"
                            groupAggregationMode="none"
                            key="bank_transaction_summary"
                            label="Bank transaction summary"
                            placeholder="Enter value"
                            position="center"
                            size={359.984375}
                            summaryAggregationMode="none"
                          />
                          <Column
                            id="707ba"
                            alignment="left"
                            cellTooltipMode="overflow"
                            format="multilineString"
                            groupAggregationMode="none"
                            key="journal_entries_summary"
                            label="Journal entries summary"
                            placeholder="Enter value"
                            position="center"
                            size={407.984375}
                            summaryAggregationMode="none"
                          />
                          <Column
                            id="73bb6"
                            alignment="right"
                            editableOptions={{ showStepper: true }}
                            format="decimal"
                            formatOptions={{
                              showSeparators: true,
                              notation: "standard",
                            }}
                            groupAggregationMode="sum"
                            key="sum_bank"
                            label="Sum bank"
                            placeholder="Enter value"
                            position="center"
                            size={97.1875}
                            summaryAggregationMode="none"
                          />
                          <Column
                            id="0a639"
                            alignment="right"
                            editableOptions={{ showStepper: true }}
                            format="decimal"
                            formatOptions={{
                              showSeparators: true,
                              notation: "standard",
                            }}
                            groupAggregationMode="sum"
                            key="sum_book"
                            label="Sum book"
                            placeholder="Enter value"
                            position="center"
                            size={91.703125}
                            summaryAggregationMode="none"
                          />
                          <Column
                            id="ef0cb"
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
                            size={133.78125}
                            summaryAggregationMode="none"
                          />
                          <Column
                            id="07008"
                            alignment="right"
                            editableOptions={{ showStepper: true }}
                            format="decimal"
                            formatOptions={{
                              showSeparators: true,
                              notation: "standard",
                            }}
                            groupAggregationMode="sum"
                            key="avg_date_diff"
                            label="Avg date diff"
                            placeholder="Enter value"
                            position="center"
                            size={88.234375}
                            summaryAggregationMode="none"
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
                                    src: 'const selectedRows = table44.selectedSourceRows?.length > 0 \n  ? table44.selectedSourceRows \n  : [currentSourceRow]; // fallback\n\n// Build the matches array\nconst transformedItem = {\n  matches: selectedRows.map(row => ({\n    bank_transaction_ids: row.bank_ids,\n    journal_entry_ids: row.journal_entries_ids\n  })),\n  adjustment_side: "bank",\n  reference: "Reconciliation batch 1",\n  notes: "Matched using high confidence scores"\n};\n\n// Flatten all selected bank and book IDs\nconst allSelectedBankIds = new Set(\n  selectedRows.flatMap(row => row.bank_ids || [])\n);\nconst allSelectedBookIds = new Set(\n  selectedRows.flatMap(row => row.journal_entries_ids || [])\n);\n\n// Trigger the API\nMatchRecords_post2.trigger({\n  additionalScope: {\n    content: transformedItem\n  },\n  onSuccess: () => {\n    // Remove matches that include ANY of the selected bank or book IDs\n    const updatedMatches = ReconciliationMatches2.value.filter(item => {\n      const bankOverlap = item.bank_ids?.some(id => allSelectedBankIds.has(id));\n      const bookOverlap = item.journal_entries_ids?.some(id => allSelectedBookIds.has(id));\n      return !bankOverlap && !bookOverlap;\n    });\n\n    ReconciliationMatches2.setValue(updatedMatches);\n    table44.clearSelection();\n\n    utils.showNotification({\n      title: "Matches submitted successfully",\n      intent: "success"\n    });\n  }\n});',
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
                              pluginId="Conciliation_get2"
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
                              pluginId="table44"
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
                              pluginId="table44"
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
                <Divider id="divider17" />
              </View>
            </Container>
            <Container
              id="container21"
              footerPadding="4px 12px"
              headerPadding="4px 12px"
              heightType="fixed"
              hidden="{{ !toggleShowParametros2.value }}"
              padding="12px"
              showBody={true}
            >
              <Header>
                <Text
                  id="containerTitle21"
                  value="###### Parâmetros Conciliação"
                  verticalAlign="center"
                />
              </Header>
              <View id="c9c98" viewKey="View 1">
                <ButtonGroup2
                  id="buttonGroup4"
                  alignment="right"
                  overflowPosition={1}
                >
                  <ButtonGroup2-Button
                    id="75d90"
                    styleVariant="solid"
                    text="Aplicar"
                  >
                    <Event
                      event="click"
                      method="trigger"
                      params={{ ordered: [] }}
                      pluginId="Transactions_get7"
                      type="datasource"
                      waitMs="0"
                      waitType="debounce"
                    />
                  </ButtonGroup2-Button>
                </ButtonGroup2>
                <Container
                  id="group64"
                  _direction="vertical"
                  _gap="0px"
                  _type="stack"
                  footerPadding="4px 12px"
                  headerPadding="4px 12px"
                  margin="0"
                  padding="0"
                  showBody={true}
                  showBorder={false}
                  style={{
                    ordered: [{ background: "rgba(255, 255, 255, 0)" }],
                  }}
                >
                  <View id="27d6c" viewKey="View 1">
                    <Include src="./collapsibleContainer16.rsx" />
                    <Include src="./collapsibleContainer17.rsx" />
                    <Include src="./collapsibleContainer18.rsx" />
                  </View>
                </Container>
              </View>
            </Container>
          </View>
        </Container>
      </View>
    </Container>
    <Module
      id="formBanks2"
      hidden="true"
      inputs="{{manageBanks3.value}}"
      name="FormBanks"
      pageUuid="b8706d74-e3ca-11ef-a1b9-df1c36976901"
    />
    <Module
      id="formBankAccounts2"
      hidden="true"
      inputs="{{ manageBankAccounts2.value }}"
      name="FormBankAccounts"
      pageUuid="c0b6635e-e4aa-11ef-8cfc-4374d6f8d1fc"
    />
    <Module
      id="manageBanks2"
      heightType="fixed"
      hidden="true"
      inputs=""
      name="manageBanks"
      pageUuid="40726b9a-e33b-11ef-815e-577d6b26a3b7"
    />
    <JSONEditor
      id="BankReconciliationParameters3"
      hidden="true"
      value={
        '{\n            "bank_ids": {{ tableBank2.displayedData.map(row => row.id) }},\n            "book_filters": {},\n            "enforce_same_bank": {{  switchSameBank2.value }}, \n            "enforce_same_entity": {{  switchSameEntity2.value }},\n            "max_bank_entries": {{ BankToCombine2.value }},\n            "max_book_entries": {{ BookToCombine2.value }},\n            "amount_tolerance": {{AmountTolerance2.value}},\n            "date_tolerance_days": {{ DateTolerance2.value }},\n            "min_confidence": {{ MinConfidence2.value }},\n            "max_suggestions": {{ MaxSuggestions2.value }},\n            "weight_date": 0.4,\n            "weight_amount": 0.6\n        }'
      }
    />
    <JSONEditor
      id="BankReconciliationParameters4"
      hidden="true"
      value="{{  ReconciliationParameters2.value }}"
    />
    <Table
      id="table47"
      actionsOverflowPosition={1}
      cellSelection="none"
      clearChangesetOnSave={true}
      data="{{ Conciliation_get2.data }}"
      defaultSelectedRow={{ mode: "index", indexType: "display", index: 0 }}
      emptyMessage="No rows found"
      enableSaveActions={true}
      primaryKeyColumnId="b56db"
      rowSelection="multiple"
      showBorder={true}
      showFooter={true}
      showHeader={true}
      toolbarPosition="bottom"
    >
      <Column
        id="b56db"
        alignment="right"
        editableOptions={{ showStepper: true }}
        format="decimal"
        formatOptions={{ showSeparators: true, notation: "standard" }}
        groupAggregationMode="sum"
        key="id"
        label="ID"
        placeholder="Enter value"
        position="center"
        size={100}
        summaryAggregationMode="none"
      />
      <Column
        id="12448"
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
        id="3b860"
        alignment="left"
        cellTooltipMode="overflow"
        format="tags"
        formatOptions={{ automaticColors: true }}
        groupAggregationMode="none"
        key="bank_transactions"
        label="Bank transactions"
        placeholder="Select options"
        position="center"
        size={115}
        summaryAggregationMode="none"
      />
      <Column
        id="3d76e"
        alignment="left"
        cellTooltipMode="overflow"
        format="tags"
        formatOptions={{ automaticColors: true }}
        groupAggregationMode="none"
        key="journal_entries"
        label="Journal entries"
        placeholder="Select options"
        position="center"
        size={169}
        summaryAggregationMode="none"
      />
      <Column
        id="904ee"
        alignment="left"
        format="string"
        groupAggregationMode="none"
        key="status"
        label="Status"
        placeholder="Enter value"
        position="center"
        size={100}
        summaryAggregationMode="none"
      />
      <Column
        id="ba1be"
        alignment="left"
        format="string"
        groupAggregationMode="none"
        key="reference"
        label="Reference"
        placeholder="Enter value"
        position="center"
        size={167.46875}
        summaryAggregationMode="none"
      />
      <Column
        id="85de8"
        alignment="left"
        cellTooltipMode="overflow"
        format="multilineString"
        groupAggregationMode="none"
        key="notes"
        label="Notes"
        placeholder="Enter value"
        position="center"
        size={588}
        summaryAggregationMode="none"
      />
      <Column
        id="c41b4"
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
        id="0d09c"
        alignment="left"
        format="string"
        groupAggregationMode="none"
        key="created_at"
        label="Created at"
        placeholder="Enter value"
        position="center"
        size={219}
        summaryAggregationMode="none"
      />
      <Column
        id="f4ff9"
        alignment="left"
        format="string"
        groupAggregationMode="none"
        key="created_by"
        label="Created by"
        placeholder="Enter value"
        position="center"
        size={100}
        summaryAggregationMode="none"
      />
      <Action
        id="481f6"
        icon="bold/interface-delete-bin-put-back-1"
        label="Delete"
      >
        <Event
          event="clickAction"
          method="setValue"
          params={{ map: { value: "{{ currentSourceRow }}" } }}
          pluginId="Conciliation_selected2"
          type="state"
          waitMs="0"
          waitType="debounce"
        />
        <Event
          enabled=""
          event="clickAction"
          method="trigger"
          params={{}}
          pluginId="Conciliation_delete2"
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
          pluginId="table47"
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
          pluginId="table47"
          type="widget"
          waitMs="0"
          waitType="debounce"
        />
      </ToolbarButton>
    </Table>
  </Frame>
</Screen>
