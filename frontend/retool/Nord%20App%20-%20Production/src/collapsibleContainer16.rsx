<Container
  id="collapsibleContainer16"
  footerPadding="4px 12px"
  headerPadding="4px 12px"
  padding="12px"
  showBody={true}
  showHeader={true}
>
  <Header>
    <Text
      id="collapsibleTitle16"
      value="###### Parâmetros Conciliação"
      verticalAlign="center"
    />
    <ToggleButton
      id="collapsibleToggle16"
      horizontalAlign="right"
      iconForFalse="bold/interface-arrows-button-down"
      iconForTrue="bold/interface-arrows-button-up"
      iconPosition="replace"
      styleVariant="outline"
      text="{{ self.value ? 'Hide' : 'Show' }}"
      value="{{ collapsibleContainer16.showBody }}"
    >
      <Event
        event="change"
        method="setShowBody"
        params={{ ordered: [{ showBody: "{{ self.value }}" }] }}
        pluginId="collapsibleContainer16"
        type="widget"
        waitMs="0"
        waitType="debounce"
      />
    </ToggleButton>
  </Header>
  <View id="53ea8" viewKey="View 1">
    <Switch
      id="switchSameBank2"
      disabled="true"
      formDataKey="enforce_same_bank"
      label="Same Bank"
    />
    <Switch
      id="switchSameEntity2"
      disabled="true"
      formDataKey="enforce_same_entity"
      label="Same Entity"
    />
    <NumberInput
      id="BankToCombine2"
      currency="USD"
      inputValue={0}
      label="Combinações Banco"
      labelPosition="top"
      max="10"
      min="1"
      placeholder="Enter value"
      showClear={true}
      showSeparators={true}
      showStepper={true}
      value="2"
    />
    <NumberInput
      id="BookToCombine2"
      currency="USD"
      inputValue={0}
      label="Combinações Book"
      labelPosition="top"
      max="10"
      min="1"
      placeholder="Enter value"
      showClear={true}
      showSeparators={true}
      showStepper={true}
      value="2"
    />
    <NumberInput
      id="AmountTolerance2"
      currency="USD"
      inputValue={0}
      label="Amount Tolerance"
      labelPosition="top"
      min="0"
      placeholder="Enter value"
      showClear={true}
      showSeparators={true}
      value="100"
    />
    <NumberInput
      id="DateTolerance2"
      currency="USD"
      inputValue={0}
      label="Date Tolerance"
      labelPosition="top"
      max="30"
      min="0"
      placeholder="Enter value"
      showClear={true}
      showSeparators={true}
      showStepper={true}
      value="2"
    />
    <NumberInput
      id="MinConfidence2"
      currency="USD"
      decimalPlaces="2"
      format="percent"
      inputValue={0}
      label="Min Confidence"
      labelPosition="top"
      max="1"
      min="0"
      placeholder="Enter value"
      showSeparators={true}
      showStepper={true}
      value="0.95"
    />
    <NumberInput
      id="MaxSuggestions2"
      currency="USD"
      decimalPlaces="0"
      inputValue={0}
      label="Max Sugestions"
      labelPosition="top"
      min="1"
      placeholder="Enter value"
      showSeparators={true}
      showStepper={true}
      value="5"
    />
  </View>
</Container>
