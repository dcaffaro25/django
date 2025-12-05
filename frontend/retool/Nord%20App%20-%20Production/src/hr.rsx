<Screen
  id="hr"
  _customShortcuts={[]}
  _hashParams={[]}
  _searchParams={[]}
  browserTitle=""
  title="HR"
  urlSlug="hr"
  uuid="b51d9cd4-ce71-49a5-92da-20aa167ec089"
>
  <State id="employee_selected" />
  <RESTQuery
    id="employees_get"
    isHidden={false}
    isMultiplayerEdited={false}
    query="/{{ tenant_subdomain.value }}/api/hr/employees"
    resourceDisplayName="Tenant Specific"
    resourceName="e4a763c9-4f5e-4f5a-99f7-6a33454d4577"
    resourceTypeOverride=""
  />
  <RESTQuery
    id="employee_new"
    body="{{ EmployeeForm.data }}"
    bodyType="raw"
    cookies={'[{"key":"","value":""}]'}
    headers={'[{"key":"Content-Type","value":"application/json"}]'}
    isHidden={false}
    isMultiplayerEdited={false}
    query="/{{ tenant_subdomain.value }}/api/hr/employees/?"
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
      pluginId="employees_get"
      type="datasource"
      waitMs="0"
      waitType="debounce"
    />
    <Event
      event="success"
      method="setValue"
      params={{ ordered: [{ value: '""' }] }}
      pluginId="employee_selected"
      type="state"
      waitMs="0"
      waitType="debounce"
    />
  </RESTQuery>
  <RESTQuery
    id="employee_edit"
    body="{{ EmployeeForm.data }}"
    bodyType="raw"
    cookies={'[{"key":"","value":""}]'}
    headers={'[{"key":"Content-Type","value":"application/json"}]'}
    isHidden={false}
    isMultiplayerEdited={false}
    query="/{{ tenant_subdomain.value }}/api/hr/employees/{{ 
employee_selected.value.id }}/"
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
      pluginId="employees_get"
      type="datasource"
      waitMs="0"
      waitType="debounce"
    />
    <Event
      event="success"
      method="setValue"
      params={{ ordered: [{ value: '""' }] }}
      pluginId="employee_selected"
      type="state"
      waitMs="0"
      waitType="debounce"
    />
  </RESTQuery>
  <State id="position_selected" />
  <RESTQuery
    id="positions_get"
    isHidden={false}
    isMultiplayerEdited={false}
    query="/{{ tenant_subdomain.value }}/api/hr/positions?"
    resourceDisplayName="Tenant Specific"
    resourceName="e4a763c9-4f5e-4f5a-99f7-6a33454d4577"
    resourceTypeOverride=""
  />
  <RESTQuery
    id="position_new"
    body="{{ PositionForm.data }}"
    bodyType="raw"
    cookies={'[{"key":"","value":""}]'}
    headers={'[{"key":"Content-Type","value":"application/json"}]'}
    isHidden={false}
    isMultiplayerEdited={false}
    query="/{{ tenant_subdomain.value }}/api/hr/positions/?"
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
      pluginId="positions_get"
      type="datasource"
      waitMs="0"
      waitType="debounce"
    />
    <Event
      event="success"
      method="setValue"
      params={{ ordered: [{ value: '""' }] }}
      pluginId="position_selected"
      type="state"
      waitMs="0"
      waitType="debounce"
    />
  </RESTQuery>
  <RESTQuery
    id="position_edit"
    body="{{ PositionForm.data }}"
    bodyType="raw"
    cookies={'[{"key":"","value":""}]'}
    headers={'[{"key":"Content-Type","value":"application/json"}]'}
    isHidden={false}
    isMultiplayerEdited={false}
    query="/{{ tenant_subdomain.value }}/api/hr/positions/{{ 
position_selected.value.id }}/"
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
      pluginId="positions_get"
      type="datasource"
      waitMs="0"
      waitType="debounce"
    />
    <Event
      event="success"
      method="setValue"
      params={{ ordered: [{ value: '""' }] }}
      pluginId="position_selected"
      type="state"
      waitMs="0"
      waitType="debounce"
    />
  </RESTQuery>
  <State id="timetracking_selected" />
  <RESTQuery
    id="timetracking_get"
    isHidden={false}
    isMultiplayerEdited={false}
    query="/{{ tenant_subdomain.value }}/api/hr/timetracking?"
    resourceDisplayName="Tenant Specific"
    resourceName="e4a763c9-4f5e-4f5a-99f7-6a33454d4577"
    resourceTypeOverride=""
  />
  <RESTQuery
    id="timetracking_new"
    body="{{ TimeTrackingForm.data }}"
    bodyType="raw"
    cookies={'[{"key":"","value":""}]'}
    headers={'[{"key":"Content-Type","value":"application/json"}]'}
    isHidden={false}
    isMultiplayerEdited={false}
    query="/{{ tenant_subdomain.value }}/api/hr/timetracking/?"
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
      pluginId="timetracking_get"
      type="datasource"
      waitMs="0"
      waitType="debounce"
    />
    <Event
      event="success"
      method="setValue"
      params={{ ordered: [{ value: '""' }] }}
      pluginId="timetracking_selected"
      type="state"
      waitMs="0"
      waitType="debounce"
    />
  </RESTQuery>
  <RESTQuery
    id="timetracking_edit"
    body="{{ TimeTrackingForm.data }}"
    bodyType="raw"
    cookies={'[{"key":"","value":""}]'}
    headers={'[{"key":"Content-Type","value":"application/json"}]'}
    isHidden={false}
    isMultiplayerEdited={false}
    query="/{{ tenant_subdomain.value }}/api/hr/timetracking/{{ 
