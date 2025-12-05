<ModalFrame
  id="modalNewPosition2"
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
      id="modalTitle10"
      value="### Container title"
      verticalAlign="center"
    />
    <Button
      id="modalCloseButton12"
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
        pluginId="modalNewPosition2"
        type="widget"
        waitMs="0"
        waitType="debounce"
      />
    </Button>
  </Header>
  <Body>
    <Form
      id="form12"
      footerPadding="4px 12px"
      headerPadding="4px 12px"
      initialData="{{ tableCostCenter.selectedRow }}"
      padding="12px"
      requireValidation={true}
      resetAfterSubmit={true}
      scroll={true}
      showBody={true}
      showFooter={true}
      showHeader={true}
    >
      <Header>
        <Text id="formTitle23" value="#### Form title" verticalAlign="center" />
      </Header>
      <Body>
        <NumberInput
          id="numberInput89"
          currency="USD"
          formDataKey="id"
          inputValue={0}
          label="ID"
          labelPosition="top"
          placeholder="Enter value"
          required={true}
          showSeparators={true}
          showStepper={true}
          value={0}
        />
        <NumberInput
          id="numberInput90"
          currency="USD"
          formDataKey="company"
          inputValue={0}
          label="Company"
          labelPosition="top"
          placeholder="Enter value"
          required={true}
          showSeparators={true}
          showStepper={true}
          value={0}
        />
        <TextInput
          id="textInput17"
          formDataKey="title"
          label="Title"
          labelPosition="top"
          placeholder="Enter value"
          required={true}
        />
        <TextInput
          id="textInput18"
          formDataKey="description"
          label="Description"
          labelPosition="top"
          placeholder="Enter value"
          required={true}
        />
        <TextInput
          id="textInput19"
          formDataKey="department"
          label="Department"
          labelPosition="top"
          placeholder="Enter value"
          required={true}
        />
        <NumberInput
          id="numberInput91"
          currency="USD"
          formDataKey="hierarchy_level"
          inputValue={0}
          label="Hierarchy level"
          labelPosition="top"
          placeholder="Enter value"
          required={true}
          showSeparators={true}
          showStepper={true}
          value={0}
        />
        <NumberInput
          id="numberInput92"
          currency="USD"
          formDataKey="min_salary"
          inputValue={0}
          label="Min salary"
          labelPosition="top"
          placeholder="Enter value"
          required={true}
          showSeparators={true}
          showStepper={true}
          value={0}
        />
        <NumberInput
          id="numberInput93"
          currency="USD"
          formDataKey="max_salary"
          inputValue={0}
          label="Max salary"
          labelPosition="top"
          placeholder="Enter value"
          required={true}
          showSeparators={true}
          showStepper={true}
          value={0}
        />
      </Body>
      <Footer>
        <Button
          id="formButton11"
          submit={true}
          submitTargetId="form12"
          text="Submit"
        />
      </Footer>
    </Form>
  </Body>
</ModalFrame>
