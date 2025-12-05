<ModalFrame
  id="modalNewEditReconPipe"
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
      id="modalTitle48"
      value="### Container title"
      verticalAlign="center"
    />
    <Button
      id="modalCloseButton53"
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
        pluginId="modalNewEditReconPipe"
        type="widget"
        waitMs="0"
        waitType="debounce"
      />
    </Button>
  </Header>
  <Body>
    <Form
      id="form23"
      footerPadding="4px 12px"
      headerPadding="4px 12px"
      initialData=""
      padding="12px"
      requireValidation={true}
      resetAfterSubmit={true}
      scroll={true}
      showBody={true}
      showBorder={false}
    >
      <Header>
        <Text id="formTitle38" value="#### Form title" verticalAlign="center" />
      </Header>
      <Body>
        <TextInput
          id="nameInput17"
          formDataKey="name"
          label="Name"
          labelPosition="top"
          placeholder="Enter value"
          required={true}
          value={
            '{{ selectedReconConfig.value ? selectedReconConfig.value[self.formDataKey] : "" }}'
          }
        />
        <Select
          id="scopeInput2"
          emptyMessage="No options"
          formDataKey="scope"
          itemMode="static"
          label="Scope"
          labelPosition="top"
          labels={null}
          overlayMaxHeight={375}
          placeholder="Select an option"
          required={true}
          showSelectionIndicator={true}
          value={
            '{{ selectedReconConfig.value ? selectedReconConfig.value[self.formDataKey] : "company" }}'
          }
          values={null}
        >
          <Option id="00030" value="global" />
          <Option id="00031" value="company" />
          <Option id="00032" value="user" />
          <Option
            id="cd51e"
            disabled={false}
            hidden={false}
            label="company & user"
            value="company_user"
          />
        </Select>
        <TextArea
          id="descriptionInput6"
          autoResize={true}
          formDataKey="description"
          label="Description"
          labelPosition="top"
          minLines={2}
          placeholder="Enter value"
          required={true}
          value={
            '{{ selectedReconConfig.value ? selectedReconConfig.value[self.formDataKey] : "" }}'
          }
        />
        <Select
          id="companyInput15"
          data="{{ clientes.data }}"
          disabled={
            '{{ scopeInput2.value == "global" || scopeInput2.value == "user"}}'
          }
          emptyMessage="No options"
          formDataKey="company"
          label="Company"
          labelPosition="top"
          labels="{{ item.name }}"
          overlayMaxHeight={375}
          placeholder="Select an option"
          showSelectionIndicator={true}
          value={
            '{{ scopeInput2.value == "company" || scopeInput2.value == "company_user" ?(selectedReconConfig.value ? selectedReconConfig.value[self.formDataKey] : "") : "" }}'
          }
          values="{{ item.id }}"
        />
        <Select
          id="userInput2"
          disabled={
            '{{ scopeInput2.value == "global" || scopeInput2.value == "company"}}'
          }
          emptyMessage="No options"
          formDataKey="user"
          itemMode="static"
          label="User"
          labelPosition="top"
          labels={null}
          overlayMaxHeight={375}
          placeholder="Select an option"
          showSelectionIndicator={true}
          value={
            '{{ scopeInput2.value == "user" || scopeInput2.value == "company_user" ?(selectedReconConfig.value ? selectedReconConfig.value[self.formDataKey] : "") : "" }}'
          }
          values={null}
        >
          <Option id="00030" value="Option 1" />
          <Option id="00031" value="Option 2" />
          <Option id="00032" value="Option 3" />
        </Select>
        <NumberInput
          id="maxGroupSizeInput4"
          currency="USD"
          formDataKey="max_group_size_bank"
          inputValue={0}
          label="Max bank group size"
          labelPosition="top"
          min="1"
          placeholder="Enter value"
          required={true}
          showSeparators={true}
          showStepper={true}
          value="{{ selectedReconConfig.value ? selectedReconConfig.value[self.formDataKey] : 1 }}"
        />
        <NumberInput
          id="maxGroupSizeInput3"
          currency="USD"
          formDataKey="max_group_size_book"
          inputValue={0}
          label="Max book group size"
          labelPosition="top"
          min="1"
          placeholder="Enter value"
          required={true}
          showSeparators={true}
          showStepper={true}
          value="{{ selectedReconConfig.value ? selectedReconConfig.value[self.formDataKey] : 1 }}"
        />
        <NumberInput
          id="amountToleranceInput2"
          currency="USD"
          formDataKey="amount_tolerance"
          inputValue={0}
          label="Amount tolerance"
          labelPosition="top"
          min="0"
          placeholder="Enter value"
          required={true}
          showSeparators={true}
          showStepper={true}
          value="{{ selectedReconConfig.value ? selectedReconConfig.value[self.formDataKey] : 0 }}"
        />
        <NumberInput
          id="dateToleranceDaysInput6"
          currency="USD"
          formDataKey="avg_date_delta_days"
          inputValue={0}
          label="Date tolerance days"
          labelPosition="top"
          min="0"
          placeholder="Enter value"
          required={true}
          showSeparators={true}
          showStepper={true}
          value="{{ selectedReconConfig.value ? selectedReconConfig.value[self.formDataKey] : 0 }}"
        />
        <NumberInput
          id="minConfidenceInput5"
          currency="USD"
          formDataKey="min_confidence"
          inputValue={0}
          label="Min confidence"
          labelPosition="top"
          max="1"
          min="0"
          placeholder="Enter value"
          required={true}
          showSeparators={true}
          showStepper={true}
          value="{{ selectedReconConfig.value ? selectedReconConfig.value[self.formDataKey] : 0.8 }}"
        />
        <NumberInput
          id="minConfidenceInput6"
          currency="USD"
          formDataKey="max_suggestions"
          inputValue={0}
          label="Max suggestions"
          labelPosition="top"
          max="10000"
          min="1"
          placeholder="Enter value"
          required={true}
          showSeparators={true}
          showStepper={true}
          value="{{ selectedReconConfig.value ? selectedReconConfig.value[self.formDataKey] : 0 }}"
        />
        <NumberInput
          id="dateToleranceDaysInput7"
          currency="USD"
          formDataKey="group_span_days"
          inputValue={0}
          label="Group Span Days"
          labelPosition="top"
          min="0"
          placeholder="Enter value"
          required={true}
          showSeparators={true}
          showStepper={true}
          value="{{ selectedReconConfig.value ? selectedReconConfig.value[self.formDataKey] : 0 }}"
        />
        <NumberInput
          id="dateToleranceDaysInput8"
          currency="USD"
          formDataKey="amount_weight"
          inputValue={0}
          label="Amount Weight"
          labelPosition="top"
          max="1"
          min="0"
          placeholder="Enter value"
          required={true}
          showSeparators={true}
          showStepper={true}
          value="{{ selectedReconConfig.value ? selectedReconConfig.value[self.formDataKey] : 0 }}"
        />
        <NumberInput
          id="minConfidenceInput7"
          currency="USD"
          formDataKey="date_weight"
          inputValue={0}
          label="Date Weight"
          labelPosition="top"
          max="1"
          min="0"
          placeholder="Enter value"
          required={true}
          showSeparators={true}
          showStepper={true}
          value="{{ selectedReconConfig.value ? selectedReconConfig.value[self.formDataKey] : 0 }}"
        />
        <NumberInput
          id="dateToleranceDaysInput10"
          currency="USD"
          formDataKey="soft_time_limit_seconds"
          inputValue={0}
          label="Time Limit (seconds)"
          labelPosition="top"
          min="0"
          placeholder="Enter value"
          required={true}
          showSeparators={true}
          showStepper={true}
          value="{{ selectedReconConfig.value ? selectedReconConfig.value[self.formDataKey] : 0 }}"
        />
        <NumberInput
          id="dateToleranceDaysInput9"
          currency="USD"
          formDataKey="embedding_weight"
          inputValue={0}
          label="Description Weight"
          labelPosition="top"
          max="1"
          min="0"
          placeholder="Enter value"
          required={true}
          showSeparators={true}
          showStepper={true}
          value="{{ selectedReconConfig.value ? selectedReconConfig.value[self.formDataKey] : 0 }}"
        />
        <NumberInput
          id="minConfidenceInput8"
          currency="USD"
          formDataKey="currency_weight"
          inputValue={0}
          label="Currency Weight"
          labelPosition="top"
          max="1"
          min="0"
          placeholder="Enter value"
          required={true}
          showSeparators={true}
          showStepper={true}
          value="{{ selectedReconConfig.value ? selectedReconConfig.value[self.formDataKey] : 0 }}"
        />
        <Include src="./group88.rsx" />
      </Body>
    </Form>
  </Body>
</ModalFrame>
