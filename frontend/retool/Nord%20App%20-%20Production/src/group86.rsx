<Container
  id="group86"
  _align="end"
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
    <TextInput
      id="filterReconSearch3"
      label="Search"
      labelPosition="top"
      placeholder="Enter value"
      showClear={true}
    />
    <DateRange
      id="filterReconDateRange3"
      dateFormat="yyyy-MM-dd"
      endPlaceholder="End date"
      iconBefore="bold/interface-calendar-remove"
      label="Date Range"
      labelPosition="top"
      showClear={true}
      startPlaceholder="Start date"
      textBetween="-"
      value={{ start: "", end: "" }}
    />
    <NumberInput
      id="filterBookMinAmount"
      allowNull={true}
      currency="USD"
      inputValue={0}
      label="Min Amount"
      labelPosition="top"
      placeholder="Enter value"
      showClear={true}
      showSeparators={true}
      showStepper={true}
      value="null"
    />
    <Button
      id="button60"
      style={{}}
      styleVariant="outline"
      text="Clear Filters"
    >
      <Event
        event="click"
        method="run"
        params={{
          map: {
            src: "filterBookMinAmount.clearValue();\nfilterBookMaxAmount.clearValue();\nfilterReconSearch3.clearValue();\nfilterReconDateRange3.clearValue();\ntableBook.clearFilter();",
          },
        }}
        pluginId=""
        type="script"
        waitMs="0"
        waitType="debounce"
      />
    </Button>
    <NumberInput
      id="filterBookMaxAmount"
      allowNull={true}
      currency="USD"
      inputValue={0}
      label="Max Amount"
      labelPosition="top"
      placeholder="Enter value"
      showClear={true}
      showSeparators={true}
      showStepper={true}
      value="null"
    />
  </View>
</Container>
