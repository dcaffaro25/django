<Screen
  id="cadastroContabilidade"
  _customShortcuts={[]}
  _hashParams={[]}
  _searchParams={[]}
  browserTitle=""
  title="Cadastro Contabilidade"
  urlSlug="cadastro"
  uuid="80092de2-ed49-4973-86d1-ac030909129c"
>
  <State id="entity_selected" />
  <State id="entity_mode" />
  <RESTQuery
    id="entities_get"
    isHidden={false}
    isMultiplayerEdited={false}
    query="{{ tenant_subdomain.value }}/api/entities-mini/"
    queryTimeout="100000"
    resourceDisplayName="Tenant Specific - Production"
    resourceName="db4d0175-aa88-429c-ba3f-f4bbd2c875e3"
    resourceTypeOverride=""
  />
  <RESTQuery
    id="entity_context_get"
    isHidden={false}
    isMultiplayerEdited={false}
    query="/{{ tenant_subdomain.value }}/api/entities/{{ entity_selected.value.id }} /context-options/"
    queryDisabled={
      '{{ entity_selected.value === null || entity_selected.value === "" }}'
    }
    resourceDisplayName="Tenant Specific - Production"
    resourceName="db4d0175-aa88-429c-ba3f-f4bbd2c875e3"
    resourceTypeOverride=""
  />
  <RESTQuery
    id="entity_edit"
    body="{{ EntityForm.data }}"
    bodyType="raw"
    cookies={'[{"key":"","value":""}]'}
    headers={'[{"key":"Content-Type","value":"application/json"}]'}
    isHidden={false}
    isMultiplayerEdited={false}
    query="/{{ tenant_subdomain.value }}/api/entities/{{ 
entity_selected.value.id }}/"
    resourceDisplayName="Tenant Specific - Production"
    resourceName="db4d0175-aa88-429c-ba3f-f4bbd2c875e3"
    resourceTypeOverride=""
    runWhenModelUpdates={false}
    type="PUT"
  >
    <Event
      event="success"
      method="trigger"
      params={{}}
      pluginId="entities_get"
      type="datasource"
      waitMs="0"
      waitType="debounce"
    />
    <Event
      event="success"
      method="setValue"
      params={{ map: { value: '""' } }}
      pluginId="entity_selected"
      type="state"
      waitMs="0"
      waitType="debounce"
    />
    <Event
      event="success"
      method="hide"
      params={{}}
      pluginId="modalEntidade"
      type="widget"
      waitMs="0"
      waitType="debounce"
    />
  </RESTQuery>
  <RESTQuery
    id="entity_new"
    body="{{ EntityForm.data }}"
    bodyType="raw"
    cookies={'[{"key":"","value":""}]'}
    headers={'[{"key":"Content-Type","value":"application/json"}]'}
    isHidden={false}
    isMultiplayerEdited={false}
    query="/{{ tenant_subdomain.value }}/api/entities/?"
    resourceDisplayName="Tenant Specific - Production"
    resourceName="db4d0175-aa88-429c-ba3f-f4bbd2c875e3"
    resourceTypeOverride=""
    runWhenModelUpdates={false}
    type="POST"
  >
    <Event
      event="success"
      method="trigger"
      params={{}}
      pluginId="entities_get"
      type="datasource"
      waitMs="0"
      waitType="debounce"
    />
    <Event
      event="success"
      method="setValue"
      params={{ map: { value: '""' } }}
      pluginId="entity_selected"
      type="state"
      waitMs="0"
      waitType="debounce"
    />
    <Event
      event="success"
      method="hide"
      params={{}}
      pluginId="modalEntidade"
      type="widget"
      waitMs="0"
      waitType="debounce"
    />
  </RESTQuery>
  <State id="account_selected" />
  <State id="account_mode" />
  <RESTQuery
    id="account_get"
    isHidden={false}
    isMultiplayerEdited={false}
    query="/{{ tenant_subdomain.value }}/api/accounts/?"
    queryTimeout="100000"
    resourceDisplayName="Tenant Specific - Production"
    resourceName="db4d0175-aa88-429c-ba3f-f4bbd2c875e3"
    resourceTypeOverride=""
  />
  <RESTQuery
    id="account_new"
    body="{{ AccountForm.data }}"
    bodyType="raw"
    cookies={'[{"key":"","value":""}]'}
    headers={'[{"key":"Content-Type","value":"application/json"}]'}
    isHidden={false}
    isMultiplayerEdited={false}
    query="/{{ tenant_subdomain.value }}/api/accounts/?"
    resourceDisplayName="Tenant Specific - Production"
    resourceName="db4d0175-aa88-429c-ba3f-f4bbd2c875e3"
    resourceTypeOverride=""
    runWhenModelUpdates={false}
    type="POST"
  >
    <Event
      event="success"
      method="trigger"
      params={{}}
      pluginId="account_get"
      type="datasource"
      waitMs="0"
      waitType="debounce"
    />
    <Event
      event="success"
      method="setValue"
      params={{ map: { value: '""' } }}
      pluginId="account_selected"
      type="state"
      waitMs="0"
      waitType="debounce"
    />
    <Event
      event="success"
      method="hide"
      params={{}}
      pluginId="modalAccount"
      type="widget"
      waitMs="0"
      waitType="debounce"
    />
  </RESTQuery>
  <RESTQuery
    id="account_edit"
    body="{{ AccountForm.data }}"
    bodyType="raw"
    cookies={'[{"key":"","value":""}]'}
    headers={'[{"key":"Content-Type","value":"application/json"}]'}
    isHidden={false}
    isMultiplayerEdited={false}
    query="/{{ tenant_subdomain.value }}/api/accounts/{{ 
