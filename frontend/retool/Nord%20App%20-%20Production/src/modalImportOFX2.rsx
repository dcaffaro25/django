<ModalFrame
  id="modalImportOFX2"
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
    <Button
      id="modalCloseButton37"
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
        pluginId="modalImportOFX2"
        type="widget"
        waitMs="0"
        waitType="debounce"
      />
      <Event
        event="click"
        method="resetValue"
        params={{}}
        pluginId="fileDropzoneOFX2"
        type="widget"
        waitMs="0"
        waitType="debounce"
      />
      <Event
        event="click"
        method="reset"
        params={{}}
        pluginId="OFXTransaction_import4"
        type="datasource"
        waitMs="0"
        waitType="debounce"
      />
    </Button>
  </Header>
  <Body>
    <Container
      id="container16"
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
        <Button
          id="button38"
          style={{ ordered: [] }}
          styleVariant="outline"
          text="Importar Todos"
        >
          <Event
            event="click"
            method="run"
            params={{
              ordered: [
                {
                  src: 'const SelectedFile = {\n  "files": fileDropzoneOFX2.value\n}\nOFXTransaction_import6.trigger({\n  additionalScope: {\n    content: SelectedFile\n  }\n});',
                },
              ],
            }}
            pluginId=""
            type="script"
            waitMs="0"
            waitType="debounce"
          />
        </Button>
        <Text
          id="containerTitle17"
          value="#### Importar de OFX"
          verticalAlign="center"
        />
      </Header>
      <View id="9fde9" viewKey="View 1">
        <Container
          id="group46"
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
              id="group47"
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
              style={{ ordered: [{ background: "rgba(255, 255, 255, 0)" }] }}
            >
              <View id="bc13f" viewKey="View 1">
                <FileDropzone
                  id="fileDropzoneOFX2"
                  _isUpgraded={true}
                  appendNewSelection={true}
                  iconBefore="bold/programming-browser-search"
                  label=""
                  labelPosition="top"
                  maxCount={20}
                  maxSize="250mb"
                  placeholder="Select or drag and drop"
                  selectionType="multiple"
                >
                  <Event
                    event="parse"
                    method="trigger"
                    params={{ ordered: [] }}
                    pluginId="OFXTransaction_import4"
                    type="datasource"
                    waitMs="0"
                    waitType="debounce"
                  />
                </FileDropzone>
                <ListViewBeta
                  id="listView6"
                  _primaryKeys="{{ i }}"
                  data="{{ OFXTransaction_import4.data }}"
                  itemWidth="200px"
                  margin="0"
                  numColumns={3}
                  padding="0"
                >
                  <Include src="./container17.rsx" />
                </ListViewBeta>
              </View>
            </Container>
            <Table
              id="table42"
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
                size={46.90625}
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
                size={203.046875}
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
                size={343.796875}
                summaryAggregationMode="none"
                valueOverride="{{  item.status === 'Success' ? item.value.bank_code +' ' + item.value.name : item.value }}"
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
                size={343.796875}
                summaryAggregationMode="none"
                valueOverride="{{  item.status === 'Success' ? item.value.account_number +' ' + item.value.name : item.value }}"
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
                size={75.03125}
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
                size={83.21875}
                summaryAggregationMode="none"
              />
              <Column
                id="4b5d0"
                alignment="right"
                editableOptions={{ showStepper: true }}
                format="decimal"
                formatOptions={{
                  showSeparators: true,
                  notation: "standard",
                  decimalPlaces: "2",
                }}
                groupAggregationMode="sum"
                key="amount"
                label="Amount"
                placeholder="Enter value"
                position="center"
                size={71.8125}
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
                size={343.796875}
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
                size={248.53125}
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
                size={78.15625}
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
                  pluginId="table42"
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
                  pluginId="table42"
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
