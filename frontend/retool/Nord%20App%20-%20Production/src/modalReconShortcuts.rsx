<ModalFrame
  id="modalReconShortcuts"
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
  size="large"
>
  <Header>
    <Text
      id="modalTitle46"
      value="### Reconciliation Shortcuts"
      verticalAlign="center"
    />
    <Button
      id="modalCloseButton51"
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
        pluginId="modalReconShortcuts"
        type="widget"
        waitMs="0"
        waitType="debounce"
      />
    </Button>
  </Header>
  <Body>
    <Container
      id="tabbedContainer5"
      currentViewKey="{{ self.viewKeys[0] }}"
      footerPadding="4px 12px"
      headerPadding="4px 12px"
      padding="12px"
      showBody={true}
      showHeader={true}
    >
      <Header>
        <Tabs
          id="tabs5"
          itemMode="static"
          navigateContainer={true}
          targetContainerId="tabbedContainer5"
          value="{{ self.values[0] }}"
        >
          <Option id="00030" value="Tab 1" />
          <Option id="00031" value="Tab 2" />
          <Option id="00032" value="Tab 3" />
        </Tabs>
      </Header>
      <View id="00031" viewKey="Pipeline">
        <Table
          id="tableReconPipes"
          actionsOverflowPosition={1}
          cellSelection="none"
          clearChangesetOnSave={true}
          data="{{  ReconPipe_get.data}}"
          defaultSelectedRow={{ mode: "index", indexType: "display", index: 0 }}
          dynamicRowHeights={true}
          emptyMessage="No rows found"
          enableSaveActions={true}
          primaryKeyColumnId="7ae1f"
          rowHeight="small"
          rowSelection="multiple"
          showBorder={true}
          showFooter={true}
          showHeader={true}
          toolbarPosition="bottom"
        >
          <Column
            id="7ae1f"
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
            id="d74ea"
            alignment="left"
            format="string"
            groupAggregationMode="none"
            key="company_name"
            label="Company name"
            placeholder="Enter value"
            position="center"
            size={100}
            summaryAggregationMode="none"
          />
          <Column
            id="65aad"
            alignment="left"
            cellTooltipMode="overflow"
            format="multilineString"
            formatOptions={{ automaticColors: true }}
            groupAggregationMode="none"
            key="stages"
            label="Stages"
            placeholder="Enter value"
            position="center"
            size={100}
            summaryAggregationMode="none"
            valueOverride={
              '{{\nArray.isArray(currentSourceRow.stages)\n  ? currentSourceRow.stages\n      .map(s => {\n        // tira um "(n)" que já venha no começo do config_name, se existir\n        const cleanName = (s.config_name || "").replace(/^\\(\\d+\\)\\s*/, "");\n        return `(${s.order}) ${cleanName}`;\n      })\n      .join("\\n")   // separador entre os estágios\n  : ""\n}}'
            }
          />
          <Column
            id="dc68a"
            alignment="left"
            format="string"
            groupAggregationMode="none"
            key="scope"
            label="Scope"
            placeholder="Enter value"
            position="center"
            size={100}
            summaryAggregationMode="none"
          />
          <Column
            id="57f34"
            alignment="left"
            format="string"
            groupAggregationMode="none"
            key="name"
            label="Name"
            placeholder="Enter value"
            position="center"
            size={100}
            summaryAggregationMode="none"
          />
          <Column
            id="9f54f"
            alignment="left"
            format="string"
            groupAggregationMode="none"
            key="description"
            label="Description"
            placeholder="Enter value"
            position="center"
            size={100}
            summaryAggregationMode="none"
          />
          <Column
            id="b2770"
            alignment="right"
            editableOptions={{ showStepper: true }}
            format="percent"
            formatOptions={{ showSeparators: true, notation: "standard" }}
            groupAggregationMode="average"
            key="auto_apply_score"
            label="Auto apply score"
            placeholder="Enter value"
            position="center"
            size={100}
            summaryAggregationMode="none"
          />
          <Column
            id="b9a51"
            alignment="right"
            editableOptions={{ showStepper: true }}
            format="decimal"
            formatOptions={{ showSeparators: true, notation: "standard" }}
            groupAggregationMode="sum"
            key="max_suggestions"
            label="Max suggestions"
            placeholder="Enter value"
            position="center"
            size={100}
            summaryAggregationMode="none"
          />
          <Column
            id="58385"
            alignment="right"
            editableOptions={{ showStepper: true }}
            format="decimal"
            formatOptions={{ showSeparators: true, notation: "standard" }}
            groupAggregationMode="sum"
            key="soft_time_limit_seconds"
            label="Soft time limit seconds"
            placeholder="Enter value"
            position="center"
            size={100}
            summaryAggregationMode="none"
          />
          <Column
            id="702a1"
            alignment="left"
            format="boolean"
            groupAggregationMode="none"
            key="is_default"
            label="Is default"
            placeholder="Enter value"
            position="center"
            size={100}
            summaryAggregationMode="none"
          />
          <Column
            id="1289b"
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
            id="e47f0"
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
            id="308c1"
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
            id="9eea7"
            alignment="right"
            editableOptions={{ showStepper: true }}
            format="decimal"
            formatOptions={{ showSeparators: true, notation: "standard" }}
            groupAggregationMode="sum"
            key="user"
            label="User"
            placeholder="Enter value"
            position="center"
            size={100}
            summaryAggregationMode="none"
          />
          <Column
            id="313b9"
            alignment="left"
            format="string"
            groupAggregationMode="none"
            key="user_name"
            label="User name"
            placeholder="Enter value"
            position="center"
            size={100}
            summaryAggregationMode="none"
          />
          <Action id="b3751" icon="bold/interface-edit-pencil" label="edit">
            <Event
              event="clickAction"
              method="run"
              params={{
                map: {
                  src: '(async () => {\n  const id = currentSourceRow?.ID ?? currentSourceRow?.id;\n  if (id == null) {\n    utils.showNotification({ title: "No ID", description: "Row has no ID.", intent: "warning" });\n    return;\n  }\n\n  // refresh configs\n  const resp = await ReconConfig_get.trigger();\n  const arr = Array.isArray(resp?.data) ? resp.data : (Array.isArray(resp) ? resp : (ReconConfig_get.data || []));\n  const cfg = (arr || []).find(x => String(x.id) === String(id));\n\n  if (!cfg) {\n    utils.showNotification({ title: "Not found", description: `Config ${id} not in ReconConfig_get.`, intent: "danger" });\n    return;\n  }\n\n  // deep-clone to avoid mutating the query data\n  const value = JSON.parse(JSON.stringify({\n    ...cfg,\n    bank_filters: cfg.bank_filters ?? { filters: [], operator: "and" },\n    book_filters: cfg.book_filters ?? { filters: [], operator: "and" }\n  }));\n\n  await selectedReconConfig.setValue(value);\n  await ReconConfig_mode.setValue("edit");\n  modalNewEditReconShortcut.show();\n})();\n',
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
              pluginId="tableReconPipes"
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
              pluginId="tableReconPipes"
              type="widget"
              waitMs="0"
              waitType="debounce"
            />
          </ToolbarButton>
          <ToolbarButton
            id="3fca0"
            icon="bold/interface-add-1"
            label="New Shortcut"
            type="custom"
          >
            <Event
              event="clickToolbar"
              method="run"
              params={{
                map: {
                  src: 'await selectedReconConfig.setValue("");\nReconConfig_mode.setValue("new");\nmodalNewEditReconShortcut.show();',
                },
              }}
              pluginId=""
              type="script"
              waitMs="0"
              waitType="debounce"
            />
          </ToolbarButton>
        </Table>
      </View>
      <View id="00030" viewKey="Single">
        <Table
          id="tableReconShortcuts"
          actionsOverflowPosition={1}
          autoColumnWidth={true}
          cellSelection="none"
          clearChangesetOnSave={true}
          data={
            "{{ (() => {\n  const d = ReconConfig_get.data || [];\n\n  const sym = o => ({\n    includes:'~', contains:'~', equals:'=', eq:'=', startswith:'^', endswith:'$', gt:'>', gte:'≥', lt:'<', lte:'≤'\n  })[String(o||'').toLowerCase()] || String(o||'');\n\n  const esc = s => String(s ?? '').replaceAll('\"','\\\\\"');\n\n  const ctx = r => {\n    const s = (r.scope || 'global').toLowerCase();\n    if (s === 'company') return `**company**: ${r.company_name ?? r.company ?? '—'}`;\n    if (s === 'user')    return `**user**: ${r.user_name   ?? r.user    ?? '—'}`;\n    return '**global**';\n  };\n\n  const filt = (f,label) => {\n    const arr = Array.isArray(f?.filters) ? f.filters.filter(x => !x?.disabled) : [];\n    if (!arr.length) return '';\n    const parts = arr.slice(0,2).map(x => `*${x.columnId || '?'}* ${sym(x.operator)} \\`${esc(x.value)}\\``);\n    const joiner = ` ${(f?.operator || 'and').toUpperCase()} `;\n    return `${label}: ${parts.join(joiner)}${arr.length > 2 ? ` (+${arr.length-2})` : ''}`;\n  };\n\n  const filtersCol = r => {\n    const s = [filt(r.bank_filters,'**bank**'), filt(r.book_filters,'**book**')].filter(Boolean).join(' \\\\| ');\n    return s || '—';\n  };\n\n  const match = r => {\n    const strat = (r.strategy || '—').replace(/optimized/i,'opt');\n    const def = r.is_default ? ' ✅' : '';\n    return `**${strat}**${def} • \\`g=${r.max_group_size ?? '—'}\\` • \\`±amt=${r.amount_tolerance ?? '—'}\\` • \\`±d=${r.date_tolerance_days ?? '—'}\\` • \\`min=${r.min_confidence ?? '—'}\\` • \\`max=${r.max_suggestions ?? '—'}\\``;\n  };\n\n  return d.map(r => {\n    const c = (stateRuleCounts.value || {})[r.id] || {};\n    const cnt = `${c.books ?? '—'} // ${c.banks ?? '—'}`;\n    return {\n      ID: r.id,\n      Name: r.name,\n      Context: ctx(r),\n      Filters: filtersCol(r),\n      Matching: match(r),\n      'Books | Banks': cnt,\n      Updated: (r.updated_at || r.created_at || '').slice(0,10),\n    };\n  });\n})() }}\n"
          }
          defaultSelectedRow={{ mode: "index", indexType: "display", index: 0 }}
          emptyMessage="No rows found"
          enableSaveActions={true}
          rowHeight="small"
          rowSelection="multiple"
          showBorder={true}
          showFooter={true}
          showHeader={true}
          toolbarPosition="bottom"
        >
          <Column
            id="0f52e"
            alignment="right"
            editableOptions={{ showStepper: true }}
            format="decimal"
            formatOptions={{ showSeparators: true, notation: "standard" }}
            groupAggregationMode="sum"
            key="ID"
            label="Id"
            placeholder="Enter value"
            position="center"
            size={29.265625}
            summaryAggregationMode="none"
          />
          <Column
            id="8ce82"
            alignment="left"
            format="string"
            groupAggregationMode="none"
            key="Name"
            label="Name"
            placeholder="Enter value"
            position="center"
            size={140.5}
            summaryAggregationMode="none"
          />
          <Column
            id="0e82c"
            alignment="left"
            cellTooltipMode="overflow"
            format="markdown"
            groupAggregationMode="none"
            key="Context"
            label="Context"
            placeholder="Enter value"
            position="center"
            size={129.5625}
            summaryAggregationMode="none"
          />
          <Column
            id="2a717"
            alignment="left"
            cellTooltipMode="overflow"
            format="markdown"
            groupAggregationMode="none"
            key="Filters"
            label="Filters"
            placeholder="Enter value"
            position="center"
            size={926.734375}
            summaryAggregationMode="none"
          />
          <Column
            id="9a6cf"
            alignment="left"
            cellTooltipMode="overflow"
            format="markdown"
            groupAggregationMode="none"
            key="Matching"
            label="Matching"
            placeholder="Enter value"
            position="center"
            size={352.453125}
            summaryAggregationMode="none"
          />
          <Column
            id="ea672"
            alignment="left"
            format="date"
            groupAggregationMode="none"
            key="Updated"
            label="Updated"
            placeholder="Enter value"
            position="center"
            size={92.671875}
            summaryAggregationMode="none"
          />
          <Column
            id="a6512"
            alignment="left"
            format="string"
            formatOptions={{ automaticColors: true }}
            groupAggregationMode="none"
            key="Books | Banks"
            label="Books | Banks"
            placeholder="Enter value"
            position="center"
            size={95.984375}
            summaryAggregationMode="none"
            valueOverride="{{ _.startCase(item) }}"
          />
          <Action id="b3751" icon="bold/interface-edit-pencil" label="edit">
            <Event
              event="clickAction"
              method="run"
              params={{
                map: {
                  src: '(async () => {\n  const id = currentSourceRow?.ID ?? currentSourceRow?.id;\n  if (id == null) {\n    utils.showNotification({ title: "No ID", description: "Row has no ID.", intent: "warning" });\n    return;\n  }\n\n  // refresh configs\n  const resp = await ReconConfig_get.trigger();\n  const arr = Array.isArray(resp?.data) ? resp.data : (Array.isArray(resp) ? resp : (ReconConfig_get.data || []));\n  const cfg = (arr || []).find(x => String(x.id) === String(id));\n\n  if (!cfg) {\n    utils.showNotification({ title: "Not found", description: `Config ${id} not in ReconConfig_get.`, intent: "danger" });\n    return;\n  }\n\n  // deep-clone to avoid mutating the query data\n  const value = JSON.parse(JSON.stringify({\n    ...cfg,\n    bank_filters: cfg.bank_filters ?? { filters: [], operator: "and" },\n    book_filters: cfg.book_filters ?? { filters: [], operator: "and" }\n  }));\n\n  await selectedReconConfig.setValue(value);\n  await ReconConfig_mode.setValue("edit");\n  modalNewEditReconShortcut.show();\n})();\n',
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
              pluginId="tableReconShortcuts"
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
              pluginId="tableReconShortcuts"
              type="widget"
              waitMs="0"
              waitType="debounce"
            />
          </ToolbarButton>
          <ToolbarButton
            id="3fca0"
            icon="bold/interface-add-1"
            label="New Shortcut"
            type="custom"
          >
            <Event
              event="clickToolbar"
              method="run"
              params={{
                map: {
                  src: 'await selectedReconConfig.setValue("");\nReconConfig_mode.setValue("new");\nmodalNewEditReconShortcut.show();',
                },
              }}
              pluginId=""
              type="script"
              waitMs="0"
              waitType="debounce"
            />
          </ToolbarButton>
        </Table>
      </View>
    </Container>
  </Body>
  <Footer>
    <Container
      id="group76"
      _gap="0px"
      _justify="center"
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
        <Button id="button56" text="Run Selected">
          <Event
            enabled={'{{ tabs5.value =="Single" }}'}
            event="click"
            method="run"
            params={{
              map: {
                src: '(async () => {\n  // 0) Refresh configs and index by ID\n  const cfgResp = await ReconConfig_get.trigger();\n  const cfgArr = (cfgResp && (cfgResp.data || cfgResp)) || ReconConfig_get.data || [];\n  const cfgById = new Map((Array.isArray(cfgArr) ? cfgArr : []).map(x => [String(x.id), x]));\n\n  // 1) Selected rule IDs from the table (column is "ID")\n  const sel = tableReconShortcuts.selectedRows || [];\n  const ruleIds = Array.from(new Set(sel.map(r => String(r.ID)).filter(Boolean)));\n  if (!ruleIds.length) {\n    utils.showNotification({ title: "No rules selected", description: "Pick one or more rules.", intent: "warning" });\n    return;\n  }\n\n  // 2) Switch: Relative vs Absolute\n  const relative = !!(typeof switchRelativeFilterRun !== "undefined" ? switchRelativeFilterRun.value : false);\n  const autoMatch = !!(typeof switch3 !== "undefined" ? switch3.value : false);\n\n  // --- helpers ---\n  const delay = (ms) => new Promise(r => setTimeout(r, ms));\n  const normStack = (s) => {\n    const f = (s && s.filters) ? s.filters : [];\n    const op = (s && s.operator) ? s.operator : "and";\n    return { filters: Array.isArray(f) ? f : [], operator: op };\n  };\n  const hasActiveFilters = (s) => {\n    const n = normStack(s);\n    return n.filters.some(x => !x?.disabled && x?.value !== "" && x?.value != null);\n  };\n  const mergeStacks = (base, extra) => {\n    const b = normStack(base), e = normStack(extra);\n    const all = [...b.filters, ...e.filters].filter(x => !x?.disabled);\n    const seen = new Set();\n    const dedup = [];\n    for (const it of all) {\n      const key = `${it.columnId}|${(it.operator||\'\').toLowerCase()}|${JSON.stringify(it.value)}`;\n      if (!seen.has(key)) { seen.add(key); dedup.push(it); }\n    }\n    return { filters: dedup, operator: e.operator || b.operator || "and" };\n  };\n  const readStack = async (tbl) =>\n    (typeof tbl.getFilterStack === "function" ? await tbl.getFilterStack() : (tbl.filterStack ?? tbl.filters ?? null));\n\n  // 3) Capture BASELINE (filters + visible IDs) right now\n  const baselineBankStack = await readStack(tableBank);\n  const baselineBookStack = await readStack(tableBook);\n\n  const visBanks0 = await tableBank.getDisplayedData();\n  const baseBankIds = (Array.isArray(visBanks0) ? visBanks0 : Object.values(visBanks0 || {}))\n    .map(r => r.id).filter(x => x != null);\n\n  const visBooks0 = await tableBook.getDisplayedData();\n  const baseBookIds = (Array.isArray(visBooks0) ? visBooks0 : Object.values(visBooks0 || {}))\n    .map(r => r.id).filter(x => x != null);\n\n  // Apply a (possibly merged) stack, read IDs, then always restore baseline\n  const getIdsForRule = async (tbl, ruleStack, baselineStack, baselineIds) => {\n    const ruleHasFilters = hasActiveFilters(ruleStack);\n    if (!ruleHasFilters || typeof tbl.setFilterStack !== "function") {\n      // No rule filters -> use baseline snapshot\n      return baselineIds;\n    }\n    // Relative: merge baseline + rule; Absolute: use rule only\n    const stackToApply = relative ? mergeStacks(baselineStack, ruleStack) : normStack(ruleStack);\n    try {\n      await tbl.setFilterStack(stackToApply);\n      await delay(60); // let Retool apply filters\n      const vis = await tbl.getDisplayedData();\n      const rows = Array.isArray(vis) ? vis : Object.values(vis || {});\n      return rows.map(r => r.id).filter(x => x != null);\n    } finally {\n      if (typeof tbl.setFilterStack === "function") {\n        await tbl.setFilterStack(baselineStack || {});\n        await delay(10);\n      }\n    }\n  };\n\n  // 4) Run rules sequentially\n  const results = [];\n  for (const rid of ruleIds) {\n    if (rid === "new") {\n      results.push({ id: rid, name: "(new shortcut)", ok: false, skipped: true, error: "Skipped special \'new\' row" });\n      continue;\n    }\n    const cfg = cfgById.get(rid);\n    if (!cfg) {\n      results.push({ id: rid, name: "", ok: false, error: "Config not found in ReconConfig_get.data" });\n      continue;\n    }\n\n    try {\n      const bankIds = await getIdsForRule(tableBank, cfg.bank_filters, baselineBankStack, baseBankIds);\n      const bookIds = await getIdsForRule(tableBook, cfg.book_filters, baselineBookStack, baseBookIds);\n\n      const payload = {\n        config_id: cfg.id,\n        bank_ids: bankIds,\n        book_ids: bookIds,\n        max_suggestions: \ncfg.max_suggestions,      max_group_size_bank: cfg.max_group_size_bank,\n        max_group_size_book:\n cfg.max_group_size_book,        amount_tolerance: cfg.amount_tolerance,\n        avg_date_diff_days: cfg.date_tolerance_days,\n        group_date_span_days:5,\n        min_confidence: cfg.min_confidence,\n        date_weight: cfg.date_weight ?? 0.4,\n        amount_weight: cfg.amount_weight ?? 0.6,\n\n        auto_match_100: autoMatch\n      };\n\n      const res = await Reconciliation_execute.trigger({ additionalScope: { payload } });\n      const taskId = (res && (res.task_id || res.data?.task_id || res.result?.task_id)) || null;\n\n      // 🔁 If auto-match is ON, refresh these after each successful execute\n      if (autoMatch) {\n        try {\n          await Promise.all([\n            BookTransactions_get.trigger(),\n            BankTransactions_get.trigger(),\n            Conciliation_get.trigger()\n          ]);\n        } catch (e) {\n          // non-fatal; note in results\n          results.push({\n            id: cfg.id,\n            name: cfg.name || "",\n            ok: true,\n            task_id: taskId,\n            counts: { banks: bankIds.length, books: bookIds.length },\n            mode: relative ? "relative" : "absolute",\n            warn: `Refresh failed: ${String(e?.message || e)}`\n          });\n          continue;\n        }\n      }\n\n      modalReconCeleryQueue.show();\n      results.push({\n        id: cfg.id,\n        name: cfg.name || "",\n        ok: true,\n        task_id: taskId,\n        counts: { banks: bankIds.length, books: bookIds.length },\n        mode: relative ? "relative" : "absolute"\n      });\n    } catch (e) {\n      results.push({\n        id: cfg?.id ?? rid,\n        name: cfg?.name || "",\n        ok: false,\n        error: String(e?.message || e),\n        mode: relative ? "relative" : "absolute"\n      });\n    }\n  }\n\n  // 5) Restore baseline filters (defensive)\n  if (typeof tableBank.setFilterStack === "function") await tableBank.setFilterStack(baselineBankStack || {});\n  if (typeof tableBook.setFilterStack === "function") await tableBook.setFilterStack(baselineBookStack || {});\n\n  // 6) Refresh queue & show modal\n  await Promise.all([Queue_get.trigger(), QueueCount_get.trigger()]);\n\n  // 7) Summary popup\n  const ok = results.filter(r => r.ok).length;\n  const failed = results.filter(r => !r.ok && !r.skipped).length;\n  const skipped = results.filter(r => r.skipped).length;\n  const lines = results.map(r =>\n    `- ${r.ok ? "✅" : (r.skipped ? "⏭️" : "❌")} [${r.id}] ${r.name}` +\n    (r.task_id ? ` (task: ${r.task_id})` : "") +\n    ` — mode:${r.mode || (relative ? "relative" : "absolute")}` +\n    (r.counts ? ` • banks:${r.counts.banks} • books:${r.counts.books}` : "") +\n    (r.warn ? ` — ⚠ ${r.warn}` : "") +\n    (r.error ? ` — ${r.error}` : "")\n  ).join(\'\\n\');\n\n  utils.showNotification({\n    title: `Batch run (${relative ? "Relative" : "Absolute"}): ${ok} ok • ${failed} failed${skipped ? ` • ${skipped} skipped` : ""}`,\n    description: lines,\n    duration: 90\n  });\n})();\n',
              },
            }}
            pluginId=""
            type="script"
            waitMs="0"
            waitType="debounce"
          />
          <Event
            enabled={'{{ tabs5.value == "Pipeline" }}'}
            event="click"
            method="run"
            params={{
              map: {
                src: '(async () => {\n  // 1) Pipelines selecionados na tabela\n  const sel = tableReconPipes.selectedRows || [];\n  if (!sel.length) {\n    utils.showNotification({\n      title: "Nenhum pipeline selecionado",\n      description: "Selecione um ou mais pipelines na tabela.",\n      intent: "warning"\n    });\n    return;\n  }\n\n  // 2) Auto-match (se ainda fizer sentido)\n  const autoMatch = !!(typeof switch3 !== "undefined" ? switch3.value : false);\n\n  const results = [];\n\n  // 3) Rodar cada pipeline selecionado\n  for (const row of sel) {\n    // ajusta aqui se o ID na tabela vier como outra chave (ex: row.ID)\n    const pipelineId = row.id ?? row.ID ?? row.pipeline_id;\n\n    if (!pipelineId) {\n      results.push({\n        id: "??",\n        name: row.name || "",\n        ok: false,\n        error: "ID do pipeline não encontrado na linha selecionada"\n      });\n      continue;\n    }\n\n    try {\n      const res = await Reconciliation_execute.trigger({\n        additionalScope: {\n          payload: {\n            pipeline_id: pipelineId,\n            auto_match_100: autoMatch\n          }\n        }\n      });\n\n      const taskId =\n        (res && (res.task_id || res.data?.task_id || res.result?.task_id)) || null;\n\n      results.push({\n        id: pipelineId,\n        name: row.name || "",\n        ok: true,\n        task_id: taskId\n      });\n    } catch (e) {\n      results.push({\n        id: pipelineId,\n        name: row.name || "",\n        ok: false,\n        error: String(e?.message || e)\n      });\n    }\n  }\n\n  // 4) Atualizar fila e mostrar modal (se existir)\n  try {\n    await Promise.all([\n      Queue_get.trigger(),\n      QueueCount_get.trigger()\n    ]);\n  } catch (e) {\n    // se der erro aqui, só registra no resumo\n    results.push({\n      id: "queue-refresh",\n      name: "Refresh da fila",\n      ok: false,\n      error: `Erro ao atualizar fila: ${String(e?.message || e)}`\n    });\n  }\n\n  if (typeof modalReconCeleryQueue !== "undefined") {\n    modalReconCeleryQueue.show();\n  }\n\n  // 5) Notificação-resumo\n  const ok = results.filter(r => r.ok).length;\n  const failed = results.filter(r => !r.ok && !r.skipped).length;\n\n  const lines = results\n    .map(r =>\n      `- ${r.ok ? "✅" : "❌"} [${r.id}] ${r.name}` +\n      (r.task_id ? ` (task: ${r.task_id})` : "") +\n      (r.error ? ` — ${r.error}` : "")\n    )\n    .join("\\n");\n\n  utils.showNotification({\n    title: `Execução de pipelines: ${ok} ok • ${failed} erro(s)`,\n    description: lines,\n    duration: 60\n  });\n})();\n',
              },
            }}
            pluginId=""
            type="script"
            waitMs="0"
            waitType="debounce"
          />
        </Button>
        <Switch
          id="switch3"
          label={'Automatically Match the "100% no Dupes"'}
          labelWrap={true}
        />
        <Switch
          id="switchRelativeFilterRun"
          label="Append Current
and Rule Filters"
          labelWrap={true}
        >
          <Event
            event="change"
            method="trigger"
            params={{}}
            pluginId="ReconCounts_compute"
            type="datasource"
            waitMs="0"
            waitType="debounce"
          />
        </Switch>
      </View>
    </Container>
  </Footer>
</ModalFrame>
