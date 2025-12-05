<Screen
  id="Transacoes"
  _customShortcuts={[]}
  _hashParams={[]}
  _searchParams={[]}
  browserTitle=""
  title="  Transações"
  urlSlug="transacoes"
  uuid="0ded4744-b8a6-4477-919b-4367c95feab3"
>
  <RESTQuery
    id="Entidades2"
    enableTransformer={true}
    isHidden={false}
    notificationDuration={4.5}
    query="/{{ tenant_subdomain.value }}/api/entities"
    resourceDisplayName="Tenant Specific"
    resourceName="e4a763c9-4f5e-4f5a-99f7-6a33454d4577"
    showSuccessToaster={false}
  />
  <RESTQuery
    id="query9"
    isHidden={false}
    query="/{{ tenant_subdomain.value }}/api/transactions"
    resourceDisplayName="Tenant Specific"
    resourceName="e4a763c9-4f5e-4f5a-99f7-6a33454d4577"
  />
  <RESTQuery
    id="bank_transactions"
    isHidden={false}
    query="/{{ tenant_subdomain.value }}/api/bank_transactions"
    resourceDisplayName="Tenant Specific"
    resourceName="e4a763c9-4f5e-4f5a-99f7-6a33454d4577"
  />
  <RESTQuery
    id="transactions"
    isHidden={false}
    query="/{{ tenant_subdomain.value }}/api/transactions"
    resourceDisplayName="Tenant Specific"
    resourceName="e4a763c9-4f5e-4f5a-99f7-6a33454d4577"
  />
  <RESTQuery
    id="journal_entries"
    isHidden={false}
    query="/{{ ClienteDropDown.value }}/api/journal_entries"
    resourceDisplayName="Tenant Specific"
    resourceName="e4a763c9-4f5e-4f5a-99f7-6a33454d4577"
  />
  <Function
    id="transformer1"
    funcBody={include("../lib/transformer1.js", "string")}
    runBehavior="debounced"
  />
  <RESTQuery
    id="transactions_filtered"
    isHidden={false}
    isMultiplayerEdited={false}
    query="/{{ ClienteDropDown.value }}/api/transactions/filtered?status={{ TransactionStatusSelect.value }}"
    resourceDisplayName="Tenant Specific"
    resourceName="e4a763c9-4f5e-4f5a-99f7-6a33454d4577"
  />
  <connectResource id="query14" _componentId="select1" />
  <RESTQuery
    id="query15"
    isHidden={false}
    query="currencies"
    resourceDisplayName="Geral"
    resourceName="ba47a497-4b7f-4065-b31f-b0a35d106095"
  />
  <connectResource id="query17" _componentId="select2" />
  <RESTQuery
    id="schemaTransaction"
    isHidden={false}
    query="/{{ ClienteDropDown.value }}/api/schema/transaction/"
    resourceDisplayName="Tenant Specific"
    resourceName="e4a763c9-4f5e-4f5a-99f7-6a33454d4577"
  />
  <RESTQuery
    id="schemaJournalEntry"
    isHidden={false}
    isMultiplayerEdited={false}
    query="/{{ ClienteDropDown.value }}/api/schema/journal-entry/"
    resourceDisplayName="Tenant Specific"
    resourceName="e4a763c9-4f5e-4f5a-99f7-6a33454d4577"
  />
  <connectResource id="query20" _componentId="select5" />
  <State id="variable4" />
  <JavascriptQuery
    id="ModalFrame2Show"
    isHidden={false}
    notificationDuration={4.5}
    resourceName="JavascriptQuery"
    showSuccessToaster={false}
  >
    <Event
      event="success"
      method="show"
      params={{ ordered: [] }}
      pluginId="modalFrame2"
      type="widget"
      waitMs="0"
      waitType="debounce"
    />
  </JavascriptQuery>
  <JavascriptQuery
    id="updateJournalEntryQuery"
    isHidden={false}
    notificationDuration={4.5}
    query={include("../lib/updateJournalEntryQuery.js", "string")}
    resourceName="JavascriptQuery"
    showSuccessToaster={false}
  />
  <Include src="./modalFrame2.rsx" />
  <Frame
    id="$main3"
    enableFullBleed={false}
    isHiddenOnDesktop={false}
    isHiddenOnMobile={false}
    padding="8px 12px"
    sticky={null}
    type="main"
  >
    <Filter id="filter1" linkedTableId="table5" linkToTable={true} />
    <Container
      id="stack1"
      _flexWrap={true}
      _gap="0px"
      _type="stack"
      footerPadding="4px 12px"
      headerPadding="4px 12px"
      padding="12px"
      showBody={true}
    >
      <View id="13f45" viewKey="View 1">
        <Container
          id="group3"
          _gap="0px"
          footerPadding="4px 12px"
          headerPadding="4px 12px"
          margin="0"
          padding="0"
          showBody={true}
          showBorder={false}
          style={{ ordered: [{ background: "rgba(255, 255, 255, 0)" }] }}
        >
          <View id="ade66" viewKey="View 1">
            <Text
              id="text1"
              style={{
                ordered: [
                  { fontSize: "h5Font" },
                  { fontWeight: "h5Font" },
                  { fontFamily: "h5Font" },
                ],
              }}
              value="Transações"
              verticalAlign="center"
            />
            <Table
              id="table5"
              actionsOverflowPosition={3}
              autoColumnWidth={true}
              cellSelection="none"
              clearChangesetOnSave={true}
              data="{{ transactions_filtered.data }}"
              defaultSelectedRow={{
                mode: "none",
                indexType: "display",
                index: 0,
              }}
              emptyMessage="No rows found"
              enableExpandableRows={true}
              enableSaveActions={true}
              linkedFilterId="filter1"
              rowHeight="medium"
              showBorder={true}
              showFooter={true}
              showHeader={true}
              style={{
                filterBackground: "surfacePrimary",
                headerBackground: "primary",
                accent: "tertiary",
              }}
              toolbarPosition="bottom"
            >
              <Include src="./table5ExpandedRow.rsx" />
              <Column
                id="a70a2"
                alignment="right"
                editableOptions={{ showStepper: true }}
                format="decimal"
                formatOptions={{ showSeparators: true, notation: "standard" }}
                groupAggregationMode="sum"
                hidden="false"
                key="id"
                label="ID"
                placeholder="Enter value"
                position="left"
                summaryAggregationMode="none"
              />
              <Column
                id="93e40"
                alignment="left"
                format="date"
                groupAggregationMode="none"
                key="date"
                label="Date"
                placeholder="Enter value"
                position="left"
              />
              <Column
                id="ac7b9"
                alignment="left"
                format="string"
                groupAggregationMode="none"
                key="description"
                label="Description"
                placeholder="Enter value"
                position="left"
              />
              <Column
                id="513ae"
                alignment="right"
                editableOptions={{ showStepper: true }}
                format="decimal"
                formatOptions={{ showSeparators: true, notation: "standard" }}
                groupAggregationMode="sum"
                key="amount"
                label="Amount"
                placeholder="Enter value"
                position="center"
              />
              <Column
                id="8757f"
                alignment="left"
                format="tag"
                formatOptions={{ automaticColors: true }}
                groupAggregationMode="none"
                key="state"
                label="Status"
                placeholder="Select option"
                position="right"
              />
              <Column
                id="c162f"
                alignment="right"
                editableOptions={{ showStepper: true }}
                format="decimal"
                formatOptions={{ showSeparators: true, notation: "standard" }}
                groupAggregationMode="sum"
                key="company"
                label="Company"
                placeholder="Enter value"
                position="center"
              />
              <Column
                id="44039"
                alignment="right"
                editableOptions={{ showStepper: true }}
                format="decimal"
                formatOptions={{ showSeparators: true, notation: "standard" }}
                groupAggregationMode="sum"
                key="currency"
                label="Currency"
                placeholder="Enter value"
                position="center"
              />
              <Column
                id="7b463"
                alignment="left"
                cellTooltipMode="overflow"
                format="tags"
                formatOptions={{ automaticColors: true }}
                groupAggregationMode="none"
                hidden="true"
                key="journal_entries"
                label="Journal entries"
                placeholder="Select options"
                position="center"
                summaryAggregationMode="none"
              />
              <Action
                id="d3481"
                icon="bold/legal-justice-scale-1"
                label="Cravar"
              />
              <Action
                id="6caa4"
                icon="bold/interface-delete-bin-2"
                label="Deletar"
              />
              <Action
                id="0ddb4"
                icon="bold/interface-edit-write-1"
                label="Editar"
              >
                <Event
                  event="clickAction"
                  method="run"
                  params={{
                    ordered: [
                      {
                        src: '// Step 1: Get the selected row data from table5\nconsole.log("teste inicio");\nconst selectedRowData = table5.selectedRow;\n\n// Step 2: Check if a row is selected\nif (!selectedRowData) {\n  utils.showNotification({ title: "Error", message: "Please select a row to edit.", type: "error" });\n  return;\n}\n\n// Step 3: Construct the JSON object to update jsonEditor1\nconst jsonObject = {\n  transaction: {\n    company: selectedRowData.company, // Extract from table5 row\n    date: selectedRowData.date,      // Extract from table5 row\n    description: selectedRowData.description, // Extract from table5 row\n    amount: selectedRowData.amount, // Extract from table5 row\n    currency: selectedRowData.currency || "USD", // Use default if undefined\n    state: selectedRowData.state,   // Extract from table5 row\n  },\n  journal_entries: selectedRowData.journal_entries || [\n    {\n      account: null,\n      debit_amount: null,\n      credit_amount: null,\n      state: "pending"\n    }\n  ]\n};\n\n// Step 4: Update the value of jsonEditor1 with the constructed JSON\n//jsonEditor1.setValue(jsonObject);\nListViewUpdatedValue.setValue(jsonObject);\n// Step 5: Open modalFrame2\nmodalFrame2.setHidden(false);',
                      },
                    ],
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
                  pluginId="table5"
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
                  pluginId="table5"
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
    <Button id="button2" text="Button">
      <Event
        event="click"
        method="run"
        params={{
          ordered: [
            {
              src: '// Define variables - these will actually come from your form\nvar id = 1;                  //  form.id\nvar name = "John Smith";     //  form.name\nvar pin = 493746;            //  etc.\nvar latitude = 37.7749;\nvar longitude = -122.4194;\n\n// Create the JSON object\nvar desiredJSON = {\n  "student": {\n    "id": id,\n    "name": name,\n    "address": {\n      "city": {\n        "nearby_town": {\n          "pin": pin\n        }\n      },\n      "coordinates": {\n        "latitude": latitude,\n        "longitude": longitude\n      }\n    }\n  }\n};',
            },
          ],
        }}
        pluginId=""
        type="script"
        waitMs="0"
        waitType="debounce"
      />
    </Button>
  </Frame>
</Screen>
