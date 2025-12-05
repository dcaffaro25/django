<Screen
  id="cadastroBilling"
  _customShortcuts={[]}
  _hashParams={[]}
  _searchParams={[]}
  browserTitle=""
  title="Cadastro Contabilidade"
  urlSlug="cadastro-1"
  uuid="c0bef0ab-1873-4260-82d5-ca75e1f683f5"
>
  <RESTQuery
    id="business_partner_categories_get"
    isHidden={false}
    isMultiplayerEdited={false}
    query="/{{ tenant_subdomain.value }}/api/business_partner_categories/"
    queryTimeout="30000"
    resourceDisplayName="Tenant Specific - Production"
    resourceName="db4d0175-aa88-429c-ba3f-f4bbd2c875e3"
    resourceTypeOverride=""
  />
  <RESTQuery
    id="business_partner_categories_context_get"
    isHidden={false}
    isMultiplayerEdited={false}
    query="/{{ tenant_subdomain.value }}/api/entities/{{ business_partner_categories_selected.value.id }} /context-options/"
    queryDisabled={
      '{{ business_partner_categories_selected.value === null || business_partner_categories_selected.value === "" }}'
    }
    resourceDisplayName="Tenant Specific - Production"
    resourceName="db4d0175-aa88-429c-ba3f-f4bbd2c875e3"
    resourceTypeOverride=""
  />
  <RESTQuery
    id="business_partner_categories_edit"
    body="{{ BusinessPartnerCategoryForm.data }}"
    bodyType="raw"
    cookies={'[{"key":"","value":""}]'}
    headers={'[{"key":"Content-Type","value":"application/json"}]'}
    isHidden={false}
    isMultiplayerEdited={false}
    query="/{{ tenant_subdomain.value }}/api/business_partner_categories/{{ 
business_partner_categories_selected.value.id }}/"
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
      pluginId="business_partner_categories_get"
      type="datasource"
      waitMs="0"
      waitType="debounce"
    />
    <Event
      event="success"
      method="setValue"
      params={{ map: { value: '""' } }}
      pluginId="business_partner_categories_selected"
      type="state"
      waitMs="0"
      waitType="debounce"
    />
    <Event
      event="success"
      method="hide"
      params={{}}
      pluginId="modalBusinessPartnerCategory"
      type="widget"
      waitMs="0"
      waitType="debounce"
    />
  </RESTQuery>
  <RESTQuery
    id="business_partner_categories_new"
    body="{{ BusinessPartnerCategoryForm.data }}"
    bodyType="raw"
    cookies={'[{"key":"","value":""}]'}
    headers={'[{"key":"Content-Type","value":"application/json"}]'}
    isHidden={false}
    isMultiplayerEdited={false}
    query="/{{ tenant_subdomain.value }}/api/business_partner_categories/?"
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
      pluginId="business_partner_categories_get"
      type="datasource"
      waitMs="0"
      waitType="debounce"
    />
    <Event
      event="success"
      method="setValue"
      params={{ map: { value: '""' } }}
      pluginId="business_partner_categories_selected"
      type="state"
      waitMs="0"
      waitType="debounce"
    />
    <Event
      event="success"
      method="hide"
      params={{}}
      pluginId="modalBusinessPartnerCategory"
      type="widget"
      waitMs="0"
      waitType="debounce"
    />
  </RESTQuery>
  <State id="business_partner_categories_selected" />
  <State id="business_partner_categories_mode" />
  <RESTQuery
    id="business_partner_edit"
    body="{{  BusinessPartnerForm.data }}"
    bodyType="raw"
    cookies={'[{"key":"","value":""}]'}
    headers={'[{"key":"Content-Type","value":"application/json"}]'}
    isHidden={false}
    isMultiplayerEdited={false}
    query="/{{ tenant_subdomain.value }}/api/business_partners/{{ 
