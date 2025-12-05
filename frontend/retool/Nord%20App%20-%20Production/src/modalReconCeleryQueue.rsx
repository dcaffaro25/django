<ModalFrame
  id="modalReconCeleryQueue"
  enableFullBleed={true}
  footerPadding="8px 12px"
  headerPadding="8px 12px"
  hidden={true}
  hideOnEscape={true}
  isHiddenOnMobile={true}
  overlayInteraction={true}
  padding="8px 12px"
  showHeader={true}
  showOverlay={true}
  size="fullScreen"
>
  <Header>
    <Text
      id="modalTitle37"
      value="### Reconciliation Queue"
      verticalAlign="center"
    />
    <Button
      id="modalCloseButton41"
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
        pluginId="modalReconCeleryQueue"
        type="widget"
        waitMs="0"
        waitType="debounce"
      />
    </Button>
  </Header>
  <Body>
    <Container
      id="group97"
      _align="end"
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
      style={{ map: { background: "rgba(255, 255, 255, 0)" } }}
    >
      <View id="00030" viewKey="View 1">
        <ButtonGroup
          id="buttonGroupLegacy1"
          label="Últimos"
          value={'"1h"'}
          values={'["1h","6h","1d", "7d", "30d"]'}
        />
        <Table
          id="table48"
          actionsOverflowPosition={1}
          cellSelection="none"
          clearChangesetOnSave={true}
          data={
            '{{ [].concat(\n  (Queue_get.data.db_tasks || []).map(t => ({ type: "db_task", ...t }))\n  )\n}}\n'
          }
          defaultSelectedRow={{ mode: "index", indexType: "display", index: 0 }}
          emptyMessage="No rows found"
          enableSaveActions={true}
          heightType="fill"
          showBorder={true}
          showFooter={true}
          showHeader={true}
          toolbarPosition="bottom"
        >
          <Column
            id="5401b"
            alignment="left"
            format="tag"
            formatOptions={{
              automaticColors: false,
              color: "{{  colorTagStatusQueue.value[item]}}",
            }}
            groupAggregationMode="none"
            key="status"
            label="Status"
            placeholder="Select option"
            position="left"
            size={100}
            summaryAggregationMode="none"
            valueOverride="{{ item }}"
          />
          <Column
            id="48b63"
            alignment="left"
            format="string"
            groupAggregationMode="none"
            key="duration_seconds"
            label="Duration seconds"
            placeholder="Enter value"
            position="center"
            size={78}
            summaryAggregationMode="none"
          />
          <Column
            id="8b2e3"
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
            size={57}
            summaryAggregationMode="none"
          />
          <Column
            id="38dac"
            alignment="left"
            format="string"
            groupAggregationMode="none"
            key="config_name"
            label="Config name"
            placeholder="Enter value"
            position="center"
            size={101}
            summaryAggregationMode="none"
          />
          <Column
            id="12652"
            alignment="left"
            format="tag"
            formatOptions={{ automaticColors: true }}
            groupAggregationMode="none"
            key="type"
            label="Type"
            placeholder="Select option"
            position="center"
            size={100}
            summaryAggregationMode="none"
            valueOverride="{{ _.startCase(item) }}"
          />
          <Column
            id="68041"
            alignment="left"
            format="string"
            groupAggregationMode="none"
            key="task_id"
            label="Task ID"
            placeholder="Enter value"
            position="center"
            size={100}
            summaryAggregationMode="none"
          />
          <Column
            id="60fc5"
            alignment="left"
            format="tag"
            formatOptions={{ automaticColors: true }}
            groupAggregationMode="none"
            key="tenant_id"
            label="Tenant ID"
            placeholder="Select option"
            position="center"
            size={100}
            summaryAggregationMode="none"
            valueOverride="{{ _.startCase(item) }}"
          />
          <Column
            id="e47ec"
            alignment="left"
            cellTooltipMode="overflow"
            format="json"
            groupAggregationMode="none"
            key="parameters"
            label="Parameters"
            placeholder="Enter value"
            position="center"
            size={100}
            summaryAggregationMode="none"
          />
          <Column
            id="a8dd3"
            alignment="left"
            cellTooltipMode="overflow"
            format="json"
            groupAggregationMode="none"
            key="result"
            label="Result"
            placeholder="Enter value"
            position="center"
            size={100}
            summaryAggregationMode="none"
          />
          <Column
            id="f287e"
            alignment="left"
            cellTooltipMode="overflow"
            format="string"
            formatOptions={{ automaticColors: true }}
            groupAggregationMode="none"
            key="error_message"
            label="Error message"
            placeholder="Enter value"
            position="center"
            size={100}
            summaryAggregationMode="none"
            valueOverride="{{ _.startCase(item) }}"
          />
          <Column
            id="f106f"
            alignment="left"
            format="string"
            groupAggregationMode="none"
            key="created_at"
            label="Created at"
            placeholder="Enter value"
            position="center"
            size={100}
            summaryAggregationMode="none"
          />
          <Column
            id="3bd7d"
            alignment="left"
            format="string"
            groupAggregationMode="none"
            key="updated_at"
            label="Updated at"
            placeholder="Enter value"
            position="center"
            size={100}
            summaryAggregationMode="none"
          />
          <Column
            id="fd111"
            alignment="right"
            editableOptions={{ showStepper: true }}
            format="decimal"
            formatOptions={{ showSeparators: true, notation: "standard" }}
            groupAggregationMode="sum"
            key="bank_candidates"
            label="Bank candidates"
            placeholder="Enter value"
            position="center"
            size={92}
            summaryAggregationMode="none"
          />
          <Column
            id="a76d3"
            alignment="right"
            editableOptions={{ showStepper: true }}
            format="decimal"
            formatOptions={{ showSeparators: true, notation: "standard" }}
            groupAggregationMode="sum"
            key="journal_candidates"
            label="Journal candidates"
            placeholder="Enter value"
            position="center"
            size={77}
            summaryAggregationMode="none"
          />
          <Column
            id="4daa2"
            alignment="right"
            editableOptions={{ showStepper: true }}
            format="decimal"
            formatOptions={{ showSeparators: true, notation: "standard" }}
            groupAggregationMode="sum"
            key="suggestion_count"
            label="Suggestion count"
            placeholder="Enter value"
            position="center"
            size={100}
            summaryAggregationMode="none"
          />
          <Column
            id="80529"
            alignment="right"
            editableOptions={{ showStepper: true }}
            format="decimal"
            formatOptions={{ showSeparators: true, notation: "standard" }}
            groupAggregationMode="sum"
            key="matched_bank_transactions"
            label="Matched bank transactions"
            placeholder="Enter value"
            position="center"
            size={78}
            summaryAggregationMode="none"
          />
          <Column
            id="06bbb"
            alignment="right"
            editableOptions={{ showStepper: true }}
            format="decimal"
            formatOptions={{ showSeparators: true, notation: "standard" }}
            groupAggregationMode="sum"
            key="matched_journal_entries"
            label="Matched journal entries"
            placeholder="Enter value"
            position="center"
            size={66}
            summaryAggregationMode="none"
          />
          <Column
            id="d7424"
            alignment="left"
            format="boolean"
            groupAggregationMode="none"
            key="auto_match_enabled"
            label="Auto match enabled"
            placeholder="Enter value"
            position="center"
            size={92}
            summaryAggregationMode="none"
          />
          <Column
            id="3bad7"
            alignment="right"
            editableOptions={{ showStepper: true }}
            format="decimal"
            formatOptions={{ showSeparators: true, notation: "standard" }}
            groupAggregationMode="sum"
            key="auto_match_applied"
            label="Auto match applied"
            placeholder="Enter value"
            position="center"
            size={100}
            summaryAggregationMode="none"
          />
          <Column
            id="0c5b9"
            alignment="right"
            editableOptions={{ showStepper: true }}
            format="decimal"
            formatOptions={{ showSeparators: true, notation: "standard" }}
            groupAggregationMode="sum"
            key="auto_match_skipped"
            label="Auto match skipped"
            placeholder="Enter value"
            position="center"
            size={74}
            summaryAggregationMode="none"
          />
          <Column
            id="9a792"
            alignment="left"
            format="json"
            groupAggregationMode="none"
            key="stats"
            label="Stats"
            placeholder="Enter value"
            position="center"
            size={0}
            summaryAggregationMode="none"
          />
          <Action id="ae177" icon="bold/interface-delete-2" label="Cancelar">
            <Event
              event="clickAction"
              method="setValue"
              params={{ map: { value: "{{ currentSourceRow.id }}" } }}
              pluginId="selectedReconRecord"
              type="state"
              waitMs="0"
              waitType="debounce"
            />
            <Event
              event="clickAction"
              method="trigger"
              params={{ map: { options: { map: { additionalScope: {} } } } }}
              pluginId="Reconciliate_cancel"
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
              pluginId="table48"
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
              pluginId="table48"
              type="widget"
              waitMs="0"
              waitType="debounce"
            />
          </ToolbarButton>
          <Event
            event="doubleClickRow"
            method="run"
            params={{
              map: {
                src: "// 1) Set the variable\nselectedReconRecord.setValue(currentSourceRow.id);\n\nReconciliation_get.trigger();\n",
              },
            }}
            pluginId=""
            type="script"
            waitMs="0"
            waitType="debounce"
          />
          <Event
            event="doubleClickRow"
            method="hide"
            params={{}}
            pluginId="modalReconCeleryQueue"
            type="widget"
            waitMs="0"
            waitType="debounce"
          />
        </Table>
      </View>
    </Container>
  </Body>
</ModalFrame>
