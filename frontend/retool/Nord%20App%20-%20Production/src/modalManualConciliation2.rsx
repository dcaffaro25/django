<ModalFrame
  id="modalManualConciliation2"
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
      id="modalTitle35"
      value="### Conciliação Manual"
      verticalAlign="center"
    />
    <Button
      id="modalCloseButton39"
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
        pluginId="modalManualConciliation2"
        type="widget"
        waitMs="0"
        waitType="debounce"
      />
    </Button>
  </Header>
  <Body>
    <Form
      id="form15"
      footerPadding="4px 12px"
      headerPadding="4px 12px"
      initialData=""
      padding="12px"
      requireValidation={true}
      resetAfterSubmit={true}
      scroll={true}
      showBody={true}
    >
      <Select
        id="companyInput13"
        data="{{ clientes.data }}"
        disabled="true"
        disabledByIndex="true"
        emptyMessage="No options"
        formDataKey="company"
        label="Company"
        labelPosition="top"
        labels="{{ item.name }}"
        overlayMaxHeight={375}
        placeholder="Select an option"
        required={true}
        showSelectionIndicator={true}
        value="{{ ClienteDropDown.selectedItem.id }}"
        values="{{ item.id }}"
      />
      <Multiselect
        id="bankTransactionsInput2"
        data="{{ BankTransactions_get2.data.filter(item => VisibleBankIds2.data.includes(item.id)) }}"
        emptyMessage="No options"
        formDataKey="bank_transactions"
        label="Bank transactions"
        labelPosition="top"
        labels={
          '{{ item.date }} _ {{  parseFloat(item.amount).toLocaleString("pt-BR", { minimumFractionDigits: 2, maximumFractionDigits: 2 }) }} _ {{ item.description }}'
        }
        overlayMaxHeight={375}
        placeholder="Select options"
        required={true}
        showSelectionIndicator={true}
        values="{{ item.id }}"
        wrapTags={true}
      />
      <Text
        id="text41"
        heightType="fixed"
        value={
          '**Total Amount: R$ {{ bankTransactionsInput2.selectedItems.reduce((sum, item) => sum + Number(item.amount), 0).toLocaleString("pt-BR", { minimumFractionDigits: 2, maximumFractionDigits: 2 }) }} \nDate: {{ (() => {\n  const s = bankTransactionsInput2.selectedItems.map(i => ({ a: Number(i.amount), d: new Date(i.date) }));\n  if (!s.length) return "No data selected";\n  const t = s.reduce((sum, i) => sum + i.a, 0);\n  const w = new Date(s.reduce((sum, i) => sum + i.d.getTime() * i.a, 0) / t);\n  const min = new Date(Math.min(...s.map(i => i.d))).toISOString().slice(0,10);\n  const max = new Date(Math.max(...s.map(i => i.d))).toISOString().slice(0,10);\n  const avg = w.toISOString().slice(0,10);\n  return `Min: ${min}, Max: ${max}, Weighted Avg: ${avg}`;\n})() }}**'
        }
      />
      <Divider id="divider20" />
      <Multiselect
        id="journalEntriesInput2"
        data="{{ Transactions_get5.data.filter(item => VisibleBookIds2.data.includes(item.id)) }}"
        emptyMessage="No options"
        formDataKey="journal_entries"
        label="Journal entries"
        labelPosition="top"
        labels={
          '{{ item.date }}  _  {{ parseFloat(item.amount).toLocaleString("pt-BR", { minimumFractionDigits: 2, maximumFractionDigits: 2 }) }}  _  {{ item.description }}'
        }
        overlayMaxHeight={375}
        placeholder="Select options"
        required={true}
        showSelectionIndicator={true}
        values="{{ item.id }}"
        wrapTags={true}
      />
      <Text
        id="text42"
        heightType="fixed"
        value={
          '**Total Amount: R$ {{ journalEntriesInput2.selectedItems.reduce((sum, item) => sum + Number(item.amount), 0).toLocaleString("pt-BR", { minimumFractionDigits: 2, maximumFractionDigits: 2 }) }} \nDate: {{ (() => {\n  const s = journalEntriesInput2.selectedItems.map(i => ({ a: Number(i.amount), d: new Date(i.date) }));\n  if (!s.length) return "No data selected";\n  const t = s.reduce((sum, i) => sum + i.a, 0);\n  const w = new Date(s.reduce((sum, i) => sum + i.d.getTime() * i.a, 0) / t);\n  const min = new Date(Math.min(...s.map(i => i.d))).toISOString().slice(0,10);\n  const max = new Date(Math.max(...s.map(i => i.d))).toISOString().slice(0,10);\n  const avg = w.toISOString().slice(0,10);\n  return `Min: ${min}, Max: ${max}, Weighted Avg: ${avg}`;\n})() }}**'
        }
      />
      <Divider id="divider18" />
      <Text
        id="text43"
        heightType="fixed"
        value={
          '**Match Quality: \nTotal Amount Difference: R$ {{ (bankTransactionsInput2.selectedItems.reduce((sum, item) => sum + Number(item.amount), 0) - journalEntriesInput2.selectedItems.reduce((sum, item) => sum + Number(item.amount), 0)).toLocaleString("pt-BR", { minimumFractionDigits: 2, maximumFractionDigits: 2 }) }} \n_**'
        }
      />
      <Divider id="divider19" />
      <TextInput
        id="statusInput2"
        disabled="true"
        formDataKey="status"
        label="Status"
        labelPosition="top"
        placeholder="Enter value"
        required={true}
      />
      <TextInput
        id="referenceInput2"
        formDataKey="reference"
        label="Reference"
        labelPosition="top"
        placeholder="Enter value"
        required={true}
      />
      <TextArea
        id="notesInput2"
        autoResize={true}
        formDataKey="notes"
        label="Notes"
        labelPosition="top"
        minLines={2}
        placeholder="Enter value"
        required={true}
      />
      <Checkbox
        id="isDeletedInput5"
        formDataKey="is_deleted"
        label="Is deleted"
        labelWidth="100"
      />
    </Form>
  </Body>
  <Footer>
    <Button id="formButton14" submitTargetId="" text="Submit">
      <Event
        event="click"
        method="run"
        params={{
          map: {
            src: '// Get selected IDs\nconst selectedBankTx = bankTransactionsInput2.selectedItems || [];\nconst selectedJournalEntries = journalEntriesInput2.selectedItems || [];\n\n// Fallback logic\nconst hasSelection = selectedBankTx.length > 0 || selectedJournalEntries.length > 0;\n\n\nconst bank_transaction_ids = selectedBankTx.length > 0\n  ? selectedBankTx.map(item => item.id)\n  : fallbackBankIds;\n\nconst journal_entry_ids = selectedJournalEntries.length > 0\n  ? selectedJournalEntries.map(item => item.id)\n  : fallbackJournalIds;\n\n// Build payload\nconst transformedItem = {\n  matches: [\n    {\n      bank_transaction_ids,\n      journal_entry_ids\n    }\n  ],\n  adjustment_side: "bank",\n  reference: "Reconciliation batch 1",\n  notes: "Matched using high confidence scores"\n};\nconsole.log(transformedItem); \n// Trigger the API\nMatchRecords_post2.trigger({\n  additionalScope: {\n    content: transformedItem\n  },\n  onSuccess: () => {\n    // Remove matched items from ReconciliationMatches\n    const updatedMatches = ReconciliationMatches2.value.filter(item => {\n      const sameBank = JSON.stringify(item.bank_ids) === JSON.stringify(bank_transaction_ids);\n      const sameJournal = JSON.stringify(item.journal_entries_ids) === JSON.stringify(journal_entry_ids);\n      return !(sameBank && sameJournal);\n    });\n\n    ReconciliationMatches2.setValue(updatedMatches);\n\n    // Optionally clear selections\n    bankTransactionsInput2.clear();\n    journalEntriesInput2.clear();\n\n    utils.showNotification({\n      title: "Matches submitted successfully",\n      intent: "success"\n    });\n  }\n});',
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
