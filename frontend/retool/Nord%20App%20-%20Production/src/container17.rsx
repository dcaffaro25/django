<Container
  id="container17"
  footerPadding="4px 12px"
  headerPadding="4px 12px"
  padding="12px"
  showBody={true}
>
  <View id="7e19a" viewKey="View 1">
    <Text
      id="containerTitle18"
      value="###### {{ item.import_results.filename }}"
      verticalAlign="center"
    />
    <Button
      id="button37"
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
              src: 'const SelectedFile = {\n  "files": [fileDropzoneOFX2.value[i]]\n}\nOFXTransaction_import6.trigger({\n  additionalScope: {\n    content: SelectedFile\n  }\n});',
            },
          ],
        }}
        pluginId=""
        type="script"
        waitMs="0"
        waitType="debounce"
      />
    </Button>
    <Text id="text38" value="**Conta**" verticalAlign="center" />
    <Text id="text37" value="**Banco**" verticalAlign="center" />
    <IconText
      id="iconText7"
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
              src: '(item.import_results.bank.result === "Success") ?\n    manageBanks3.setIn(["current_record"], item.import_results.bank.value)\n    :\n  manageBanks3.setIn(["current_record"],[])  \n  manageBanks3.setIn(["form_fields"], {"bank_code": { \n      "default_value": item.import_results.bank.value, \n      "disabled": true\n    }});\nmanageBanks3.setIn(["modal_addedit_show"], true);\n',
            },
          ],
        }}
        pluginId=""
        type="script"
        waitMs="0"
        waitType="debounce"
      />
    </IconText>
    <IconText
      id="iconText8"
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
              src: 'const newObj = {\n  ...manageBankAccounts2.value,  // Copy the existing state\n  current_record: item.import_results.bank.result === "Success"\n    ? item.import_results.account.value\n    : [],\n  form_fields: {\n    account_number: {\n      default_value: item.import_results.account.value,\n      disabled: true\n    }\n  },\n  modal_addedit_show: true\n};\n\nmanageBankAccounts2.setValue(newObj);\n',
            },
          ],
        }}
        pluginId=""
        type="script"
        waitMs="0"
        waitType="debounce"
      />
    </IconText>
    <Divider id="divider25" />
    <Text
      id="text57"
      value="**Data**
{{ (() => {
  const txs = item?.import_results?.transactions ?? [];
  const field = 'date';           // <- change if your key differs
  const tz = 'America/Sao_Paulo';

  const ds = txs.map(t => new Date(t?.[field])).filter(d => !isNaN(d));
  if (!ds.length) return '—';

  const min = new Date(Math.min(...ds));
  const max = new Date(Math.max(...ds));

  const yNum = new Intl.DateTimeFormat('en-US', { timeZone: tz, year: 'numeric' });
  const parts = d => Object.fromEntries(
    new Intl.DateTimeFormat('pt-BR', { timeZone: tz, day: '2-digit', month: '2-digit', year: '2-digit' })
      .formatToParts(d).map(p => [p.type, p.value])
  );

  const a = parts(min), b = parts(max);
  const sameYear = yNum.format(min) === yNum.format(max);
  const sameDay  = sameYear && a.day === b.day && a.month === b.month;

  if (sameDay) return `${a.day}/${a.month}/${a.year}`;
  return sameYear
    ? `${a.day}/${a.month} - ${b.day}/${b.month}/${b.year}`
    : `${a.day}/${a.month}/${a.year} - ${b.day}/${b.month}/${b.year}`;
})() }}"
      verticalAlign="center"
    />
    <Text
      id="text58"
      value="**Movimentação**
{{ (() => {
  const txs = item?.import_results?.transactions ?? [];
  const amountKey = 'amount';
  const typeKey = 'transaction_type'; // expects 'CREDIT' or 'DEBIT' (any case)

  const toNumber = (v) => {
    if (typeof v === 'number') return v;
    if (v == null) return 0;
    let s = String(v).trim().replace(/[^\d,.\-]/g, '');
    if (s.includes(',') && s.includes('.')) s = s.replace(/\./g, '').replace(',', '.');
    else if (s.includes(',') && !s.includes('.')) s = s.replace(',', '.');
    const n = Number(s);
    return Number.isFinite(n) ? n : 0;
  };

  const cents = txs.reduce((sum, t) => {
    const amt = Math.abs(toNumber(t?.[amountKey]));
    const kind = String(t?.[typeKey] ?? '').toLowerCase();
    const sign = (kind === 'debit') ? -1 : 1; // credit = +, debit = -
    return sum + Math.round(amt * sign * 100);
  }, 0);

  const total = cents / 100;
  return new Intl.NumberFormat('pt-BR', {
    style: 'currency',
    currency: 'BRL',
    minimumFractionDigits: 2,
    maximumFractionDigits: 2
  }).format(total);
})() }}"
      verticalAlign="center"
    />
    <Text
      id="text36"
      value="**Transações**
{{ item.import_results.transactions.length }}"
      verticalAlign="center"
    />
    <Divider id="divider26" />
    <Text
      id="text59"
      value="**Transações**
{{ item.import_results.warning }}"
      verticalAlign="center"
    />
  </View>
</Container>
