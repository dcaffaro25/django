<Container
  id="container10"
  footerPadding="4px 12px"
  headerPadding="4px 12px"
  padding="12px"
  showBody={true}
>
  <View id="7e19a" viewKey="View 1">
    <Text
      id="containerTitle12"
      value="###### {{ item.import_results.filename }}"
      verticalAlign="center"
    />
    <Button
      id="button21"
      style={{ ordered: [] }}
      styleVariant="outline"
      text="Importar"
    >
      <Event
        event="click"
        method="run"
        params={{
          ordered: [
            {
              src: 'const SelectedFile = {\n  "files": [fileDropzoneOFX.value[i]]\n}\nOFXTransaction_import3.trigger({\n  additionalScope: {\n    content: SelectedFile\n  }\n});',
            },
          ],
        }}
        pluginId=""
        type="script"
        waitMs="0"
        waitType="debounce"
      />
    </Button>
    <Text id="text26" value="**Banco**" verticalAlign="center" />
    <Text
      id="text25"
      value="**Transações**
{{ item.import_results.transactions.length }}"
      verticalAlign="center"
    />
    <IconText
      id="iconText5"
      icon={
        '{{  "/icon:bold/interface-setting-menu-horizontal-circle-alternate" }}'
      }
      style={{
        ordered: [
          {
            iconColor:
              '{{item.import_results.bank.result === "Error" ? "danger" : "black" }}',
          },
          {
            color:
              '{{item.import_results.bank.result === "Error" ? "danger" : "black" }}',
          },
        ],
      }}
      text={
        '{{ \n  item.import_results.bank.result === "Success"\n    ? `${item.import_results.bank.value.bank_code} ${item.import_results.bank.value.name}`\n    : `${item.import_results.bank.value}`\n}}\n'
      }
    >
      <Event
        event="click"
        method="run"
        params={{
          ordered: [
            {
              src: '(item.import_results.bank.result === "Success") ?\n    manageBanks.setIn(["current_record"], item.import_results.bank.value)\n    :\n  manageBanks.setIn(["current_record"],[])  \n  manageBanks.setIn(["form_fields"], {"bank_code": { \n      "default_value": item.import_results.bank.value, \n      "disabled": true\n    }});\nmanageBanks.setIn(["modal_addedit_show"], true);\n',
            },
          ],
        }}
        pluginId=""
        type="script"
        waitMs="0"
        waitType="debounce"
      />
    </IconText>
    <Text id="text27" value="**Conta**" verticalAlign="center" />
    <IconText
      id="iconText6"
      icon={
        '{{  "/icon:bold/interface-setting-menu-horizontal-circle-alternate" }}'
      }
      style={{
        ordered: [
          {
            iconColor:
              '{{item.import_results.account.result === "Error" ? "danger" : "black" }}',
          },
          {
            color:
              '{{item.import_results.account.result === "Error" ? "danger" : "black" }}',
          },
        ],
      }}
      text={
        '{{\n  item.import_results.account.result === "Success"\n    ? `${item.import_results.account.value.entity.name} ${item.import_results.account.value.account_number}`\n    : `${item.import_results.account.value}`\n}}'
      }
    >
      <Event
        event="click"
        method="run"
        params={{
          ordered: [
            {
              src: 'const newObj = {\n  ...manageBankAccounts.value,  // Copy the existing state\n  current_record: item.import_results.bank.result === "Success"\n    ? item.import_results.account.value\n    : [],\n  form_fields: {\n    account_number: {\n      default_value: item.import_results.account.value,\n      disabled: true\n    }\n  },\n  modal_addedit_show: true\n};\n\nmanageBankAccounts.setValue(newObj);\n',
            },
          ],
        }}
        pluginId=""
        type="script"
        waitMs="0"
        waitType="debounce"
      />
    </IconText>
  </View>
</Container>
