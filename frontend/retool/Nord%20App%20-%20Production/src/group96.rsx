<Container
  id="group96"
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
      id="filterReconSearch6"
      label="Search"
      labelPosition="top"
      placeholder="Enter value"
      showClear={true}
    />
    <DateRange
      id="filterReconDateRange6"
      dateFormat="yyyy-MM-dd"
      endPlaceholder="End date"
      iconBefore="bold/interface-calendar-remove"
      label="Book and Bank Date Range"
      labelPosition="top"
      showClear={true}
      startPlaceholder="Start date"
      textBetween="-"
      value={{ start: "", end: "" }}
    />
    <Button
      id="button66"
      style={{}}
      styleVariant="outline"
      text="Clear Filters"
    >
      <Event
        event="click"
        method="reset"
        params={{}}
        pluginId="form26"
        type="widget"
        waitMs="0"
        waitType="debounce"
      />
    </Button>
    <DateRange
      id="filterReconDateRange7"
      dateFormat="yyyy-MM-dd"
      endPlaceholder="End date"
      iconBefore="bold/interface-calendar-remove"
      label="Recon at Date Range"
      labelPosition="top"
      showClear={true}
      startPlaceholder="Start date"
      textBetween="-"
      value={{ start: "", end: "" }}
    />
    <NumberInput
      id="filterReconMinAmount"
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
    <NumberInput
      id="filterReconMaxAmount"
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
