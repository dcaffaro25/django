<ModalFrame
  id="modalGeneralImport"
  enableFullBleed={true}
  footerPadding="8px 12px"
  headerPadding="8px 12px"
  hidden={true}
  hideOnEscape={true}
  isHiddenOnMobile={true}
  overlayInteraction={true}
  padding="8px 12px"
  showFooter={true}
  showHeader={true}
  showOverlay={true}
  size="fullScreen"
>
  <Header>
    <Text id="modalTitle22" value="### General Import" verticalAlign="center" />
    <Button
      id="modalCloseButton24"
      ariaLabel="Close"
      horizontalAlign="right"
      iconBefore="bold/interface-delete-1"
      style={{ map: { border: "transparent" } }}
      styleVariant="outline"
    >
      <Event
        event="click"
        method="setHidden"
        params={{ map: { hidden: true } }}
        pluginId="modalGeneralImport"
        type="widget"
        waitMs="0"
        waitType="debounce"
      />
      <Event
        event="click"
        method="reset"
        params={{}}
        pluginId="bulk_import_preview5"
        type="datasource"
        waitMs="0"
        waitType="debounce"
      />
    </Button>
  </Header>
  <Body>
    <Container
      id="tabbedContainer3"
      currentViewKey="{{ self.viewKeys[0] }}"
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
        <Tabs
          id="tabs3"
          itemMode="static"
          navigateContainer={true}
          targetContainerId="tabbedContainer3"
          value="{{ self.values[0] }}"
        >
          <Option id="00030" value="Tab 1" />
          <Option id="00031" value="Tab 2" />
          <Option id="00032" value="Tab 3" />
        </Tabs>
      </Header>
      <View id="00030" viewKey="Registros">
        <Table
          id="table38"
          cellSelection="none"
          clearChangesetOnSave={true}
          data={
            '{{ bulk_import_preview5.data.data.imports.flatMap(item =>\n  item.result.map(row => ({\n    model: item.model,\n    __row_id: row.__row_id,\n    status: row.status,\n    action: row.action,\n    data: row.data,          // merge all nested "data" properties\n    observations: row.observations,\n    message: row.message\n  }))\n) }}\n'
          }
          defaultSelectedRow={{ mode: "index", indexType: "display", index: 0 }}
          emptyMessage="No rows found"
          enableSaveActions={true}
          showBorder={true}
          showFooter={true}
          showHeader={true}
          toolbarPosition="bottom"
        >
          <Column
            id="ac625"
            alignment="left"
            format="string"
            formatOptions={{ automaticColors: true }}
            groupAggregationMode="none"
            key="model"
            label="Model"
            placeholder="Enter value"
            position="center"
            size={144}
            summaryAggregationMode="none"
            valueOverride="{{ _.startCase(item) }}"
          />
          <Column
            id="edb97"
            alignment="left"
            format="string"
            groupAggregationMode="none"
            key="__row_id"
            label="Row ID"
            placeholder="Enter value"
            position="center"
            size={100}
            summaryAggregationMode="none"
          />
          <Column
            id="db1c1"
            alignment="left"
            cellTooltip="{{ table38.data[i].message }}"
            cellTooltipMode="custom"
            format="tag"
            formatOptions={{
              automaticColors: false,
              color:
                "{{ \n  {\n    Success:'#ecfdf5', \n    Ok:'#eff6ff', \n    Warning:'#fffbeb', \n    Error:'#fef2f2'\n  }[item]\n}}\n",
            }}
            groupAggregationMode="none"
            key="status"
            label="Status"
            placeholder="Select option"
            position="center"
            size={100}
            summaryAggregationMode="none"
            valueOverride="{{ _.startCase(item) }}"
          />
          <Column
            id="008eb"
            alignment="left"
            format="tag"
            formatOptions={{
              automaticColors: false,
              color:
                "{{ \n  {\n    Create:'#ecfdf5', \n    Edit:'#eff6ff', \n    Delete:'#fffbeb'\n  }[item]\n}}\n",
            }}
            groupAggregationMode="none"
            key="action"
            label="Action"
            placeholder="Select option"
            position="center"
            size={106}
            summaryAggregationMode="none"
            valueOverride="{{ _.startCase(item) }}"
          />
          <Column
            id="c5f4b"
            alignment="left"
            cellTooltipMode="overflow"
            format="string"
            groupAggregationMode="none"
            key="message"
            label="Message"
            placeholder="Enter value"
            position="center"
            size={121}
            summaryAggregationMode="none"
          />
          <Column
            id="06018"
            alignment="left"
            cellTooltipMode="overflow"
            format="multilineString"
            formatOptions={{ automaticColors: true }}
            groupAggregationMode="none"
            key="observations"
            label="Observations"
            placeholder="Enter value"
            position="center"
            size={265}
            summaryAggregationMode="none"
          />
          <Column
            id="3e53e"
            alignment="left"
            cellTooltipMode="overflow"
            format="multilineString"
            groupAggregationMode="none"
            key="data"
            label="Data"
            placeholder="Enter value"
            position="center"
            size={573.328125}
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
              pluginId="table38"
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
              pluginId="table38"
              type="widget"
              waitMs="0"
              waitType="debounce"
            />
          </ToolbarButton>
        </Table>
      </View>
      <View id="00031" viewKey="Erros">
        <Table
          id="table39"
          cellSelection="none"
          clearChangesetOnSave={true}
          data="{{ bulk_import_ETL.data.errors }}"
          defaultSelectedRow={{ mode: "index", indexType: "display", index: 0 }}
          emptyMessage="No rows found"
          enableSaveActions={true}
          showBorder={true}
          showFooter={true}
          showHeader={true}
          toolbarPosition="bottom"
        >
          <Column
            id="ac625"
            alignment="left"
            format="string"
            formatOptions={{ automaticColors: true }}
            groupAggregationMode="none"
            key="model"
            label="Model"
            placeholder="Enter value"
            position="center"
            size={84.296875}
            summaryAggregationMode="none"
            valueOverride="{{ _.startCase(item) }}"
          />
          <Column
            id="a4806"
            alignment="right"
            editableOptions={{ showStepper: true }}
            format="decimal"
            formatOptions={{ showSeparators: true, notation: "standard" }}
            groupAggregationMode="sum"
            key="row"
            label="Row"
            placeholder="Enter value"
            position="center"
            size={100}
            summaryAggregationMode="none"
          />
          <Column
            id="379b3"
            alignment="left"
            format="string"
            groupAggregationMode="none"
            key="field"
            label="Field"
            placeholder="Enter value"
            position="center"
            size={100}
            summaryAggregationMode="none"
          />
          <Column
            id="158c7"
            alignment="left"
            cellTooltipMode="overflow"
            format="string"
            groupAggregationMode="none"
            key="message"
            label="Message"
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
              pluginId="table39"
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
              pluginId="table39"
              type="widget"
              waitMs="0"
              waitType="debounce"
            />
          </ToolbarButton>
        </Table>
      </View>
      <View
        id="07c8b"
        disabled={false}
        hidden={false}
        iconPosition="left"
        viewKey="Raw Response"
      >
        <JSONExplorer id="jsonExplorer1" value="{{ bulk_import_ETL.data }}" />
      </View>
    </Container>
  </Body>
  <Footer>
    <Button id="button31" text="Submit">
      <Event
        enabled=""
        event="click"
        method="run"
        params={{
          map: {
            src: '// --- Gather rows from the preview (or the table if you already bound it) ---\nconst imports = bulk_import_preview5.data?.data?.imports ?? [];\nconst flattenedFromPreview = imports.flatMap(item =>\n  (item?.result ?? []).map(row => ({\n    model: item.model,\n    __row_id: row.__row_id,\n    status: row.status,\n    action: row.action,\n    data: row.data,\n    observations: row.observations,\n    message: row.message\n  }))\n);\n\n// If table38 already points to that flattened array, prefer it;\n// otherwise fall back to recomputing from the preview response.\nconst rows = Array.isArray(table38.data) && table38.data.length\n  ? table38.data\n  : flattenedFromPreview;\n\n// Guard: no rows\nif (!rows.length) {\n  utils.showNotification({\n    title: "Nothing to submit",\n    description: "Run the preview first to generate rows.",\n    intent: "warning",\n    duration: 6000\n  });\n  return;\n}\n\n// Helper to detect error-like statuses (case-insensitive)\nconst isErrorStatus = (s) => {\n  const v = String(s ?? "").trim().toLowerCase();\n  return ["error", "erro", "failed", "fail", "invalid"].includes(v);\n};\n\n// Compute errors and breakdown by model\nconst errorRows = rows.filter(r => isErrorStatus(r.status));\nif (errorRows.length > 0) {\n  const byModel = errorRows.reduce((acc, r) => {\n    acc[r.model] = (acc[r.model] ?? 0) + 1;\n    return acc;\n  }, {});\n  const breakdown = Object.entries(byModel)\n    .map(([model, count]) => `• ${model}: ${count} error${count > 1 ? "s" : ""}`)\n    .join("\\n");\n\n  utils.showNotification({\n    title: "Can\'t submit: errors found",\n    description: `Fix the errors in your file before executing.\\n\\nTotal errors: ${errorRows.length}\\n${breakdown}`,\n    intent: "danger",\n    duration: 9000\n  });\n  return;\n}\n\n// No errors -> execute import\nbulk_import_execute2.trigger({\n  onSuccess: (res) => {\n    const committed = res?.data?.committed ?? res?.committed ?? true;\n    const reason = res?.data?.reason ?? res?.reason ?? "";\n    const desc = committed\n      ? "Import committed successfully."\n      : `Executed, but backend reported not committed${reason ? ` (${reason})` : ""}.`;\n\n    utils.showNotification({\n      title: committed ? "Import complete" : "Import finished with warnings",\n      description: desc,\n      intent: committed ? "success" : "warning",\n      duration: 7000\n    });\n  },\n  onFailure: (err) => {\n    utils.showNotification({\n      title: "Import failed",\n      description: err?.message || String(err),\n      intent: "danger",\n      duration: 9000\n    });\n  }\n});\n',
          },
        }}
        pluginId=""
        type="script"
        waitMs="0"
        waitType="debounce"
      />
    </Button>
  </Footer>
</ModalFrame>
