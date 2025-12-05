<Container
  id="group87"
  _align="end"
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
    <NumberInput
      id="filterReconDescrScore"
      currency="USD"
      format="percent"
      inputValue={0}
      label="Descr Score"
      labelPosition="top"
      max={1}
      min={0}
      placeholder="Enter value"
      showClear={true}
      showSeparators={true}
      showStepper={true}
      value={0}
    />
    <NumberInput
      id="filterReconDateScore"
      currency="USD"
      format="percent"
      inputValue={0}
      label="Date Score"
      labelPosition="top"
      max={1}
      min={0}
      placeholder="Enter value"
      showClear={true}
      showSeparators={true}
      showStepper={true}
      value={0}
    />
    <TextInput
      id="filterReconSearch"
      label="Search"
      labelPosition="top"
      placeholder="Enter value"
      showClear={true}
    />
    <DateRange
      id="filterReconDateRange"
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
    <Button
      id="button58"
      style={{}}
      styleVariant="outline"
      text="Clear Filters"
    >
      <Event
        event="click"
        method="reset"
        params={{}}
        pluginId="form20"
        type="widget"
        waitMs="0"
        waitType="debounce"
      />
    </Button>
    <NumberInput
      id="filterReconGlobalScore"
      currency="USD"
      format="percent"
      inputValue={0}
      label="Global Score"
      labelPosition="top"
      max={1}
      min={0}
      placeholder="Enter value"
      showClear={true}
      showSeparators={true}
      showStepper={true}
      value={0}
    />
    <NumberInput
      id="filterReconAmountScore"
      currency="USD"
      format="percent"
      inputValue={0}
      label="Amount Score"
      labelPosition="top"
      max={1}
      min={0}
      placeholder="Enter value"
      showClear={true}
      showSeparators={true}
      showStepper={true}
      value={0}
    />
  </View>
</Container>
