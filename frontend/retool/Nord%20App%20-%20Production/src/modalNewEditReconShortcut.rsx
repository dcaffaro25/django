<ModalFrame
  id="modalNewEditReconShortcut"
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
  size="medium"
>
  <Header>
    <Text
      id="modalTitle39"
      value="### Reconciliation Shortcut"
      verticalAlign="center"
    />
    <Button
      id="modalCloseButton43"
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
        pluginId="modalNewEditReconShortcut"
        type="widget"
        waitMs="0"
        waitType="debounce"
      />
    </Button>
  </Header>
  <Body>
    <Form
      id="form16"
      footerPadding="4px 12px"
      headerPadding="4px 12px"
      initialData=""
      padding="12px"
      requireValidation={true}
      resetAfterSubmit={true}
      scroll={true}
      showBody={true}
      showBorder={false}
    >
      <Header>
        <Text id="formTitle29" value="#### Form title" verticalAlign="center" />
      </Header>
      <Body>
        <Select
          id="scopeInput"
          emptyMessage="No options"
          formDataKey="scope"
          itemMode="static"
          label="Scope"
          labelPosition="top"
          labels={null}
          overlayMaxHeight={375}
          placeholder="Select an option"
          required={true}
          showSelectionIndicator={true}
          value={
            '{{ selectedReconConfig.value ? selectedReconConfig.value[self.formDataKey] : "company" }}'
          }
          values={null}
        >
          <Option id="00030" value="global" />
          <Option id="00031" value="company" />
          <Option id="00032" value="user" />
          <Option
            id="cd51e"
            disabled={false}
            hidden={false}
            label="company & user"
            value="company_user"
          />
        </Select>
        <TextInput
          id="nameInput16"
          formDataKey="name"
          label="Name"
          labelPosition="top"
          placeholder="Enter value"
          required={true}
          value={
            '{{ selectedReconConfig.value ? selectedReconConfig.value[self.formDataKey] : "" }}'
          }
        />
        <TextArea
          id="descriptionInput5"
          autoResize={true}
          formDataKey="description"
          label="Description"
          labelPosition="top"
          minLines={2}
          placeholder="Enter value"
          required={true}
          value={
            '{{ selectedReconConfig.value ? selectedReconConfig.value[self.formDataKey] : "" }}'
          }
        />
        <Select
          id="userInput"
          disabled={
            '{{ scopeInput.value == "global" || scopeInput.value == "company"}}'
          }
          emptyMessage="No options"
          formDataKey="user"
          itemMode="static"
          label="User"
          labelPosition="top"
          labels={null}
          overlayMaxHeight={375}
          placeholder="Select an option"
          showSelectionIndicator={true}
          value={
            '{{ scopeInput.value == "user" || scopeInput.value == "company_user" ?(selectedReconConfig.value ? selectedReconConfig.value[self.formDataKey] : "") : "" }}'
          }
          values={null}
        >
          <Option id="00030" value="Option 1" />
          <Option id="00031" value="Option 2" />
          <Option id="00032" value="Option 3" />
        </Select>
        <Select
          id="companyInput14"
          data="{{ clientes.data }}"
          disabled={
            '{{ scopeInput.value == "global" || scopeInput.value == "user"}}'
          }
          emptyMessage="No options"
          formDataKey="company"
          label="Company"
          labelPosition="top"
          labels="{{ item.name }}"
          overlayMaxHeight={375}
          placeholder="Select an option"
          showSelectionIndicator={true}
          value={
            '{{ scopeInput.value == "company" || scopeInput.value == "company_user" ?(selectedReconConfig.value ? selectedReconConfig.value[self.formDataKey] : "") : "" }}'
          }
          values="{{ item.id }}"
        />
        <NumberInput
          id="maxGroupSizeInput2"
          currency="USD"
          formDataKey="max_group_size_bank"
          inputValue={0}
          label="Max bank group size"
          labelPosition="top"
          min="1"
          placeholder="Enter value"
          required={true}
          showSeparators={true}
          showStepper={true}
          value="{{ selectedReconConfig.value ? selectedReconConfig.value[self.formDataKey] : 1 }}"
        />
        <NumberInput
          id="maxGroupSizeInput"
          currency="USD"
          formDataKey="max_group_size_book"
          inputValue={0}
          label="Max book group size"
          labelPosition="top"
          min="1"
          placeholder="Enter value"
          required={true}
          showSeparators={true}
          showStepper={true}
          value="{{ selectedReconConfig.value ? selectedReconConfig.value[self.formDataKey] : 1 }}"
        />
        <NumberInput
          id="amountToleranceInput"
          currency="USD"
          formDataKey="amount_tolerance"
          inputValue={0}
          label="Amount tolerance"
          labelPosition="top"
          min="0"
          placeholder="Enter value"
          required={true}
          showSeparators={true}
          showStepper={true}
          value="{{ selectedReconConfig.value ? selectedReconConfig.value[self.formDataKey] : 0 }}"
        />
        <NumberInput
          id="dateToleranceDaysInput"
          currency="USD"
          formDataKey="avg_date_delta_days"
          inputValue={0}
          label="Date tolerance days"
          labelPosition="top"
          min="0"
          placeholder="Enter value"
          required={true}
          showSeparators={true}
          showStepper={true}
          value="{{ selectedReconConfig.value ? selectedReconConfig.value[self.formDataKey] : 0 }}"
        />
        <NumberInput
          id="minConfidenceInput"
          currency="USD"
          formDataKey="min_confidence"
          inputValue={0}
          label="Min confidence"
          labelPosition="top"
          max="1"
          min="0"
          placeholder="Enter value"
          required={true}
          showSeparators={true}
          showStepper={true}
          value="{{ selectedReconConfig.value ? selectedReconConfig.value[self.formDataKey] : 0.8 }}"
        />
        <NumberInput
          id="minConfidenceInput2"
          currency="USD"
          formDataKey="max_suggestions"
          inputValue={0}
          label="Max suggestions"
          labelPosition="top"
          max="10000"
          min="1"
          placeholder="Enter value"
          required={true}
          showSeparators={true}
          showStepper={true}
          value="{{ selectedReconConfig.value ? selectedReconConfig.value[self.formDataKey] : 0 }}"
        />
        <NumberInput
          id="dateToleranceDaysInput3"
          currency="USD"
          formDataKey="amount_weight"
          inputValue={0}
          label="Amount Weight"
          labelPosition="top"
          max="1"
          min="0"
          placeholder="Enter value"
          required={true}
          showSeparators={true}
          showStepper={true}
          value="{{ selectedReconConfig.value ? selectedReconConfig.value[self.formDataKey] : 0 }}"
        />
        <NumberInput
          id="dateToleranceDaysInput2"
          currency="USD"
          formDataKey="group_span_days"
          inputValue={0}
          label="Group Span Days"
          labelPosition="top"
          min="0"
          placeholder="Enter value"
          required={true}
          showSeparators={true}
          showStepper={true}
          value="{{ selectedReconConfig.value ? selectedReconConfig.value[self.formDataKey] : 0 }}"
        />
        <NumberInput
          id="minConfidenceInput3"
          currency="USD"
          formDataKey="date_weight"
          inputValue={0}
          label="Date Weight"
          labelPosition="top"
          max="1"
          min="0"
          placeholder="Enter value"
          required={true}
          showSeparators={true}
          showStepper={true}
          value="{{ selectedReconConfig.value ? selectedReconConfig.value[self.formDataKey] : 0 }}"
        />
        <NumberInput
          id="dateToleranceDaysInput5"
          currency="USD"
          formDataKey="soft_time_limit_seconds"
          inputValue={0}
          label="Time Limit (seconds)"
          labelPosition="top"
          min="0"
          placeholder="Enter value"
          required={true}
          showSeparators={true}
          showStepper={true}
          value="{{ selectedReconConfig.value ? selectedReconConfig.value[self.formDataKey] : 0 }}"
        />
        <NumberInput
          id="dateToleranceDaysInput4"
          currency="USD"
          formDataKey="embedding_weight"
          inputValue={0}
          label="Description Weight"
          labelPosition="top"
          max="1"
          min="0"
          placeholder="Enter value"
          required={true}
          showSeparators={true}
          showStepper={true}
          value="{{ selectedReconConfig.value ? selectedReconConfig.value[self.formDataKey] : 0 }}"
        />
        <NumberInput
          id="minConfidenceInput4"
          currency="USD"
          formDataKey="currency_weight"
          inputValue={0}
          label="Currency Weight"
          labelPosition="top"
          max="1"
          min="0"
          placeholder="Enter value"
          required={true}
          showSeparators={true}
          showStepper={true}
          value="{{ selectedReconConfig.value ? selectedReconConfig.value[self.formDataKey] : 0 }}"
        />
        <Switch
          id="switch8"
          formDataKey="allow_mixed_signs"
          label="Allow Mixed Signs?"
          value="{{ selectedReconConfig.value ? selectedReconConfig.value[self.formDataKey] : false }}"
        />
        <Include src="./group77.rsx" />
      </Body>
    </Form>
  </Body>
  <Footer>
    <Button id="formButton22" submitTargetId="form16" text="Submit">
      <Event
        event="click"
        method="run"
        params={{
          map: {
            src: "(String(ReconConfig_mode.value||'new').toLowerCase()==='edit'\n    ? ReconConfig_edit.trigger()\n    : ReconConfig_new.trigger()\n).then(()=>Promise.all([ReconConfig_get.trigger()]))\n .then(()=>{ modalNewEditReconShortcut.hide(); utils.showNotification({title:'Saved', intent:'success'}) })\n .catch(e=>utils.showNotification({title:'Save failed', description:String(e), intent:'danger'})) \n",
          },
        }}
        pluginId=""
        type="script"
        waitMs="0"
        waitType="debounce"
      />
    </Button>
  </Footer>
  <Event
    event="show"
    method="run"
    params={{
      map: {
        src: '(async () => {\n  try {\n    console.log("[LoadRuleFilters] open modal");\n\n    const cfg = selectedReconConfig.value;\n    if (!cfg) {\n      console.warn("[LoadRuleFilters] selectedReconConfig is empty");\n      utils.showNotification({ title: "No config selected", description: "Nothing to load.", intent: "warning" });\n      return;\n    }\n\n    const normalize = (stack, label) => {\n      // Accept {operator, filters[]} or a raw array\n      const arr = Array.isArray(stack?.filters) ? stack.filters : (Array.isArray(stack) ? stack : []);\n      const operator = (stack?.operator || "and");\n      const filters = arr\n        .filter(f => f && (f.columnId || f.key || f.column))\n        .map((f, i) => ({\n          id: f?.id ?? `${label}-${i}-${Date.now()}`,\n          columnId: f?.columnId ?? f?.key ?? f?.column ?? "",\n          operator: f?.operator || "includes",\n          value: f?.value,\n          disabled: !!f?.disabled\n        }));\n      return { operator, filters };\n    };\n\n    const bankStack = normalize(cfg.bank_filters, "bank");\n    const bookStack = normalize(cfg.book_filters, "book");\n\n    console.log("[LoadRuleFilters] bankStack:", bankStack);\n    console.log("[LoadRuleFilters] bookStack:", bookStack);\n\n    // Apply to Filter components\n    if (typeof filterBank.setFilterStack === "function") {\n      await filterBank.setFilterStack(bankStack);\n    } else if (typeof filterBank.setValue === "function") {\n      await filterBank.setValue(bankStack);\n    } else {\n      console.warn("[LoadRuleFilters] filterBank not settable");\n    }\n\n    if (typeof filterBook.setFilterStack === "function") {\n      await filterBook.setFilterStack(bookStack);\n    } else if (typeof filterBook.setValue === "function") {\n      await filterBook.setValue(bookStack);\n    } else {\n      console.warn("[LoadRuleFilters] filterBook not settable");\n    }\n\n    // (Optional) keep tables in sync with the filters you just applied\n    if (typeof tableBank.setFilterStack === "function") await tableBank.setFilterStack(bankStack);\n    if (typeof tableBook.setFilterStack === "function") await tableBook.setFilterStack(bookStack);\n\n    utils.showNotification({\n      title: "Filters loaded",\n      description: `bank: ${bankStack.filters.length} • book: ${bookStack.filters.length}`,\n      intent: "success"\n    });\n  } catch (err) {\n    console.error("[LoadRuleFilters] error:", err);\n    utils.showNotification({ title: "Failed to load filters", description: String(err?.message || err), intent: "danger" });\n  }\n})()',
      },
    }}
    pluginId=""
    type="script"
    waitMs="0"
    waitType="debounce"
  />
</ModalFrame>
