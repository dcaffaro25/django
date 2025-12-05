<ModalFrame
  id="modalBank"
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
      id="modalTitle17"
      value={'#### {{ bank_mode.value !== "edit"  ? "Novo" : "Editar" }} Banco'}
      verticalAlign="center"
    />
    <Button
      id="modalCloseButton19"
      ariaLabel="Close"
      horizontalAlign="right"
      iconBefore="bold/interface-delete-1"
      style={{ map: { border: "transparent" } }}
      styleVariant="outline"
    >
      <Event
        event="click"
        method="setHidden"
        params={{ map: { hidden: true } }}
        pluginId="modalBank"
        type="widget"
        waitMs="0"
        waitType="debounce"
      />
    </Button>
  </Header>
  <Body>
    <Form
      id="BankForm"
      footerPadding="4px 12px"
      headerPadding="4px 12px"
      initialData=""
      padding="12px"
      requireValidation={true}
      resetAfterSubmit={true}
      scroll={true}
      showBody={true}
    >
      <TextInput
        id="nameInput5"
        formDataKey="name"
        label="Name"
        labelPosition="top"
        placeholder="Enter value"
        required={true}
        value="{{ bank_selected.value && bank_selected.value[self.formDataKey] ? bank_selected.value[self.formDataKey] : null }}"
      />
      <Select
        id="countryInput"
        emptyMessage="No options"
        formDataKey="country"
        itemMode="static"
        label="Country"
        labelPosition="top"
        labels={null}
        overlayMaxHeight={375}
        placeholder="Select an option"
        required={true}
        showSelectionIndicator={true}
        value="{{ bank_selected.value && bank_selected.value[self.formDataKey] ? bank_selected.value[self.formDataKey] : null }}"
        values={null}
      >
        <Option id="ad9a4" value="Brasil" />
      </Select>
      <NumberInput
        id="bankCodeInput"
        currency="USD"
        formDataKey="bank_code"
        inputValue={0}
        label="Bank code"
        labelPosition="top"
        placeholder="Enter value"
        required={true}
        showSeparators={true}
        showStepper={true}
        value="{{ bank_selected.value && bank_selected.value[self.formDataKey] ? bank_selected.value[self.formDataKey] : null }}"
      />
    </Form>
  </Body>
  <Footer>
    <Button
      id="button28"
      hidden={'{{ bank_mode.value !== "edit" }}'}
      text="Edit"
    >
      <Event
        event="click"
        method="trigger"
        params={{
          map: {
            options: {
              object: {
                onSuccess: null,
                onFailure: null,
                additionalScope: null,
              },
            },
          },
        }}
        pluginId="bank_edit"
        type="datasource"
        waitMs="0"
        waitType="debounce"
      />
    </Button>
    <Button
      id="button29"
      hidden={'{{ bank_mode.value !== "new" }}'}
      text="Submit"
    >
      <Event
        event="click"
        method="trigger"
        params={{}}
        pluginId="bank_new"
        type="datasource"
        waitMs="0"
        waitType="debounce"
      />
    </Button>
  </Footer>
</ModalFrame>