account_selected.value.id }}/"
    resourceDisplayName="Tenant Specific - Production"
    resourceName="db4d0175-aa88-429c-ba3f-f4bbd2c875e3"
    resourceTypeOverride=""
    runWhenModelUpdates={false}
    type="PUT"
  >
    <Event
      event="success"
      method="trigger"
      params={{}}
      pluginId="account_get"
      type="datasource"
      waitMs="0"
      waitType="debounce"
    />
    <Event
      event="success"
      method="setValue"
      params={{ map: { value: '""' } }}
      pluginId="account_selected"
      type="state"
      waitMs="0"
      waitType="debounce"
    />
    <Event
      event="success"
      method="hide"
      params={{}}
      pluginId="modalAccount"
      type="widget"
      waitMs="0"
      waitType="debounce"
    />
  </RESTQuery>
  <State id="costcenter_selected" />
  <State id="costcenter_mode" value="" />
  <RESTQuery
    id="costcenter_get"
    isHidden={false}
    isMultiplayerEdited={false}
    query="/{{ tenant_subdomain.value }}/api/cost_centers/"
    resourceDisplayName="Tenant Specific - Production"
    resourceName="db4d0175-aa88-429c-ba3f-f4bbd2c875e3"
    resourceTypeOverride=""
  />
  <RESTQuery
    id="costcenter_new"
    body="{{ CostCenterForm.data }}"
    bodyType="raw"
    cookies={'[{"key":"","value":""}]'}
    headers={'[{"key":"Content-Type","value":"application/json"}]'}
    isHidden={false}
    isMultiplayerEdited={false}
    query="/{{ tenant_subdomain.value }}/api/cost_centers/?"
    resourceDisplayName="Tenant Specific - Production"
    resourceName="db4d0175-aa88-429c-ba3f-f4bbd2c875e3"
    resourceTypeOverride=""
    runWhenModelUpdates={false}
    type="POST"
  >
    <Event
      event="success"
      method="trigger"
      params={{}}
      pluginId="costcenter_get"
      type="datasource"
      waitMs="0"
      waitType="debounce"
    />
    <Event
      event="success"
      method="setValue"
      params={{ map: { value: '""' } }}
      pluginId="costcenter_selected"
      type="state"
      waitMs="0"
      waitType="debounce"
    />
    <Event
      event="success"
      method="hide"
      params={{}}
      pluginId="modalCostCenter"
      type="widget"
      waitMs="0"
      waitType="debounce"
    />
  </RESTQuery>
  <RESTQuery
    id="costcenter_edit"
    body="{{  CostCenterForm.data }}"
    bodyType="raw"
    cookies={'[{"key":"","value":""}]'}
    headers={'[{"key":"Content-Type","value":"application/json"}]'}
    isHidden={false}
    isMultiplayerEdited={false}
    query="/{{ tenant_subdomain.value }}/api/cost_centers/{{ 
