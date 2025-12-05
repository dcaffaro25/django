<Screen
  id="page5"
  _customShortcuts={[]}
  _hashParams={[]}
  _order={13}
  _searchParams={[]}
  browserTitle={null}
  title={null}
  urlSlug={null}
  uuid="d5ee9516-46c4-4ee9-863e-596c5e995d1c"
>
  <RESTQuery
    id="financial_statements_get"
    headers={
      '[{"key":"content-type","value":"application/json"},{"key":"authorization","value":"Token {{ currentUser.value.token }}"}]'
    }
    isHidden={false}
    isMultiplayerEdited={false}
    query="{{ baseUrl.value }}/{{ tenant_subdomain.value }}/api/financial-statements/"
    queryDisabled="{{ currentUser.value == null || SelectedTenant.value == null }}"
    queryTimeout="20000"
    resourceName="REST-WithoutResource"
    resourceTypeOverride=""
  />
  <RESTQuery
    id="financial_statements_generate"
    body={
      '{\n    "template_id": 2,\n    "start_date": "2025-01-01",\n    "end_date": "2025-03-31",\n    "comparison_types": ["previous_period"],\n    "dimension": "month",\n    "include_pending": true\n}'
    }
    bodyType="raw"
    headers={
      '[{"key":"content-type","value":"application/json"},{"key":"authorization","value":"Token {{ currentUser.value.token }}"}]'
    }
    isHidden={false}
    isMultiplayerEdited={false}
    query="{{ baseUrl.value }}/{{ tenant_subdomain.value }}/api/financial-statements/with_comparisons/?preview=true"
    queryDisabled="{{ currentUser.value == null || SelectedTenant.value == null }}"
    queryTimeout="20000"
    resourceName="REST-WithoutResource"
    resourceTypeOverride=""
    runWhenModelUpdates={false}
    type="POST"
  />
  <RESTQuery
    id="financial_statements_generate2"
    body={
      '{\n    "template_id": 2,\n    "start_date": "2025-01-01",\n    "end_date": "2025-12-31",\n    "dimension": "month",\n    "include_pending": true\n}'
    }
    bodyType="raw"
    headers={
      '[{"key":"content-type","value":"application/json"},{"key":"authorization","value":"Token {{ currentUser.value.token }}"}]'
    }
    isHidden={false}
    isMultiplayerEdited={false}
    query="{{ baseUrl.value }}/{{ tenant_subdomain.value }}/api/financial-statements/time_series/?preview=true&include_metadata=true"
    queryDisabled="{{ currentUser.value == null || SelectedTenant.value == null }}"
    queryTimeout="20000"
    resourceName="REST-WithoutResource"
    resourceTypeOverride=""
    runWhenModelUpdates={false}
    type="POST"
  />
  <Frame
    id="$main15"
    enableFullBleed={false}
    isHiddenOnDesktop={false}
    isHiddenOnMobile={false}
    padding="8px 12px"
    sticky={null}
    type="main"
  >
    <Text
      id="text62"
      value="{{ financial_statements_generate.data.formatted.html }}"
      verticalAlign="center"
    />
    <Text
      id="text63"
      value="{{ financial_statements_generate2.data.formatted.markdown }}"
      verticalAlign="center"
    />
    <HTML
      id="html4"
      css={include("../lib/html4.css", "string")}
      html="{{ financial_statements_generate2.data.formatted.html }}"
    />
    <Container
      id="container38"
      footerPadding="4px 12px"
      headerPadding="4px 12px"
      padding="12px"
      showBody={true}
      showHeader={true}
    >
      <Header>
        <Text
          id="containerTitle39"
          value="#### Container title"
          verticalAlign="center"
        />
      </Header>
      <View id="00030" viewKey="View 1">
        <Text id="text64" value="##### Cash in Bank" verticalAlign="center" />
        <Text
          id="text65"
          value={
            "# {{\n  (() => {\n    const total = _.sumBy(\n      financial_statements_generate2.data.lines[0].data,\n      'value'\n    ) || 0;\n\n    const sign = total < 0 ? '-' : '';\n    let abs = Math.abs(total);\n    let suffix = '';\n\n    if (abs >= 1e9) {\n      abs = abs / 1e9;\n      suffix = 'B';\n    } else if (abs >= 1e6) {\n      abs = abs / 1e6;\n      suffix = 'M';\n    } else if (abs >= 1e3) {\n      abs = abs / 1e3;\n      suffix = 'K';\n    }\n\n    const numStr = abs.toLocaleString('pt-BR', {\n      minimumFractionDigits: 0,\n      maximumFractionDigits: 1,\n    });\n\n    return `${sign}R$ ${numStr}${suffix}`;\n  })()\n}} <span style=\"font-size:0.4em; font-weight:400; opacity:0.7;\">current</span>\n##### Ultimos 6 meses\n"
          }
          verticalAlign="center"
        />
        <Chart
          id="barChart4"
          barGap={0.4}
          barMode="group"
          legendPosition="none"
          rangeSlider={true}
          selectedPoints="[]"
          stackedBarTotalsDataLabelPosition="none"
          title={null}
          xAxisRangeMax=""
          xAxisRangeMin=""
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
            colorArrayDropDown={{ array: ["{{ theme.primary }}"] }}
            colorInputMode="colorArrayDropDown"
            connectorLineColor="#000000"
            dataLabelPosition="none"
            datasource="{{ financial_statements_generate2.data.lines[0].data }}"
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
            name="sales"
            showMarkers={false}
            textTemplate={null}
            textTemplateMode="manual"
            type="bar"
            waterfallBase={0}
            waterfallMeasures={null}
            waterfallMeasuresMode="source"
            xData="{{ formatDataAsObject(financial_statements_generate2.data.lines[0].data).period_key }}"
            xDataMode="source"
            yAxis="y"
            yData="{{ formatDataAsObject(financial_statements_generate2.data.lines[0].data).value }}"
            yDataMode="source"
            zData={null}
            zDataMode="manual"
          />
        </Chart>
      </View>
    </Container>
    <Text
      id="text66"
      value={
        '{{\n  (() => {\n    const result = financial_statements_generate2.data;\n    if (!result || !Array.isArray(result.lines)) return {};\n\n    const lines = result.lines;\n\n    // tenta achar por label; se não achar, cai no índice\n    const cashCF =\n      lines.find(l => l.label === "Cash CF") ||\n      lines[0];\n\n    const cashBalance =\n      lines.find(l => l.label === "Cash Balance") ||\n      lines[lines.length - 1];\n\n    const x = (cashCF.data || []).map(p => p.period_label);\n\n    return {\n      data: [\n        // BARRAS – Cash CF\n        {\n          type: "bar",\n          name: cashCF.label,\n          x,\n          y: (cashCF.data || []).map(p => p.value),\n          hovertemplate: "%{x}<br>Cash CF: R$ %{y:,.2f}<extra></extra>"\n        },\n\n        // LINHA – Cash Balance (eixo secundário)\n        {\n          type: "scatter",\n          mode: "lines+markers",\n          name: cashBalance.label,\n          x,\n          y: (cashBalance.data || []).map(p => p.value),\n          yaxis: "y2",\n          hovertemplate: "%{x}<br>Cash Balance: R$ %{y:,.2f}<extra></extra>"\n        }\n      ],\n      layout: {\n        barmode: "relative",\n        xaxis: {\n          title: "",\n          tickangle: -45\n        },\n        yaxis: {\n          title: "Cash Flow (R$)",\n          tickformat: "~s",      // K / M / B\n          separatethousands: true\n        },\n        yaxis2: {\n          title: "Cash Balance (R$)",\n          overlaying: "y",\n          side: "right",\n          showgrid: false,\n          tickformat: "~s",      // K / M / B\n          separatethousands: true\n        },\n        legend: {\n          orientation: "h"\n        },\n        margin: {\n          t: 30,\n          l: 60,\n          r: 60,\n          b: 80\n        }\n      }\n    };\n  })()\n}}\n'
      }
      verticalAlign="center"
    />
    <Chart
      id="plotlyJsonChart1"
      chartType="plotlyJson"
      plotlyDataJson={
        '{{  (\n  financial_statements_generate2.data &&\n  Array.isArray(financial_statements_generate2.data.lines) &&\n  financial_statements_generate2.data.lines.length &&\n  [\n    { label: "Cash CF",       name: "Cash Flow do período",          type: "bar",     yaxis: null },\n    { label: "Cash Balance",  name: "Saldo de caixa (fim do mês)",   type: "scatter", yaxis: "y2" }\n  ]\n    .map(cfg => {\n      const line = financial_statements_generate2.data.lines.find(l => l.label === cfg.label);\n      if (!line || !line.data || !line.data.length) {\n        return null;\n      }\n\n      const x = line.data.map(p => p.period_label);\n      const y = line.data.map(p => p.value);\n\n      return {\n        type: cfg.type,\n        name: cfg.name,\n        x,\n        y,\n        ...(cfg.type === "scatter" ? { mode: "lines+markers" } : {}),\n        ...(cfg.yaxis ? { yaxis: cfg.yaxis } : {}),\n        hovertemplate: \'%{x}<br>\' + cfg.name + \': R$ %{y:,.2f}<extra></extra>\'\n      };\n    })\n    .filter(Boolean)\n) || []\n}}'
      }
      plotlyLayoutJson={
        "{\n  title: {\n    text: 'Cash Flow & Cash Balance - 2025',\n    x: 0.02,\n    xanchor: 'left',\n    font: {\n      size: 18,\n      family: 'Inter, system-ui, -apple-system, BlinkMacSystemFont, \"Segoe UI\", sans-serif',\n      color: '#111111'\n    }\n  },\n\n  // Global typography & palette (grayscale only)\n  font: {\n    family: 'Inter, system-ui, -apple-system, BlinkMacSystemFont, \"Segoe UI\", sans-serif',\n    color: '#111111',\n    size: 12\n  },\n  colorway: ['#111111', '#6b7280', '#d1d5db'], // black + mid gray + light gray\n\n  // Backgrounds\n  paper_bgcolor: 'rgba(0,0,0,0)', // transparent to blend with Retool\n  plot_bgcolor: '#ffffff',        // pure white chart area\n\n  // Interactions / hover (minimal, unified)\n  hovermode: 'x unified',\n  hoverlabel: {\n    bgcolor: '#000000',\n    bordercolor: '#000000',\n    font: {\n      color: '#ffffff',\n      size: 11\n    }\n  },\n\n  // X axis\n  xaxis: {\n    title: '',\n    tickangle: -35,\n    showgrid: false,\n    zeroline: false,\n    linecolor: '#000000',\n    tickcolor: '#000000',\n    tickfont: { size: 11 },\n    automargin: true\n  },\n\n  // Primary Y axis (bars)\n  yaxis: {\n    title: {\n      text: 'Cash flow (R$)',\n      standoff: 10\n    },\n    tickprefix: 'R$ ',\n    hoverformat: ',.2f',\n    tickformat: '~s',\n    zeroline: false,\n    linecolor: '#000000',\n    tickcolor: '#000000',\n    gridcolor: 'rgba(0,0,0,0.08)', // very subtle light grid\n    gridwidth: 0.6\n  },\n\n  // Secondary Y axis (line)\n  yaxis2: {\n    title: {\n      text: 'Saldo de caixa (R$)',\n      standoff: 10\n    },\n    overlaying: 'y',\n    side: 'right',\n    showgrid: false,\n    tickprefix: 'R$ ',\n    hoverformat: ',.2f',\n    tickformat: '~s',\n    zeroline: false,\n    linecolor: '#000000',\n    tickcolor: '#000000'\n  },\n\n  // Bars + line behavior\n  barmode: 'relative',\n  bargap: 0.2,\n  bargroupgap: 0.05,\n\n  // Legend (subtle, border only)\n  legend: {\n    orientation: 'h',\n    y: 1.08,\n    x: 0,\n    xanchor: 'left',\n    font: { size: 11 },\n    bgcolor: 'rgba(255,255,255,0.9)',\n    bordercolor: 'rgba(0,0,0,0.12)',\n    borderwidth: 1\n  },\n\n  // Layout spacing\n  margin: {\n    t: 60,\n    r: 70,\n    b: 90,\n    l: 70\n  },\n\n  // Smooth transitions on updates\n  transition: {\n    duration: 200,\n    easing: 'cubic-in-out'\n  }\n}\n"
      }
      selectedPoints="[]"
    />
  </Frame>
</Screen>
