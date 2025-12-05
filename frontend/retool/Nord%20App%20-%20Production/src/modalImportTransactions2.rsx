<ModalFrame
  id="modalImportTransactions2"
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
    <Button
      id="modalCloseButton38"
      ariaLabel="Close"
      horizontalAlign="right"
      iconBefore="bold/interface-delete-1"
      style={{ ordered: [{ border: "transparent" }] }}
      styleVariant="outline"
    >
      <Event
        event="click"
        method="setHidden"
        params={{ ordered: [{ hidden: true }] }}
        pluginId="modalImportTransactions2"
        type="widget"
        waitMs="0"
        waitType="debounce"
      />
    </Button>
  </Header>
  <Body>
    <Container
      id="container18"
      footerPadding="4px 12px"
      headerPadding="4px 12px"
      heightType="fixed"
      padding="12px"
      showBody={true}
      showHeader={true}
    >
      <Header>
        <Button id="button40" text="Template">
          <Event
            event="click"
            method="run"
            params={{
              map: {
                src: '// 🔁 Step 1: Trigger the query and wait for response\nawait AccountingTransaction_template2.trigger(); // Replace with your actual query name\n\n// 🔁 Step 2: Access the data\nconst file = AccountingTransaction_template2.data; // Replace again if needed\nconst base64 = file.base64Data;\nconst fileName = file.name || "import_template.xlsx";\n\n// 🔁 Step 3: Convert base64 to Blob and download\nconst byteCharacters = atob(base64);\nconst byteNumbers = new Array(byteCharacters.length);\nfor (let i = 0; i < byteCharacters.length; i++) {\n  byteNumbers[i] = byteCharacters.charCodeAt(i);\n}\nconst byteArray = new Uint8Array(byteNumbers);\nconst blob = new Blob([byteArray], {\n  type: file.type || \'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet\'\n});\n\nconst link = document.createElement("a");\nlink.href = URL.createObjectURL(blob);\nlink.download = fileName;\ndocument.body.appendChild(link);\nlink.click();\ndocument.body.removeChild(link);\n',
              },
            }}
            pluginId=""
            type="script"
            waitMs="0"
            waitType="debounce"
          />
        </Button>
        <Button
          id="button39"
          style={{ ordered: [] }}
          styleVariant="outline"
          text="Importar Todos"
        />
        <Text
          id="containerTitle19"
          value="#### Importar de Transações"
          verticalAlign="center"
        />
      </Header>
      <View id="9fde9" viewKey="View 1">
        <Container
          id="group48"
          _gap="0px"
          _type="stack"
          footerPadding="4px 12px"
          headerPadding="4px 12px"
          heightType="fixed"
          margin="0"
          overflowType="hidden"
          padding="0"
          showBody={true}
          showBorder={false}
          style={{ ordered: [{ background: "rgba(255, 255, 255, 0)" }] }}
        >
          <View id="9fde9" viewKey="View 1">
            <Container
              id="group49"
              _direction="vertical"
              _flexWrap={true}
              _gap="0px"
              _type="stack"
              footerPadding="4px 12px"
              headerPadding="4px 12px"
              heightType="fill"
              margin="0"
              padding="0"
              showBody={true}
              showBorder={false}
              style={{ ordered: [{ background: "rgba(255, 255, 255, 0)" }] }}
            >
              <View id="bc13f" viewKey="View 1">
                <FileDropzone
                  id="fileDropzoneBook2"
                  _isUpgraded={true}
                  appendNewSelection={true}
                  iconBefore="bold/programming-browser-search"
                  label=""
                  labelPosition="top"
                  maxCount={20}
                  maxSize="250mb"
                  parseFiles={true}
                  placeholder="Select or drag and drop"
                  selectionType="multiple"
                >
                  <Event
                    event="parse"
                    method="trigger"
                    params={{ ordered: [] }}
                    pluginId="AccountingTransaction_import2"
                    type="datasource"
                    waitMs="0"
                    waitType="debounce"
                  />
                </FileDropzone>
              </View>
            </Container>
            <Table
              id="table43"
              cellSelection="none"
              clearChangesetOnSave={true}
              data="{{ transformOFX2.value }}"
              defaultSelectedRow={{
                mode: "index",
                indexType: "display",
                index: 0,
              }}
              emptyMessage="No rows found"
              enableSaveActions={true}
              heightType="fill"
              showBorder={true}
              showFooter={true}
              showHeader={true}
              toolbarPosition="bottom"
            >
              <Column
                id="5900d"
                alignment="right"
                editableOptions={{ showStepper: true }}
                format="decimal"
                formatOptions={{ showSeparators: true, notation: "standard" }}
                groupAggregationMode="sum"
                key="index"
                label="Index"
                placeholder="Enter value"
                position="center"
                size={46.890625}
                summaryAggregationMode="none"
              />
              <Column
                id="01a84"
                alignment="left"
                format="string"
                groupAggregationMode="none"
                key="filename"
                label="Filename"
                placeholder="Enter value"
                position="center"
                size={86.203125}
                summaryAggregationMode="none"
              />
              <Column
                id="56e95"
                alignment="left"
                format="json"
                groupAggregationMode="none"
                key="bank"
                label="Bank"
                placeholder="Enter value"
                position="center"
                size={100}
                statusIndicatorOptions={{
                  manualData: [
                    {
                      ordered: [
                        { showWhen: "{{ item.status === 'Error' }}" },
                        { label: "" },
                        { icon: "bold/interface-delete-2" },
                        { color: "rgba(184, 0, 0, 1)" },
                      ],
                    },
                  ],
                }}
                summaryAggregationMode="none"
                valueOverride="{{  item.value }}"
              />
              <Column
                id="9ba3b"
                alignment="left"
                format="json"
                groupAggregationMode="none"
                key="account"
                label="Account"
                placeholder="Enter value"
                position="center"
                size={100}
                summaryAggregationMode="none"
              />
              <Column
                id="34c8d"
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
                id="14f10"
                alignment="left"
                format="date"
                groupAggregationMode="none"
                key="date"
                label="Date"
                placeholder="Enter value"
                position="center"
                size={100}
                summaryAggregationMode="none"
              />
              <Column
                id="4b5d0"
                alignment="right"
                editableOptions={{ showStepper: true }}
                format="decimal"
                formatOptions={{ showSeparators: true, notation: "standard" }}
                groupAggregationMode="sum"
                key="amount"
                label="Amount"
                placeholder="Enter value"
                position="center"
                size={100}
                summaryAggregationMode="none"
              />
              <Column
                id="9f0ae"
                alignment="left"
                format="string"
                groupAggregationMode="none"
                key="memo"
                label="Memo"
                placeholder="Enter value"
                position="center"
                size={100}
                summaryAggregationMode="none"
              />
              <Column
                id="06da7"
                alignment="left"
                format="string"
                groupAggregationMode="none"
                key="tx_hash"
                label="Tx hash"
                placeholder="Enter value"
                position="center"
                size={100}
                summaryAggregationMode="none"
              />
              <Column
                id="9b4a2"
                alignment="left"
                format="tag"
                formatOptions={{ automaticColors: true }}
                groupAggregationMode="none"
                key="status"
                label="Status"
                placeholder="Select option"
                position="center"
                size={100}
                summaryAggregationMode="none"
                valueOverride="{{ _.startCase(item) }}"
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
                  pluginId="table43"
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
                  pluginId="table43"
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
  </Body>
</ModalFrame>