business_partner_selected.value.id }}/"
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
      pluginId="business_partner_get"
      type="datasource"
      waitMs="0"
      waitType="debounce"
    />
    <Event
      event="success"
      method="hide"
      params={{}}
      pluginId="modalBusinessPartner"
      type="widget"
      waitMs="0"
      waitType="debounce"
    />
  </RESTQuery>
  <State id="business_partner_mode" />
  <State id="business_partner_selected" />
  <RESTQuery
    id="business_partner_new"
    body="{{ BusinessPartnerForm.data }}"
    bodyType="raw"
    cookies={'[{"key":"","value":""}]'}
    headers={'[{"key":"Content-Type","value":"application/json"}]'}
    isHidden={false}
    isMultiplayerEdited={false}
    query="/{{ tenant_subdomain.value }}/api/business_partners/?"
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
      pluginId="business_partner_get"
      type="datasource"
      waitMs="0"
      waitType="debounce"
    />
    <Event
      event="success"
      method="setValue"
      params={{ map: { value: '""' } }}
      pluginId="business_partner_selected"
      type="state"
      waitMs="0"
      waitType="debounce"
    />
    <Event
      event="success"
      method="hide"
      params={{}}
      pluginId="modalBusinessPartner"
      type="widget"
      waitMs="0"
      waitType="debounce"
    />
  </RESTQuery>
  <RESTQuery
    id="business_partner_get"
    isHidden={false}
    isMultiplayerEdited={false}
    query="/{{ tenant_subdomain.value }}/api/business_partners/?"
    resourceDisplayName="Tenant Specific - Production"
    resourceName="db4d0175-aa88-429c-ba3f-f4bbd2c875e3"
    resourceTypeOverride=""
  />
  <RESTQuery
    id="product_service_categories_new"
    body="{{ ProductServiceCategoryForm.data }}"
    bodyType="raw"
    cookies={'[{"key":"","value":""}]'}
    headers={'[{"key":"Content-Type","value":"application/json"}]'}
    isHidden={false}
    isMultiplayerEdited={false}
    query="/{{ tenant_subdomain.value }}/api/product_service_categories/?"
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
      pluginId="product_service_categories_get"
      type="datasource"
      waitMs="0"
      waitType="debounce"
    />
    <Event
      event="success"
      method="setValue"
      params={{ map: { value: '""' } }}
      pluginId="product_service_categories_selected"
      type="state"
      waitMs="0"
      waitType="debounce"
    />
    <Event
      event="success"
      method="hide"
      params={{}}
      pluginId="modalProductServiceCategory"
      type="widget"
      waitMs="0"
      waitType="debounce"
    />
  </RESTQuery>
  <RESTQuery
    id="product_service_categories_edit"
    body="{{  ProductServiceCategoryForm.data }}"
    bodyType="raw"
    cookies={'[{"key":"","value":""}]'}
    headers={'[{"key":"Content-Type","value":"application/json"}]'}
    isHidden={false}
    isMultiplayerEdited={false}
    query="/{{ tenant_subdomain.value }}/api/product_service_categories/{{ 
product_service_categories_selected.value.id }}/"
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
      pluginId="product_service_categories_get"
      type="datasource"
      waitMs="0"
      waitType="debounce"
    />
    <Event
      event="success"
      method="hide"
      params={{}}
      pluginId="modalProductServiceCategory"
      type="widget"
      waitMs="0"
      waitType="debounce"
    />
    <Event
      event="success"
      method="setValue"
      params={{ map: { value: "null" } }}
      pluginId="product_service_categories_selected"
      type="state"
      waitMs="0"
      waitType="debounce"
    />
  </RESTQuery>
  <State id="product_service_categories_mode" />
  <State id="product_service_categories_selected" />
  <RESTQuery
    id="product_service_categories_get"
    isHidden={false}
    isMultiplayerEdited={false}
    query="/{{ tenant_subdomain.value }}/api/product_service_categories/?"
    resourceDisplayName="Tenant Specific - Production"
    resourceName="db4d0175-aa88-429c-ba3f-f4bbd2c875e3"
    resourceTypeOverride=""
  />
  <RESTQuery
    id="product_service_new"
    body="{{ ProductServiceForm.data }}"
    bodyType="raw"
    cookies={'[{"key":"","value":""}]'}
    headers={'[{"key":"Content-Type","value":"application/json"}]'}
    isHidden={false}
    isMultiplayerEdited={false}
    query="/{{ tenant_subdomain.value }}/api/product_services/?"
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
      pluginId="product_service_get"
      type="datasource"
      waitMs="0"
      waitType="debounce"
    />
    <Event
      event="success"
      method="setValue"
      params={{ map: { value: '""' } }}
      pluginId="product_service_selected"
      type="state"
      waitMs="0"
      waitType="debounce"
    />
    <Event
      event="success"
      method="hide"
      params={{}}
      pluginId="modalProductService"
      type="widget"
      waitMs="0"
      waitType="debounce"
    />
  </RESTQuery>
  <State id="product_service_selected" />
  <RESTQuery
    id="product_service_get"
    isHidden={false}
    isMultiplayerEdited={false}
    query="/{{ tenant_subdomain.value }}/api/product_services/?"
    resourceDisplayName="Tenant Specific - Production"
    resourceName="db4d0175-aa88-429c-ba3f-f4bbd2c875e3"
    resourceTypeOverride=""
  />
  <RESTQuery
    id="product_service_edit"
    body="{{ ProductServiceForm.data }}"
    bodyType="raw"
    cookies={'[{"key":"","value":""}]'}
    headers={'[{"key":"Content-Type","value":"application/json"}]'}
    isHidden={false}
    isMultiplayerEdited={false}
    query="/{{ tenant_subdomain.value }}/api/product_services/{{ 
