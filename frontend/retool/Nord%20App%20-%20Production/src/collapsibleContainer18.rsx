<Container
  id="collapsibleContainer18"
  footerPadding="4px 12px"
  headerPadding="4px 12px"
  padding="12px"
  showBody={true}
  showHeader={true}
>
  <Header>
    <Text
      id="collapsibleTitle18"
      value="###### Filtros Transações Book"
      verticalAlign="center"
    />
    <ToggleButton
      id="collapsibleToggle18"
      horizontalAlign="right"
      iconForFalse="bold/interface-arrows-button-down"
      iconForTrue="bold/interface-arrows-button-up"
      iconPosition="replace"
      styleVariant="outline"
      text="{{ self.value ? 'Hide' : 'Show' }}"
      value="{{ collapsibleContainer18.showBody }}"
    >
      <Event
        event="change"
        method="setShowBody"
        params={{ ordered: [{ showBody: "{{ self.value }}" }] }}
        pluginId="collapsibleContainer18"
        type="widget"
        waitMs="0"
        waitType="debounce"
      />
    </ToggleButton>
  </Header>
  <View id="08456" viewKey="View 1">
    <NumberInput
      id="minBookAmount2"
      currency="USD"
      inputValue={0}
      label="Min Book Amount"
      labelPosition="top"
      placeholder="Enter value"
      showClear={true}
      showSeparators={true}
      value="-9999999"
    />
    <NumberInput
      id="maxBookAmount2"
      currency="USD"
      inputValue={0}
      label="Max Book Amount"
      labelPosition="top"
      placeholder="Enter value"
      showClear={true}
      showSeparators={true}
      value="9999999"
    />
    <DateRange
      id="dateRangeBook2"
      dateFormat="MMM d, yyyy"
      endPlaceholder="End date"
      iconBefore="bold/interface-calendar-remove"
      label="Book Date Range"
      labelPosition="top"
      startPlaceholder="Start date"
      textBetween="-"
      value={{ ordered: [{ start: "" }, { end: "" }] }}
    />
  </View>
</Container>