timetracking_selected.value.id }}/"
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
      pluginId="timetracking_get"
      type="datasource"
      waitMs="0"
      waitType="debounce"
    />
    <Event
      event="success"
      method="setValue"
      params={{ ordered: [{ value: '""' }] }}
      pluginId="timetracking_selected"
      type="state"
      waitMs="0"
      waitType="debounce"
    />
  </RESTQuery>
  <RESTQuery
    id="timetracking_delete"
    body="{{ TimeTrackingForm.data }}"
    bodyType="raw"
    cookies={'[{"key":"","value":""}]'}
    headers={'[{"key":"Content-Type","value":"application/json"}]'}
    isHidden={false}
    isMultiplayerEdited={false}
    query="/{{ tenant_subdomain.value }}/api/hr/timetracking/{{ 
timetracking_selected.value.id }}/"
    resourceDisplayName="Tenant Specific"
    resourceName="e4a763c9-4f5e-4f5a-99f7-6a33454d4577"
    resourceTypeOverride=""
    runWhenModelUpdates={false}
    type="DELETE"
  >
    <Event
      event="success"
      method="trigger"
      params={{ ordered: [] }}
      pluginId="timetracking_get"
      type="datasource"
      waitMs="0"
      waitType="debounce"
    />
    <Event
      event="success"
      method="setValue"
      params={{ ordered: [{ value: '""' }] }}
      pluginId="timetracking_selected"
      type="state"
      waitMs="0"
      waitType="debounce"
    />
  </RESTQuery>
  <State id="payroll_selected" />
  <RESTQuery
    id="payroll_get"
    isHidden={false}
    isMultiplayerEdited={false}
    query="/{{ tenant_subdomain.value }}/api/hr/payrolls?"
    resourceDisplayName="Tenant Specific"
    resourceName="e4a763c9-4f5e-4f5a-99f7-6a33454d4577"
    resourceTypeOverride=""
  />
  <RESTQuery
    id="payroll_new"
    body={
      '[{"key":"company_id","value":"1"},{"key":"employee_ids","value":"[1]"},{"key":"pay_date","value":"2024-11-01"}]'
    }
    bodyType="json"
    cookies={'[{"key":"","value":""}]'}
    headers={'[{"key":"Content-Type","value":"application/json"}]'}
    isHidden={false}
    isMultiplayerEdited={false}
    query="/{{ tenant_subdomain.value }}/api/hr/payrolls/generate-monthly/"
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
      pluginId="payroll_get"
      type="datasource"
      waitMs="0"
      waitType="debounce"
    />
  </RESTQuery>
  <RESTQuery
    id="payroll_recal"
    body={'[{"key":"payroll_ids","value":"[1]"}]'}
    bodyType="json"
    cookies={'[{"key":"","value":""}]'}
    headers={'[{"key":"Content-Type","value":"application/json"}]'}
    isHidden={false}
    isMultiplayerEdited={false}
    query="/{{ tenant_subdomain.value }}/api/hr/payrolls/recalculate/"
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
      pluginId="payroll_get"
      type="datasource"
      waitMs="0"
      waitType="debounce"
    />
  </RESTQuery>
  <RESTQuery
    id="payroll_delete"
    body="[]"
    bodyType="json"
    cookies={'[{"key":"","value":""}]'}
    headers={'[{"key":"Content-Type","value":"application/json"}]'}
    isHidden={false}
    isMultiplayerEdited={false}
    query="/{{ tenant_subdomain.value }}/api/hr/payrolls/{{ payroll_selected.id }}/"
    resourceDisplayName="Tenant Specific"
    resourceName="e4a763c9-4f5e-4f5a-99f7-6a33454d4577"
    resourceTypeOverride=""
    runWhenModelUpdates={false}
    type="DELETE"
  >
    <Event
      event="success"
      method="trigger"
      params={{ ordered: [] }}
      pluginId="payroll_get"
      type="datasource"
      waitMs="0"
      waitType="debounce"
    />
  </RESTQuery>
  <State id="recurring_adjustment_selected" />
  <RESTQuery
    id="recurring_adjustment_get"
    isHidden={false}
    isMultiplayerEdited={false}
    query="/{{ tenant_subdomain.value }}/api/hr/recurring-adjustments?"
    resourceDisplayName="Tenant Specific"
    resourceName="e4a763c9-4f5e-4f5a-99f7-6a33454d4577"
    resourceTypeOverride=""
  />
  <RESTQuery
    id="recurring_adjustment_new"
    body="{{ RecurringAdjustmentForm.data }}"
    bodyType="raw"
    cookies={'[{"key":"","value":""}]'}
    headers={'[{"key":"Content-Type","value":"application/json"}]'}
    isHidden={false}
    isMultiplayerEdited={false}
    query="/{{ tenant_subdomain.value }}/api/hr/recurring-adjustments/?"
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
      pluginId="recurring_adjustment_get"
      type="datasource"
      waitMs="0"
      waitType="debounce"
    />
    <Event
      event="success"
      method="setValue"
      params={{ ordered: [{ value: '""' }] }}
      pluginId="recurring_adjustment_selected"
      type="state"
      waitMs="0"
      waitType="debounce"
    />
  </RESTQuery>
  <RESTQuery
    id="recurring_adjustment_edit"
    body="{{ RecurringAdjustmentForm.data }}"
    bodyType="raw"
    cookies={'[{"key":"","value":""}]'}
    headers={'[{"key":"Content-Type","value":"application/json"}]'}
    isHidden={false}
    isMultiplayerEdited={false}
    query="/{{ tenant_subdomain.value }}/api/hr/recurring-adjustments/{{ 