costcenter_selected.value.id }}/"
    resourceDisplayName="Tenant Specific - Production"
    resourceName="db4d0175-aa88-429c-ba3f-f4bbd2c875e3"
    resourceTypeOverride=""
    runWhenModelUpdates={false}
    type="PUT"
  >
    <Event
      event="success"
      method="trigger"
      params={{}}
      pluginId="costcenter_get"
      type="datasource"
      waitMs="0"
      waitType="debounce"
    />
    <Event
      event="success"
      method="hide"
      params={{}}
      pluginId="modalCostCenter"
      type="widget"
      waitMs="0"
      waitType="debounce"
    />
    <Event
      event="success"
      method="setValue"
      params={{ map: { value: "null" } }}
      pluginId="costcenter_selected"
      type="state"
      waitMs="0"
      waitType="debounce"
    />
  </RESTQuery>
  <State id="bankaccount_selected" />
  <State id="bankaccount_mode" />
  <RESTQuery
    id="bankaccount_get"
    isHidden={false}
    isMultiplayerEdited={false}
    query="/{{ tenant_subdomain.value }}/api/bank_accounts/?"
    resourceDisplayName="Tenant Specific - Production"
    resourceName="db4d0175-aa88-429c-ba3f-f4bbd2c875e3"
    resourceTypeOverride=""
  />
  <RESTQuery
    id="bankaccount_edit"
    body="{{  BankAccountForm.data }}"
    bodyType="raw"
    cookies={'[{"key":"","value":""}]'}
    headers={'[{"key":"Content-Type","value":"application/json"}]'}
    isHidden={false}
    isMultiplayerEdited={false}
    query="/{{ tenant_subdomain.value }}/api/bank_accounts/{{ 
bankaccount_selected.value.id }}/"
    resourceDisplayName="Tenant Specific - Production"
    resourceName="db4d0175-aa88-429c-ba3f-f4bbd2c875e3"
    resourceTypeOverride=""
    runWhenModelUpdates={false}
    type="PUT"
  >
    <Event
      event="success"
      method="trigger"
      params={{}}
      pluginId="bankaccount_get"
      type="datasource"
      waitMs="0"
      waitType="debounce"
    />
    <Event
      event="success"
      method="hide"
      params={{}}
      pluginId="modalBankAccount"
      type="widget"
      waitMs="0"
      waitType="debounce"
    />
    <Event
      event="success"
      method="setValue"
      params={{ map: { value: "null" } }}
      pluginId="bankaccount_selected"
      type="state"
      waitMs="0"
      waitType="debounce"
    />
  </RESTQuery>
  <RESTQuery
    id="bankaccount_new"
    body="{{ BankAccountForm.data }}"
    bodyType="raw"
    cookies={'[{"key":"","value":""}]'}
    headers={'[{"key":"Content-Type","value":"application/json"}]'}
    isHidden={false}
    isMultiplayerEdited={false}
    query="/{{ tenant_subdomain.value }}/api/bank_accounts/?"
    resourceDisplayName="Tenant Specific - Production"
    resourceName="db4d0175-aa88-429c-ba3f-f4bbd2c875e3"
    resourceTypeOverride=""
    runWhenModelUpdates={false}
    type="POST"
  >
    <Event
      event="success"
      method="trigger"
      params={{}}
      pluginId="bankaccount_get"
      type="datasource"
      waitMs="0"
      waitType="debounce"
    />
    <Event
      event="success"
      method="setValue"
      params={{ map: { value: '""' } }}
      pluginId="bankaccount_selected"
      type="state"
      waitMs="0"
      waitType="debounce"
    />
    <Event
      event="success"
      method="hide"
      params={{}}
      pluginId="modalBankAccount"
      type="widget"
      waitMs="0"
      waitType="debounce"
    />
  </RESTQuery>
  <State id="bank_selected" />
  <State id="bank_mode" />
  <RESTQuery
    id="bank_get"
    isHidden={false}
    isMultiplayerEdited={false}
    query="/{{ tenant_subdomain.value }}/api/banks/?"
    resourceDisplayName="Tenant Specific - Production"
    resourceName="db4d0175-aa88-429c-ba3f-f4bbd2c875e3"
    resourceTypeOverride=""
  />
  <RESTQuery
    id="bank_edit"
    body="{{  BankForm.data }}"
    bodyType="raw"
    cookies={'[{"key":"","value":""}]'}
    headers={'[{"key":"Content-Type","value":"application/json"}]'}
    isHidden={false}
    isMultiplayerEdited={false}
    query="/{{ tenant_subdomain.value }}/api/banks/{{ 
