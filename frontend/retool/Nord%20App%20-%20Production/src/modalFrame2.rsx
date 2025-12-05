<ModalFrame
  id="modalFrame2"
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
  size="fullScreen"
>
  <Header>
    <Text id="modalTitle2" value="### Transações" verticalAlign="center" />
    <Button
      id="modalCloseButton2"
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
        pluginId="modalFrame2"
        type="widget"
        waitMs="0"
        waitType="debounce"
      />
    </Button>
    <Form
      id="form7"
      footerPadding="4px 12px"
      headerPadding="4px 12px"
      padding="12px"
      requireValidation={true}
      resetAfterSubmit={true}
      showBody={true}
    >
      <Header>
        <Text id="formTitle6" value="#### Form title" verticalAlign="center" />
      </Header>
      <Body>
        <TextInput
          id="textInput3"
          label="Transação"
          labelPosition="top"
          placeholder="Enter value"
          value="{{ jsonEditor1.value.transaction.description }}"
        />
        <Date
          id="date3"
          dateFormat="MMM d, yyyy"
          datePlaceholder="{{ self.dateFormat.toUpperCase() }}"
          formDataKey="date"
          iconBefore="bold/interface-calendar"
          label="Data"
          labelPosition="top"
          required={true}
          value="{{ jsonEditor1.value.transaction.date }}"
        />
        <Select
          id="select6"
          data="{{ currencies.data }}"
          emptyMessage="No options"
          label="Moeda"
          labelPosition="top"
          labels="{{ item.name }}"
          overlayMaxHeight={375}
          placeholder="Select an option"
          showSelectionIndicator={true}
          value="{{ jsonEditor1.value.transaction.currency.id }}"
          values="{{ item.id }}"
        />
        <NumberInput
          id="numberInput27"
          currency="USD"
          formDataKey="currency"
          inputValue={0}
          label="Valor"
          labelPosition="top"
          placeholder="Enter value"
          required={true}
          showSeparators={true}
          showStepper={true}
          value="{{ jsonEditor1.value.transaction.amount }}"
        />
        <Status
          id="status1"
          heightType="fixed"
          horizontalAlign="center"
          itemMode="static"
          value="{{ jsonEditor1.value.transaction.state }}"
          verticalAlign="center"
        >
          <Option
            id="4b954"
            color="{{ theme.warning }}"
            icon="bold/interface-alert-warning-circle"
            label="Pending"
            value="pending"
          />
          <Option
            id="15db7"
            color="{{ theme.danger }}"
            icon="bold/interface-delete-circle"
            label="Canceled"
            value="canceled"
          />
          <Option
            id="4753e"
            color="{{ theme.success }}"
            icon="bold/interface-validation-check-circle"
            label="Posted"
            value="posted"
          />
        </Status>
        <Button id="button4" text="Post" />
      </Body>
      <Footer>
        <Button
          id="formButton6"
          submit={true}
          submitTargetId="form7"
          text="Submit"
        />
      </Footer>
    </Form>
    <JSONEditor id="jsonEditor1" value="{{ListViewUpdatedValue.value}}" />
    <Container
      id="container1"
      _gap="0px"
      enableFullBleed={true}
      footerPadding="4px 12px"
      headerPadding="4px 12px"
      heightType="fixed"
      overflowType="hidden"
      padding="12px"
      showBody={true}
      showHeader={true}
    >
      <Header>
        <Text
          id="listViewTitle1"
          value="#### Journal Entries"
          verticalAlign="center"
        />
      </Header>
      <View id="c2208" viewKey="View 1">
        <ListViewBeta
          id="listView1"
          _primaryKeys=""
          data="{{ jsonEditor1.value.journal_entries }}"
          formDataKey=""
          itemWidth="200px"
          margin="0"
          numColumns={3}
          padding="12px"
        >
          <Form
            id="form6"
            footerPadding="4px 12px"
            headerPadding="4px 12px"
            padding="12px"
            requireValidation={true}
            resetAfterSubmit={true}
            showBody={true}
          >
            <TextInput
              id="textInput2"
              formDataKey="description"
              label="Descrição"
              labelPosition="top"
              placeholder="Enter value"
              value="{{ item.credit_amount }}"
            >
              <Event
                event="change"
                method="run"
                params={{
                  ordered: [
                    {
                      src: '// Step 1: Retrieve the current value of ListViewUpdatedValue\nlet tempArray = ListViewUpdatedValue.value || []; // Ensure it\'s initialized as an array\n\n// Step 2: Define the position `i` (row index) and the updated key-value pair\nconst i = table5.selectedRowIndex; // Position/index of the control being changed\nconst updatedKey = "description"; // Replace with the actual key being modified\nconsole.log(form6.data[updatedKey]);\nconst updatedValue = form6.data[updatedKey]; // Get the updated value for the key\n\n// Step 3: Validate the index and key\nif (i < 0 || i >= tempArray.length) {\n  utils.showNotification({ title: "Error", message: "Invalid index for update.", type: "error" });\n  return;\n}\nif (updatedValue === undefined) {\n  utils.showNotification({ title: "Error", message: `Invalid key: ${updatedKey}`, type: "error" });\n  return;\n}\n\n// Step 4: Update the specific key in the correct journal entry\nif (tempArray[i] && tempArray[i].hasOwnProperty(updatedKey)) {\n  tempArray[i][updatedKey] = updatedValue; // Update the specific key\n} else {\n  console.warn(`Key "${updatedKey}" not found in the selected object.`);\n}\n\n// Step 5: Set the updated array back to ListViewUpdatedValue\nListViewUpdatedValue.setValue(tempArray);\n\n// Step 6: Log for debugging\nconsole.log("Updated ListViewUpdatedValue:", tempArray);',
                    },
                  ],
                }}
                pluginId=""
                type="script"
                waitMs="0"
                waitType="debounce"
              />
            </TextInput>
            <Select
              id="select7"
              data="{{ Entidades2.data }}"
              emptyMessage="No options"
              formDataKey="entity"
              label="Entidade"
              labelPosition="top"
              labels="{{ item.path }}"
              overlayMaxHeight={375}
              placeholder="Select an option"
              showSelectionIndicator={true}
              value="{{ jsonEditor1.value.journal_entries[i].entity.id }}"
              values="{{ item.id }}"
            >
              <Event
                event="change"
                method="run"
                params={{
                  ordered: [
                    {
                      src: 'try {\n  const updatedKey = "entity"; \n  \n  // Step 1: Retrieve the current value of ListViewUpdatedValue\n  let tempData = JSON.parse(JSON.stringify(ListViewUpdatedValue.value || {})); // Deep clone\n  console.log("Current ListViewUpdatedValue:", tempData);\n\n  // Step 2: Access the journal_entries array\n  let journalEntries = tempData.journal_entries || [];\n  console.log("Current journal_entries:", journalEntries);\n\n  // Step 3: Define the position `i` and the updated key/value\n  //const r = {i}; // Get the index of the row being updated\n  // Replace with the key being updated dynamically\n  const updatedValue = form6.data[updatedKey]; // New value from form6\n  console.log(`Index: ${i}, Key: ${updatedKey}, Value: ${updatedValue}`);\n\n  // Step 4: Validate the index and updated key\n  if (i < 0 || i >= journalEntries.length) {\n    console.error("Error: Invalid row index", i);\n    utils.showNotification({ title: "Error", message: "Invalid row index.", type: "error" });\n    return;\n  }\n\n  if (updatedValue === undefined) {\n    console.error(`Error: Key "${updatedKey}" is invalid or value is undefined.`);\n    utils.showNotification({ title: "Error", message: `Invalid key or value: ${updatedKey}`, type: "error" });\n    return;\n  }\n\n  // Step 5: Update only the specific key in the selected journal entry\n  if (journalEntries[i]) {\n    console.log("Before Update:", journalEntries[i]);\n    journalEntries[i][updatedKey] = updatedValue; // Update only the targeted key\n    console.log("After Update:", journalEntries[i]);\n  } else {\n    console.error("Error: Row not found at index", i);\n    utils.showNotification({ title: "Error", message: "Row not found.", type: "error" });\n    return;\n  }\n\n  // Step 6: Update the main ListViewUpdatedValue object\n  tempData.journal_entries = journalEntries; // Replace the journal_entries array\n  ListViewUpdatedValue.setValue(tempData);\n  console.log("Updated ListViewUpdatedValue:", tempData);\n\n  // Step 7: Confirmation\n  utils.showNotification({ title: "Success", message: "Value updated successfully!", type: "success" });\n} catch (error) {\n  console.error("An unexpected error occurred:", error);\n  utils.showNotification({ title: "Error", message: "An unexpected error occurred. Check logs.", type: "error" });\n}\n',
                    },
                  ],
                }}
                pluginId=""
                type="script"
                waitMs="0"
                waitType="debounce"
              />
            </Select>
            <Select
              id="select5"
              data="{{ accounts.data }}"
              emptyMessage="No options"
              formDataKey="account"
              label="Conta Contábil"
              labelPosition="top"
              labels="{{ item.account_code }} {{ item.name }}"
              overlayMaxHeight={375}
              placeholder="Select an option"
              showSelectionIndicator={true}
              value={
                '{{\n  typeof jsonEditor1.value.journal_entries[i].account === "object" \n    ? jsonEditor1.value.journal_entries[i].account.id \n    : jsonEditor1.value.journal_entries[i].account\n}}'
              }
              values="{{ item.id }}"
            >
              <Event
                event="change"
                method="run"
                params={{
                  ordered: [
                    {
                      src: 'try {\n  const updatedKey = "account"; \n  \n  // Step 1: Retrieve the current value of ListViewUpdatedValue\n  let tempData = JSON.parse(JSON.stringify(ListViewUpdatedValue.value || {})); // Deep clone\n  console.log("Current ListViewUpdatedValue:", tempData);\n\n  // Step 2: Access the journal_entries array\n  let journalEntries = tempData.journal_entries || [];\n  console.log("Current journal_entries:", journalEntries);\n\n  // Step 3: Define the position `i` and the updated key/value\n  //const r = {i}; // Get the index of the row being updated\n  // Replace with the key being updated dynamically\n  const updatedValue = form6.data[updatedKey]; // New value from form6\n  console.log(`Index: ${i}, Key: ${updatedKey}, Value: ${updatedValue}`);\n\n  // Step 4: Validate the index and updated key\n  if (i < 0 || i >= journalEntries.length) {\n    console.error("Error: Invalid row index", i);\n    utils.showNotification({ title: "Error", message: "Invalid row index.", type: "error" });\n    return;\n  }\n\n  if (updatedValue === undefined) {\n    console.error(`Error: Key "${updatedKey}" is invalid or value is undefined.`);\n    utils.showNotification({ title: "Error", message: `Invalid key or value: ${updatedKey}`, type: "error" });\n    return;\n  }\n\n  // Step 5: Update only the specific key in the selected journal entry\n  if (journalEntries[i]) {\n    console.log("Before Update:", journalEntries[i]);\n    journalEntries[i][updatedKey] = updatedValue; // Update only the targeted key\n    console.log("After Update:", journalEntries[i]);\n  } else {\n    console.error("Error: Row not found at index", i);\n    utils.showNotification({ title: "Error", message: "Row not found.", type: "error" });\n    return;\n  }\n\n  // Step 6: Update the main ListViewUpdatedValue object\n  tempData.journal_entries = journalEntries; // Replace the journal_entries array\n  ListViewUpdatedValue.setValue(tempData);\n  console.log("Updated ListViewUpdatedValue:", tempData);\n\n  // Step 7: Confirmation\n  utils.showNotification({ title: "Success", message: "Value updated successfully!", type: "success" });\n} catch (error) {\n  console.error("An unexpected error occurred:", error);\n  utils.showNotification({ title: "Error", message: "An unexpected error occurred. Check logs.", type: "error" });\n}\n',
                    },
                  ],
                }}
                pluginId=""
                type="script"
                waitMs="0"
                waitType="debounce"
              />
            </Select>
            <NumberInput
              id="numberInput28"
              currency="USD"
              formDataKey="credit_amount"
              inputValue={0}
              label="Crédito"
              labelPosition="top"
              placeholder="Enter value"
              showClear={true}
              showSeparators={true}
              showStepper={true}
              value="{{ jsonEditor1.value.journal_entries[i].credit_amount }}"
            >
              <Event
                event="change"
                method="run"
                params={{
                  ordered: [
                    {
                      src: 'try {\n  const updatedKey = "credit_amount"; \n  \n  // Step 1: Retrieve the current value of ListViewUpdatedValue\n  let tempData = JSON.parse(JSON.stringify(ListViewUpdatedValue.value || {})); // Deep clone\n  console.log("Current ListViewUpdatedValue:", tempData);\n\n  // Step 2: Access the journal_entries array\n  let journalEntries = tempData.journal_entries || [];\n  console.log("Current journal_entries:", journalEntries);\n\n  // Step 3: Define the position `i` and the updated key/value\n  //const r = {i}; // Get the index of the row being updated\n  // Replace with the key being updated dynamically\n  const updatedValue = form6.data[updatedKey]; // New value from form6\n  console.log(`Index: ${i}, Key: ${updatedKey}, Value: ${updatedValue}`);\n\n  // Step 4: Validate the index and updated key\n  if (i < 0 || i >= journalEntries.length) {\n    console.error("Error: Invalid row index", i);\n    utils.showNotification({ title: "Error", message: "Invalid row index.", type: "error" });\n    return;\n  }\n\n  if (updatedValue === undefined) {\n    console.error(`Error: Key "${updatedKey}" is invalid or value is undefined.`);\n    utils.showNotification({ title: "Error", message: `Invalid key or value: ${updatedKey}`, type: "error" });\n    return;\n  }\n\n  // Step 5: Update only the specific key in the selected journal entry\n  if (journalEntries[i]) {\n    console.log("Before Update:", journalEntries[i]);\n    journalEntries[i][updatedKey] = updatedValue; // Update only the targeted key\n    console.log("After Update:", journalEntries[i]);\n  } else {\n    console.error("Error: Row not found at index", i);\n    utils.showNotification({ title: "Error", message: "Row not found.", type: "error" });\n    return;\n  }\n\n  // Step 6: Update the main ListViewUpdatedValue object\n  tempData.journal_entries = journalEntries; // Replace the journal_entries array\n  ListViewUpdatedValue.setValue(tempData);\n  console.log("Updated ListViewUpdatedValue:", tempData);\n\n  // Step 7: Confirmation\n  utils.showNotification({ title: "Success", message: "Value updated successfully!", type: "success" });\n} catch (error) {\n  console.error("An unexpected error occurred:", error);\n  utils.showNotification({ title: "Error", message: "An unexpected error occurred. Check logs.", type: "error" });\n}\n',
                    },
                  ],
                }}
                pluginId=""
                type="script"
                waitMs="0"
                waitType="debounce"
              />
            </NumberInput>
            <NumberInput
              id="numberInput29"
              currency="USD"
              formDataKey="debit_amount"
              inputValue={0}
              label="Débito"
              labelPosition="top"
              placeholder="Enter value"
              showClear={true}
              showSeparators={true}
              showStepper={true}
              value="{{ jsonEditor1.value.journal_entries[i].debit_amount }}"
            >
              <Event
                event="change"
                method="run"
                params={{
                  ordered: [
                    {
                      src: 'try {\n  const updatedKey = "debit_amount"; \n  \n  // Step 1: Retrieve the current value of ListViewUpdatedValue\n  let tempData = JSON.parse(JSON.stringify(ListViewUpdatedValue.value || {})); // Deep clone\n  console.log("Current ListViewUpdatedValue:", tempData);\n\n  // Step 2: Access the journal_entries array\n  let journalEntries = tempData.journal_entries || [];\n  console.log("Current journal_entries:", journalEntries);\n\n  // Step 3: Define the position `i` and the updated key/value\n  //const r = {i}; // Get the index of the row being updated\n  // Replace with the key being updated dynamically\n  const updatedValue = form6.data[updatedKey]; // New value from form6\n  console.log(`Index: ${i}, Key: ${updatedKey}, Value: ${updatedValue}`);\n\n  // Step 4: Validate the index and updated key\n  if (i < 0 || i >= journalEntries.length) {\n    console.error("Error: Invalid row index", i);\n    utils.showNotification({ title: "Error", message: "Invalid row index.", type: "error" });\n    return;\n  }\n\n  if (updatedValue === undefined) {\n    console.error(`Error: Key "${updatedKey}" is invalid or value is undefined.`);\n    utils.showNotification({ title: "Error", message: `Invalid key or value: ${updatedKey}`, type: "error" });\n    return;\n  }\n\n  // Step 5: Update only the specific key in the selected journal entry\n  if (journalEntries[i]) {\n    console.log("Before Update:", journalEntries[i]);\n    journalEntries[i][updatedKey] = updatedValue; // Update only the targeted key\n    console.log("After Update:", journalEntries[i]);\n  } else {\n    console.error("Error: Row not found at index", i);\n    utils.showNotification({ title: "Error", message: "Row not found.", type: "error" });\n    return;\n  }\n\n  // Step 6: Update the main ListViewUpdatedValue object\n  tempData.journal_entries = journalEntries; // Replace the journal_entries array\n  ListViewUpdatedValue.setValue(tempData);\n  console.log("Updated ListViewUpdatedValue:", tempData);\n\n  // Step 7: Confirmation\n  utils.showNotification({ title: "Success", message: "Value updated successfully!", type: "success" });\n} catch (error) {\n  console.error("An unexpected error occurred:", error);\n  utils.showNotification({ title: "Error", message: "An unexpected error occurred. Check logs.", type: "error" });\n}\n',
                    },
                  ],
                }}
                pluginId=""
                type="script"
                waitMs="0"
                waitType="debounce"
              />
            </NumberInput>
            <Select
              id="select3"
              emptyMessage="No options"
              formDataKey="state"
              itemMode="static"
              label="Status"
              labelPosition="top"
              overlayMaxHeight={375}
              placeholder="Select an option"
              showSelectionIndicator={true}
              value="{{ item.state }}"
            >
              <Option id="87d84" label="Pending" value="pending" />
              <Option id="71a71" label="Posted" value="posted" />
              <Option id="4d3e4" label="Cancelled" value="cancelled" />
            </Select>
          </Form>
        </ListViewBeta>
      </View>
      <Event
        event="change"
        method="run"
        params={{
          ordered: [
            {
              src: "query.trigger({\n  additionalScope: {\n    formChangeSet: form6.data\n  }\n})",
            },
          ],
        }}
        pluginId=""
        type="script"
        waitMs="0"
        waitType="debounce"
      />
    </Container>
  </Header>
  <Footer>
    <Button id="button3" text="Submit">
      <Event
        event="click"
        method="setValue"
        params={{ ordered: [{ value: "{{ !variable5.value }}" }] }}
        pluginId="variable5"
        type="state"
        waitMs="0"
        waitType="debounce"
      />
    </Button>
  </Footer>
  <Event
    event="show"
    method="trigger"
    params={{ ordered: [] }}
    pluginId="ModalFrame2Show"
    type="datasource"
    waitMs="0"
    waitType="debounce"
  />
</ModalFrame>
