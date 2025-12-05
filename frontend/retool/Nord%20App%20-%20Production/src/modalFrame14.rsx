<ModalFrame
  id="modalFrame14"
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
      id="modalTitle44"
      heightType="fixed"
      value="#### Adicionar Dados Fictícios"
      verticalAlign="center"
    />
    <Button
      id="modalCloseButton49"
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
        pluginId="modalFrame14"
        type="widget"
        waitMs="0"
        waitType="debounce"
      />
    </Button>
  </Header>
  <Body>
    <Button
      id="button50"
      iconBefore="bold/interface-add-1"
      style={{ ordered: [] }}
      styleVariant="outline"
    />
    <Text id="text55" value="**Modelo**" verticalAlign="center" />
    <Text id="text56" value="**Quantidade**" verticalAlign="center" />
    <Container
      id="container26"
      enableFullBleed={true}
      footerPadding="4px 12px"
      headerPadding="4px 12px"
      heightType="fixed"
      overflowType="hidden"
      padding="12px"
      showBody={true}
    >
      <Header>
        <Text
          id="listViewTitle3"
          value="#### List View title"
          verticalAlign="center"
        />
      </Header>
      <View id="e5f54" viewKey="View 1">
        <ListViewBeta
          id="listView7"
          data="[0, 1, 2, 3, 4, 5]"
          itemWidth="200px"
          margin="0"
          numColumns={3}
          padding="12px"
        >
          <Select
            id="select25"
            emptyMessage="No options"
            hideLabel={true}
            itemMode="static"
            label="Modelo"
            labelPosition="top"
            overlayMaxHeight={375}
            placeholder="Select an option"
            showSelectionIndicator={true}
          >
            <Option id="11e11" value="Option 1" />
            <Option id="c83f9" value="Option 2" />
            <Option id="97074" value="Option 3" />
          </Select>
          <NumberInput
            id="numberInput110"
            currency="USD"
            decimalPlaces="0"
            hideLabel={true}
            inputValue={0}
            label="Quantidade"
            labelPosition="top"
            max="10"
            min="0"
            placeholder="Enter value"
            showSeparators={true}
            showStepper={true}
            value={0}
          />
          <Button
            id="button51"
            iconBefore="bold/interface-delete-bin-1"
            style={{ ordered: [] }}
            styleVariant="outline"
          />
        </ListViewBeta>
      </View>
    </Container>
  </Body>
</ModalFrame>