bank_selected.value.id }}/"
    resourceDisplayName="Tenant Specific - Production"
    resourceName="db4d0175-aa88-429c-ba3f-f4bbd2c875e3"
    resourceTypeOverride=""
    runWhenModelUpdates={false}
    type="PUT"
  >
    <Event
      event="success"
      method="trigger"
      params={{}}
      pluginId="bank_get"
      type="datasource"
      waitMs="0"
      waitType="debounce"
    />
    <Event
      event="success"
      method="hide"
      params={{}}
      pluginId="modalBank"
      type="widget"
      waitMs="0"
      waitType="debounce"
    />
  </RESTQuery>
  <RESTQuery
    id="bank_new"
    body="{{ BankForm.data }}"
    bodyType="raw"
    cookies={'[{"key":"","value":""}]'}
    headers={'[{"key":"Content-Type","value":"application/json"}]'}
    isHidden={false}
    isMultiplayerEdited={false}
    query="/{{ tenant_subdomain.value }}/api/banks/?"
    resourceDisplayName="Tenant Specific - Production"
    resourceName="db4d0175-aa88-429c-ba3f-f4bbd2c875e3"
    resourceTypeOverride=""
    runWhenModelUpdates={false}
    type="POST"
  >
    <Event
      event="success"
      method="trigger"
      params={{}}
      pluginId="bank_get"
      type="datasource"
      waitMs="0"
      waitType="debounce"
    />
    <Event
      event="success"
      method="setValue"
      params={{ map: { value: '""' } }}
      pluginId="bank_selected"
      type="state"
      waitMs="0"
      waitType="debounce"
    />
    <Event
      event="success"
      method="hide"
      params={{}}
      pluginId="modalBank"
      type="widget"
      waitMs="0"
      waitType="debounce"
    />
  </RESTQuery>
  <RESTQuery
    id="bulk_import_preview"
    body="{{ BankForm.data }}"
    bodyType="raw"
    cookies={'[{"key":"","value":""}]'}
    headers={'[{"key":"Content-Type","value":"application/json"}]'}
    isHidden={false}
    isMultiplayerEdited={false}
    query="/{{ tenant_subdomain.value }}/api/banks/?"
    resourceDisplayName="Tenant Specific - Production"
    resourceName="db4d0175-aa88-429c-ba3f-f4bbd2c875e3"
    resourceTypeOverride=""
    runWhenModelUpdates={false}
    type="POST"
  >
    <Event
      event="success"
      method="trigger"
      params={{}}
      pluginId="bank_get"
      type="datasource"
      waitMs="0"
      waitType="debounce"
    />
    <Event
      event="success"
      method="setValue"
      params={{ map: { value: '""' } }}
      pluginId="bank_selected"
      type="state"
      waitMs="0"
      waitType="debounce"
    />
    <Event
      event="success"
      method="hide"
      params={{}}
      pluginId="modalBank"
      type="widget"
      waitMs="0"
      waitType="debounce"
    />
  </RESTQuery>
  <SqlTransformQuery
    id="check_login7"
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
  <Include src="./modalAccount.rsx" />
  <Include src="./modalAccountFS.rsx" />
  <Include src="./modalBank.rsx" />
  <Include src="./modalBankAccount.rsx" />
  <Include src="./modalBankAccountsFS.rsx" />
  <Include src="./modalBankFS.rsx" />
  <Include src="./modalCostCenter.rsx" />
  <Include src="./modalEntidade.rsx" />
  <Include src="./modalEntidadeFC.rsx" />
  <Include src="./modalFrame6.rsx" />
  <Include src="./modalNewPosition2.rsx" />
  <Frame
    id="$main9"
    enableFullBleed={false}
    isHiddenOnDesktop={false}
    isHiddenOnMobile={false}
    padding="8px 12px"
    sticky={null}
    style={{}}
    type="main"
  >
    <Breadcrumbs
      id="breadcrumbs1"
      itemMode="static"
      style={{
        fontSize: "h6Font",
        fontWeight: "h6Font",
        fontFamily: "h6Font",
        currentPageFontSize: "h6Font",
        currentPageFontWeight: "h6Font",
        currentPageFontFamily: "h6Font",
      }}
      value="{{ retoolContext.appUuid }}"
    >
      <Option id="5e5bd" itemType="page" label="Geral" screenTargetId="home" />
      <Option
        id="91ad8"
        itemType="page"
        label="{{ ClienteDropDown.selectedItem.name }}"
        screenTargetId="cadastroContabilidade"
      />
    </Breadcrumbs>
    <Container
      id="collapsibleContainer8"
      footerPadding="4px 12px"
      headerPadding="4px 12px"
      padding="12px"
      showBody={true}
      showHeader={true}
    >
      <Header>
        <Text
          id="collapsibleTitle8"
          value="#### Listas"
          verticalAlign="center"
        />
        <ToggleButton
          id="collapsibleToggle8"
          horizontalAlign="right"
          iconForFalse="bold/interface-arrows-button-down"
          iconForTrue="bold/interface-arrows-button-up"
          iconPosition="replace"
          styleVariant="outline"
          text="{{ self.value ? 'Hide' : 'Show' }}"
          value="{{ collapsibleContainer8.showBody }}"
        >
          <Event
            event="change"
            method="setShowBody"
            params={{ map: { showBody: "{{ self.value }}" } }}
            pluginId="collapsibleContainer8"
            type="widget"
            waitMs="0"
            waitType="debounce"
          />
        </ToggleButton>
      </Header>
      <View id="fd113" viewKey="View 1">
        <Include src="./group40.rsx" />
      </View>
    </Container>
  </Frame>
</Screen>