recurring_adjustment_selected.value.id }}/"
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
      pluginId="recurring_adjustment_get"
      type="datasource"
      waitMs="0"
      waitType="debounce"
    />
    <Event
      event="success"
      method="setValue"
      params={{ ordered: [{ value: '""' }] }}
      pluginId="recurring_adjustment_selected"
      type="state"
      waitMs="0"
      waitType="debounce"
    />
  </RESTQuery>
  <Include src="./modalNewPosition.rsx" />
  <Frame
    id="$main4"
    enableFullBleed={false}
    isHiddenOnDesktop={false}
    isHiddenOnMobile={false}
    padding="8px 12px"
    sticky={null}
    type="main"
  >
    <Chart
      id="barChart1"
      barGap={0.4}
      barMode="group"
      legendPosition="none"
      selectedPoints="[]"
      stackedBarTotalsDataLabelPosition="none"
      title={null}
      xAxisLineWidth=""
      xAxisRangeMax=""
      xAxisRangeMin=""
      xAxisScale="category"
      xAxisShowTickLabels={true}
      xAxisTickFormat="%Y-%m"
      yAxis2LineWidth={1}
      yAxis2RangeMax=""
      yAxis2RangeMin=""
      yAxis2ShowTickLabels={true}
      yAxis2TickFormatMode="gui"
      yAxisRangeMax=""
      yAxisRangeMin=""
      yAxisShowTickLabels={true}
      yAxisTickFormatMode="gui"
    >
      <Series
        id="0"
        aggregationType="sum"
        colorArray={{ array: [] }}
        colorArrayDropDown={{ array: [] }}
        colorInputMode="gradientColorArray"
        connectorLineColor="#000000"
        dataLabelPosition="none"
        datasource="{{ payroll_get.data }}"
        datasourceMode="manual"
        decreasingBorderColor="#000000"
        decreasingColor="#000000"
        filteredGroups={null}
        filteredGroupsMode="source"
        gradientColorArray={{ array: [] }}
        groupBy={{ array: ["pay_date"] }}
        groupByDropdownType="source"
        groupByStyles={{}}
        hoverTemplateArray={{ array: [] }}
        hoverTemplateMode="manual"
        increasingBorderColor="#000000"
        increasingColor="#000000"
        lineColor="#000000"
        lineDash="solid"
        lineShape="linear"
        lineUnderFillMode="none"
        lineWidth={2}
        markerBorderColor="#ffffff"
        markerBorderWidth={1}
        markerColor="#000000"
        markerSize={6}
        markerSymbol="circle"
        name="A Pagar"
        showMarkers={false}
        textTemplateMode="manual"
        type="bar"
        waterfallBase={0}
        waterfallMeasures={{ array: [] }}
        waterfallMeasuresMode="source"
        xData="{{ formatDataAsObject(payroll_get.data).pay_date }}"
        xDataMode="source"
        yAxis="y"
        yData="{{ formatDataAsObject(payroll_get.data).net_salary }}"
        yDataMode="source"
        zData="[1, 2, 3, 4, 5]"
        zDataMode="manual"
      />
    </Chart>
    <Statistic
      id="statistic1"
      currency="USD"
      label="Funcionários"
      labelCaption="Ativos"
      positiveTrend="{{ self.value >= 0 }}"
      secondaryCurrency="USD"
      secondaryEnableTrend={true}
      secondaryFormattingStyle="percent"
      secondaryPositiveTrend="{{ self.secondaryValue >= 0 }}"
      secondaryShowSeparators={true}
      secondarySignDisplay="trendArrows"
      secondaryValue=""
      showSeparators={true}
      value="{{ employees_get.data.length }}"
    />
    <Include src="./tabbedContainer1.rsx" />
  </Frame>
</Screen>
