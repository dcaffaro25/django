<ModalFrame
  id="modalCostCenter"
  footerPadding="8px 12px"
  headerPadding="8px 12px"
  hidden={true}
  hideOnEscape={true}
  isHiddenOnMobile={true}
  overlayInteraction={true}
  padding="8px 12px"
  showHeader={true}
  showOverlay={true}
  size="medium"
>
  <Header>
    <Text
      id="modalTitle16"
      value={
        '#### {{ costcenter_mode.value !== "edit" ? "Novo" : "Editar" }} Centro de Custo'
      }
      verticalAlign="center"
    />
    <Button
      id="modalCloseButton18"
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
        pluginId="modalCostCenter"
        type="widget"
        waitMs="0"
        waitType="debounce"
      />
    </Button>
  </Header>
  <Body>
    <Form
      id="CostCenterForm"
      footerPadding="4px 12px"
      headerPadding="4px 12px"
      initialData="{{ tableCostCenter.selectedRow }}"
      padding="12px"
      requireValidation={true}
      resetAfterSubmit={true}
      scroll={true}
      showBody={true}
      showFooter={true}
    >
      <Body>
        <Select
          id="centerTypeInput"
          emptyMessage="No options"
          formDataKey="center_type"
          itemMode="static"
          label="Center type"
          labelPosition="top"
          labels={null}
          overlayMaxHeight={375}
          placeholder="Select an option"
          required={true}
          showSelectionIndicator={true}
          values={null}
        >
          <Option id="f9b72" value="profit" />
          <Option id="65fd3" value="cost" />
        </Select>
        <TextInput
          id="nameInput6"
          formDataKey="name"
          label="Name"
          labelPosition="top"
          placeholder="Enter value"
          required={true}
        />
        <TextInput
          id="descriptionInput"
          formDataKey="description"
          label="Description"
          labelPosition="top"
          placeholder="Enter value"
          required={true}
        />
        <Date
          id="balanceDateInput2"
          dateFormat="yyyy-MM-dd"
          datePlaceholder="{{ self.dateFormat.toUpperCase() }}"
          formDataKey="balance_date"
          iconBefore="bold/interface-calendar"
          label="Balance date"
          labelPosition="top"
          required={true}
          value="{{ new Date() }}"
        />
        <NumberInput
          id="balanceInput3"
          currency="USD"
          formDataKey="balance"
          inputValue={0}
          label="Balance"
          labelPosition="top"
          placeholder="Enter value"
          required={true}
          showSeparators={true}
          showStepper={true}
          value={0}
        />
        <NumberInput
          id="numberInput94"
          currency="USD"
          disabled="true"
          formDataKey="company"
          hidden="true"
          inputValue={0}
          label="Company Id"
          labelPosition="top"
          placeholder="Enter value"
          required={true}
          showSeparators={true}
          showStepper={true}
          value="{{ ClienteDropDown.selectedItem.id }}"
        />
      </Body>
      <Footer>
        <Button
          id="NewButton16"
          hidden={'{{ costcenter_mode.value !== "new" }}'}
          submitTargetId="CostCenterForm"
          text="Submit"
        >
          <Event
            event="click"
            method="trigger"
            params={{ ordered: [] }}
            pluginId="costcenter_new"
            type="datasource"
            waitMs="0"
            waitType="debounce"
          />
        </Button>
        <Button
          id="EditButton16"
          hidden={'{{ costcenter_mode.value !== "edit" }}'}
          submit={true}
          submitTargetId="CostCenterForm"
          text="Edit"
        />
      </Footer>
    </Form>
  </Body>
</ModalFrame>
