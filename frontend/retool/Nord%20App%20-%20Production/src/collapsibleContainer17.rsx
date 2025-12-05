<Container
  id="collapsibleContainer17"
  footerPadding="4px 12px"
  headerPadding="4px 12px"
  padding="12px"
  showBody={true}
  showHeader={true}
>
  <Header>
    <Text
      id="collapsibleTitle17"
      value="###### Filtros Transações Banco"
      verticalAlign="center"
    />
    <ToggleButton
      id="collapsibleToggle17"
      horizontalAlign="right"
      iconForFalse="bold/interface-arrows-button-down"
      iconForTrue="bold/interface-arrows-button-up"
      iconPosition="replace"
      styleVariant="outline"
      text="{{ self.value ? 'Hide' : 'Show' }}"
      value="{{ collapsibleContainer17.showBody }}"
    >
      <Event
        event="change"
        method="setShowBody"
        params={{ ordered: [{ showBody: "{{ self.value }}" }] }}
        pluginId="collapsibleContainer17"
        type="widget"
        waitMs="0"
        waitType="debounce"
      />
    </ToggleButton>
  </Header>
  <View id="53ea8" viewKey="View 1">
    <NumberInput
      id="minBankAmount2"
      currency="USD"
      inputValue={0}
      label="Min Bank Amount"
      labelPosition="top"
      placeholder="Enter value"
      showClear={true}
      showSeparators={true}
      value="-9999999"
    />
    <NumberInput
      id="maxBankAmount2"
      currency="USD"
      inputValue={0}
      label="Max Bank Amount"
      labelPosition="top"
      placeholder="Enter value"
      showClear={true}
      showSeparators={true}
      value="9999999"
    />
    <DateRange
      id="dateRangeBank2"
      dateFormat="MMM d, yyyy"
      endPlaceholder="End date"
      iconBefore="bold/interface-calendar-remove"
      label="Bank Date Range"
      labelPosition="top"
      startPlaceholder="Start date"
      textBetween="-"
      value={{ ordered: [{ start: "" }, { end: "" }] }}
    />
    <TextInput
      id="textInput23"
      label="Description"
      labelPosition="top"
      placeholder="Enter value"
    />
    <Multiselect
      id="multiselect6"
      data="{{ BankAccount_get2.data }}"
      emptyMessage="No options"
      label="Conta Bancária"
      labelPosition="top"
      labels="{{ item.name + ' (' +item.bank.name +' '+item.branch_id +' - ' +item.account_number +')'}}"
      overlayMaxHeight={375}
      placeholder="Select options"
      showSelectionIndicator={true}
      tooltipByIndex="{{ item.name + ' (' +item.bank.name +' '+item.branch_id +' - ' +item.account_number +')'}}"
      values="{{ item.id }}"
      wrapTags={true}
    />
  </View>
</Container>