product_service_selected.value.id }}/"
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
      pluginId="product_service_get"
      type="datasource"
      waitMs="0"
      waitType="debounce"
    />
    <Event
      event="success"
      method="setValue"
      params={{ map: { value: '""' } }}
      pluginId="product_service_selected"
      type="state"
      waitMs="0"
      waitType="debounce"
    />
    <Event
      event="success"
      method="hide"
      params={{}}
      pluginId="modalProductService"
      type="widget"
      waitMs="0"
      waitType="debounce"
    />
  </RESTQuery>
  <State id="product_service_mode" />
  <RESTQuery
    id="contract_edit"
    body="{{  ContractForm.data }}"
    bodyType="raw"
    cookies={'[{"key":"","value":""}]'}
    headers={'[{"key":"Content-Type","value":"application/json"}]'}
    isHidden={false}
    isMultiplayerEdited={false}
    query="/{{ tenant_subdomain.value }}/api/contracts/{{ 
contract_selected.value.id }}/"
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
      pluginId="contract_get"
      type="datasource"
      waitMs="0"
      waitType="debounce"
    />
    <Event
      event="success"
      method="hide"
      params={{}}
      pluginId="modalContract"
      type="widget"
      waitMs="0"
      waitType="debounce"
    />
    <Event
      event="success"
      method="setValue"
      params={{ map: { value: "null" } }}
      pluginId="contract_selected"
      type="state"
      waitMs="0"
      waitType="debounce"
    />
  </RESTQuery>
  <RESTQuery
    id="contract_new"
    body="{{ ContractForm.data }}"
    bodyType="raw"
    cookies={'[{"key":"","value":""}]'}
    headers={'[{"key":"Content-Type","value":"application/json"}]'}
    isHidden={false}
    isMultiplayerEdited={false}
    query="/{{ tenant_subdomain.value }}/api/contracts/?"
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
      pluginId="contract_get"
      type="datasource"
      waitMs="0"
      waitType="debounce"
    />
    <Event
      event="success"
      method="setValue"
      params={{ map: { value: '""' } }}
      pluginId="contract_selected"
      type="state"
      waitMs="0"
      waitType="debounce"
    />
    <Event
      event="success"
      method="hide"
      params={{}}
      pluginId="modalContract"
      type="widget"
      waitMs="0"
      waitType="debounce"
    />
  </RESTQuery>
  <State id="contract_mode" value="" />
  <RESTQuery
    id="contract_get"
    isHidden={false}
    isMultiplayerEdited={false}
    query="/{{ tenant_subdomain.value }}/api/contracts/?"
    resourceDisplayName="Tenant Specific - Production"
    resourceName="db4d0175-aa88-429c-ba3f-f4bbd2c875e3"
    resourceTypeOverride=""
  />
  <State id="contract_selected" />
  <RESTQuery
    id="bulk_import_preview3"
    body="{{ BusinessPartnerForm.data }}"
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
      pluginId="business_partner_get"
      type="datasource"
      waitMs="0"
      waitType="debounce"
    />
    <Event
      event="success"
      method="setValue"
      params={{ map: { value: '""' } }}
      pluginId="business_partner_selected"
      type="state"
      waitMs="0"
      waitType="debounce"
    />
    <Event
      event="success"
      method="hide"
      params={{}}
      pluginId="modalBusinessPartner"
      type="widget"
      waitMs="0"
      waitType="debounce"
    />
  </RESTQuery>
  <Include src="./modalAccountFS2.rsx" />
  <Include src="./modalBankAccountsFS2.rsx" />
  <Include src="./modalBusinessPartner.rsx" />
  <Include src="./modalBusinessPartnerCategory.rsx" />
  <Include src="./modalBusinessPartnerFS2.rsx" />
  <Include src="./modalContract.rsx" />
  <Include src="./modalEntidadeFC2.rsx" />
  <Include src="./modalFrame7.rsx" />
  <Include src="./modalNewPosition3.rsx" />
  <Include src="./modalProductService.rsx" />
  <Include src="./modalProductServiceCategory.rsx" />
  <Frame
    id="$main10"
    enableFullBleed={false}
    isHiddenOnDesktop={false}
    isHiddenOnMobile={false}
    padding="8px 12px"
    sticky={null}
    type="main"
  >
    <Breadcrumbs
      id="breadcrumbs2"
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
      id="collapsibleContainer14"
      footerPadding="4px 12px"
      headerPadding="4px 12px"
      padding="12px"
      showBody={true}
      showHeader={true}
    >
      <Header>
        <Text
          id="collapsibleTitle14"
          value="#### Listas"
          verticalAlign="center"
        />
        <ToggleButton
          id="collapsibleToggle14"
          horizontalAlign="right"
          iconForFalse="bold/interface-arrows-button-down"
          iconForTrue="bold/interface-arrows-button-up"
          iconPosition="replace"
          styleVariant="outline"
          text="{{ self.value ? 'Hide' : 'Show' }}"
          value="{{ collapsibleContainer14.showBody }}"
        >
          <Event
            event="change"
            method="setShowBody"
            params={{ map: { showBody: "{{ self.value }}" } }}
            pluginId="collapsibleContainer14"
            type="widget"
            waitMs="0"
            waitType="debounce"
          />
        </ToggleButton>
      </Header>
      <View id="fd113" viewKey="View 1">
        <Include src="./group44.rsx" />
      </View>
    </Container>
  </Frame>
</Screen>
