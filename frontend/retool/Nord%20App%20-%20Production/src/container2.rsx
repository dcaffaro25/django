<Container
  id="container2"
  footerPadding="4px 12px"
  headerPadding="4px 12px"
  padding="12px"
  showBody={true}
  showHeader={true}
>
  <Header>
    <Text id="containerTitle1" value="#### Sandbox" verticalAlign="center" />
    <Button
      id="button12"
      iconBefore="bold/interface-arrows-synchronize"
      style={{ ordered: [] }}
      styleVariant="outline"
    >
      <Event
        event="click"
        method="trigger"
        params={{ ordered: [] }}
        pluginId="IntegrationRule_validate"
        type="datasource"
        waitMs="0"
        waitType="debounce"
      />
    </Button>
  </Header>
  <View id="afd51" viewKey="View 1">
    <Button
      id="button9"
      iconBefore="bold/programming-script-code"
      style={{ ordered: [] }}
      styleVariant="outline"
    >
      <Event
        event="click"
        method="show"
        params={{ ordered: [] }}
        pluginId="modalCodeEditorRegra"
        type="widget"
        waitMs="0"
        waitType="debounce"
      />
    </Button>
    <Text id="text3" value="**Setup**" verticalAlign="center" />
    <CustomComponent
      id="CodeEditorSetup"
      iframeCode={
        '<!-- 1) CodeMirror + Python mode -->\n<script\n  src="https://cdnjs.cloudflare.com/ajax/libs/codemirror/5.65.11/codemirror.min.js"\n  integrity="sha512-rdFIN28+neM8H8zNsjRClhJb1fIYby2YCNmoqwnqBDEvZgpcp7MJiX8Wd+Oi6KcJOMOuvGztjrsI59rly9BsVQ=="\n  crossorigin="anonymous"\n  referrerpolicy="no-referrer">\n</script>\n<script\n  src="https://cdnjs.cloudflare.com/ajax/libs/codemirror/5.65.11/mode/python/python.min.js"\n  referrerpolicy="no-referrer">\n</script>\n\n<!-- 2) Basic CodeMirror CSS + theme (Eclipse or any other) -->\n<style>\n@import url("https://cdnjs.cloudflare.com/ajax/libs/codemirror/5.65.11/codemirror.min.css");\n@import url("https://cdnjs.cloudflare.com/ajax/libs/codemirror/5.65.11/theme/icecoder.min.css");\n\nhtml, body {\n  height: 100%;\n  width: 100%;\n  overflow: hidden;\n  padding: 0;\n  margin: 0;\n  box-sizing: border-box;\n}\nhtml {\n  border: 1px solid #d1d1d1;\n  border-radius: 4px;\n}\nbody {\n  padding: 0 4px;\n  overflow: auto;\n}\n.CodeMirror {\n  height: auto;\n  font-family: monospace;\n  font-size: 13px;\n}\n</style>\n\n<!-- 3) JS to manage the editor and Retool interactions -->\n<script>\n/** Our CodeMirror instance */\nlet codeEditor = null;\n/** Tracks the last code we accepted (from the user or from Retool) */\nlet mostRecentCode = "";\n/** True when we are in the middle of an external setValue() */\nlet isExternalUpdate = false;\n/** Used for debouncing calls to Retool.modelUpdate */\nlet updateTimer = null;\n\n/** Safely initialize CodeMirror */\nfunction createEditor() {\n  if (typeof CodeMirror === "undefined") {\n    setTimeout(createEditor, 50);\n    return;\n  }\n\n  codeEditor = CodeMirror(document.body, {\n    value: "",\n    mode: "python",\n    lineNumbers: true,\n    theme: "icecoder",\n    indentUnit: 4,     // Typical Python indentation is 4\n    tabSize: 4,\n    /*\n    extraKeys: {\n      // If you also want Tab indentation:\n      Tab: (cm) => {\n        if (cm.somethingSelected()) {\n          cm.indentSelection("add");\n        } else {\n          // Insert 4 spaces\n          cm.replaceSelection("    ", "end", "+input");\n        }\n      },\n      "Shift-Tab": (cm) => cm.indentSelection("subtract")\n    }\n    */\n  });\n\n  // When the user edits the code, update Retool after a small debounce\n  codeEditor.on("change", () => {\n    if (isExternalUpdate) {\n      return; // Don\'t re-fire changes caused by ourselves\n    }\n    clearTimeout(updateTimer);\n    updateTimer = setTimeout(() => {\n      const newVal = normalizeLineEndings(codeEditor.getValue());\n      // Only update if truly changed\n      if (newVal !== mostRecentCode) {\n        mostRecentCode = newVal;\n        console.log("[CodeMirror -> Retool] Updated code:", newVal);\n        window.Retool.modelUpdate({ code: newVal });\n      }\n    }, 50); // wait 200ms after user stops typing\n  });\n}\n\n/** Safely set the CodeMirror contents */\nfunction setCode(code) {\n  if (!codeEditor) {\n    setTimeout(() => setCode(code), 50);\n    return;\n  }\n  const norm = normalizeLineEndings(code);\n  const currentNorm = normalizeLineEndings(codeEditor.getValue());\n  if (norm !== currentNorm) {\n    isExternalUpdate = true;\n    console.log("[Retool -> CodeMirror] Setting code:", norm);\n    codeEditor.setValue(norm);\n    isExternalUpdate = false;\n  }\n}\n\n/** Normalize line endings to "\\n" to avoid mismatch */\nfunction normalizeLineEndings(str) {\n  return (str || "").replace(/\\r\\n/g, "\\n");\n}\n\n/** Listen for model changes from Retool */\nwindow.Retool.subscribe((model) => {\n  if (!model || typeof model.code !== "string") return;\n  const newVal = normalizeLineEndings(model.code);\n  if (newVal !== mostRecentCode) {\n    mostRecentCode = newVal;\n    setCode(newVal);\n  }\n});\n\n/** Start up the editor */\ncreateEditor();\n</script>\n'
      }
      model=""
    />
    <Button
      id="button13"
      iconBefore="bold/programming-script-code"
      style={{ ordered: [] }}
      styleVariant="outline"
    >
      <Event
        event="click"
        method="show"
        params={{ ordered: [] }}
        pluginId="modalCodeEditorRegra"
        type="widget"
        waitMs="0"
        waitType="debounce"
      />
    </Button>
    <Text id="text10" value="**Payload Exemplo**" verticalAlign="center" />
    <CustomComponent
      id="CodeEditorPayload"
      iframeCode={
        '<!-- 1) CodeMirror + Python mode -->\n<script\n  src="https://cdnjs.cloudflare.com/ajax/libs/codemirror/5.65.11/codemirror.min.js"\n  integrity="sha512-rdFIN28+neM8H8zNsjRClhJb1fIYby2YCNmoqwnqBDEvZgpcp7MJiX8Wd+Oi6KcJOMOuvGztjrsI59rly9BsVQ=="\n  crossorigin="anonymous"\n  referrerpolicy="no-referrer">\n</script>\n<script\n  src="https://cdnjs.cloudflare.com/ajax/libs/codemirror/5.65.11/mode/python/python.min.js"\n  referrerpolicy="no-referrer">\n</script>\n\n<!-- 2) Basic CodeMirror CSS + theme (Eclipse or any other) -->\n<style>\n@import url("https://cdnjs.cloudflare.com/ajax/libs/codemirror/5.65.11/codemirror.min.css");\n@import url("https://cdnjs.cloudflare.com/ajax/libs/codemirror/5.65.11/theme/icecoder.min.css");\n\nhtml, body {\n  height: 100%;\n  width: 100%;\n  overflow: hidden;\n  padding: 0;\n  margin: 0;\n  box-sizing: border-box;\n}\nhtml {\n  border: 1px solid #d1d1d1;\n  border-radius: 4px;\n}\nbody {\n  padding: 0 4px;\n  overflow: auto;\n}\n.CodeMirror {\n  height: auto;\n  font-family: monospace;\n  font-size: 13px;\n}\n</style>\n\n<!-- 3) JS to manage the editor and Retool interactions -->\n<script>\n/** Our CodeMirror instance */\nlet codeEditor = null;\n/** Tracks the last code we accepted (from the user or from Retool) */\nlet mostRecentCode = "";\n/** True when we are in the middle of an external setValue() */\nlet isExternalUpdate = false;\n/** Used for debouncing calls to Retool.modelUpdate */\nlet updateTimer = null;\n\n/** Safely initialize CodeMirror */\nfunction createEditor() {\n  if (typeof CodeMirror === "undefined") {\n    setTimeout(createEditor, 50);\n    return;\n  }\n\n  codeEditor = CodeMirror(document.body, {\n    value: "",\n    mode: "python",\n    lineNumbers: true,\n    theme: "icecoder",\n    indentUnit: 4,     // Typical Python indentation is 4\n    tabSize: 4,\n    /*\n    extraKeys: {\n      // If you also want Tab indentation:\n      Tab: (cm) => {\n        if (cm.somethingSelected()) {\n          cm.indentSelection("add");\n        } else {\n          // Insert 4 spaces\n          cm.replaceSelection("    ", "end", "+input");\n        }\n      },\n      "Shift-Tab": (cm) => cm.indentSelection("subtract")\n    }\n    */\n  });\n\n  // When the user edits the code, update Retool after a small debounce\n  codeEditor.on("change", () => {\n    if (isExternalUpdate) {\n      return; // Don\'t re-fire changes caused by ourselves\n    }\n    clearTimeout(updateTimer);\n    updateTimer = setTimeout(() => {\n      const newVal = normalizeLineEndings(codeEditor.getValue());\n      // Only update if truly changed\n      if (newVal !== mostRecentCode) {\n        mostRecentCode = newVal;\n        console.log("[CodeMirror -> Retool] Updated code:", newVal);\n        window.Retool.modelUpdate({ code: newVal });\n      }\n    }, 50); // wait 200ms after user stops typing\n  });\n}\n\n/** Safely set the CodeMirror contents */\nfunction setCode(code) {\n  if (!codeEditor) {\n    setTimeout(() => setCode(code), 50);\n    return;\n  }\n  const norm = normalizeLineEndings(code);\n  const currentNorm = normalizeLineEndings(codeEditor.getValue());\n  if (norm !== currentNorm) {\n    isExternalUpdate = true;\n    console.log("[Retool -> CodeMirror] Setting code:", norm);\n    codeEditor.setValue(norm);\n    isExternalUpdate = false;\n  }\n}\n\n/** Normalize line endings to "\\n" to avoid mismatch */\nfunction normalizeLineEndings(str) {\n  return (str || "").replace(/\\r\\n/g, "\\n");\n}\n\n/** Listen for model changes from Retool */\nwindow.Retool.subscribe((model) => {\n  if (!model || typeof model.code !== "string") return;\n  const newVal = normalizeLineEndings(model.code);\n  if (newVal !== mostRecentCode) {\n    mostRecentCode = newVal;\n    setCode(newVal);\n  }\n});\n\n/** Start up the editor */\ncreateEditor();\n</script>\n'
      }
      model=""
    />
    <Button
      id="button14"
      iconBefore="bold/programming-script-code"
      style={{ ordered: [] }}
      styleVariant="outline"
    >
      <Event
        event="click"
        method="show"
        params={{ ordered: [] }}
        pluginId="modalCodeEditorRegra"
        type="widget"
        waitMs="0"
        waitType="debounce"
      />
    </Button>
    <Text
      id="text8"
      value="**Payload Após Condições**"
      verticalAlign="center"
    />
    <CustomComponent
      id="CodeEditorPayloadFiltrado"
      iframeCode={
        '<!-- 1) CodeMirror + Python mode -->\n<script\n  src="https://cdnjs.cloudflare.com/ajax/libs/codemirror/5.65.11/codemirror.min.js"\n  integrity="sha512-rdFIN28+neM8H8zNsjRClhJb1fIYby2YCNmoqwnqBDEvZgpcp7MJiX8Wd+Oi6KcJOMOuvGztjrsI59rly9BsVQ=="\n  crossorigin="anonymous"\n  referrerpolicy="no-referrer">\n</script>\n<script\n  src="https://cdnjs.cloudflare.com/ajax/libs/codemirror/5.65.11/mode/python/python.min.js"\n  referrerpolicy="no-referrer">\n</script>\n\n<!-- 2) Basic CodeMirror CSS + theme (Eclipse or any other) -->\n<style>\n@import url("https://cdnjs.cloudflare.com/ajax/libs/codemirror/5.65.11/codemirror.min.css");\n@import url("https://cdnjs.cloudflare.com/ajax/libs/codemirror/5.65.11/theme/icecoder.min.css");\n\nhtml, body {\n  height: 100%;\n  width: 100%;\n  overflow: hidden;\n  padding: 0;\n  margin: 0;\n  box-sizing: border-box;\n}\nhtml {\n  border: 1px solid #d1d1d1;\n  border-radius: 4px;\n}\nbody {\n  padding: 0 4px;\n  overflow: auto;\n}\n.CodeMirror {\n  height: auto;\n  font-family: monospace;\n  font-size: 13px;\n}\n</style>\n\n<!-- 3) JS to manage the editor and Retool interactions -->\n<script>\n/** Our CodeMirror instance */\nlet codeEditor = null;\n/** Tracks the last code we accepted (from the user or from Retool) */\nlet mostRecentCode = "";\n/** True when we are in the middle of an external setValue() */\nlet isExternalUpdate = false;\n/** Used for debouncing calls to Retool.modelUpdate */\nlet updateTimer = null;\n\n/** Safely initialize CodeMirror */\nfunction createEditor() {\n  if (typeof CodeMirror === "undefined") {\n    setTimeout(createEditor, 50);\n    return;\n  }\n\n  codeEditor = CodeMirror(document.body, {\n    value: "",\n    mode: "python",\n    lineNumbers: true,\n    theme: "icecoder",\n    indentUnit: 4,     // Typical Python indentation is 4\n    tabSize: 4,\n    /*\n    extraKeys: {\n      // If you also want Tab indentation:\n      Tab: (cm) => {\n        if (cm.somethingSelected()) {\n          cm.indentSelection("add");\n        } else {\n          // Insert 4 spaces\n          cm.replaceSelection("    ", "end", "+input");\n        }\n      },\n      "Shift-Tab": (cm) => cm.indentSelection("subtract")\n    }\n    */\n  });\n\n  // When the user edits the code, update Retool after a small debounce\n  codeEditor.on("change", () => {\n    if (isExternalUpdate) {\n      return; // Don\'t re-fire changes caused by ourselves\n    }\n    clearTimeout(updateTimer);\n    updateTimer = setTimeout(() => {\n      const newVal = normalizeLineEndings(codeEditor.getValue());\n      // Only update if truly changed\n      if (newVal !== mostRecentCode) {\n        mostRecentCode = newVal;\n        console.log("[CodeMirror -> Retool] Updated code:", newVal);\n        window.Retool.modelUpdate({ code: newVal });\n      }\n    }, 50); // wait 200ms after user stops typing\n  });\n}\n\n/** Safely set the CodeMirror contents */\nfunction setCode(code) {\n  if (!codeEditor) {\n    setTimeout(() => setCode(code), 50);\n    return;\n  }\n  const norm = normalizeLineEndings(code);\n  const currentNorm = normalizeLineEndings(codeEditor.getValue());\n  if (norm !== currentNorm) {\n    isExternalUpdate = true;\n    console.log("[Retool -> CodeMirror] Setting code:", norm);\n    codeEditor.setValue(norm);\n    isExternalUpdate = false;\n  }\n}\n\n/** Normalize line endings to "\\n" to avoid mismatch */\nfunction normalizeLineEndings(str) {\n  return (str || "").replace(/\\r\\n/g, "\\n");\n}\n\n/** Listen for model changes from Retool */\nwindow.Retool.subscribe((model) => {\n  if (!model || typeof model.code !== "string") return;\n  const newVal = normalizeLineEndings(model.code);\n  if (newVal !== mostRecentCode) {\n    mostRecentCode = newVal;\n    setCode(newVal);\n  }\n});\n\n/** Start up the editor */\ncreateEditor();\n</script>\n'
      }
      model=""
    />
    <Button
      id="button15"
      iconBefore="bold/programming-script-code"
      style={{ ordered: [] }}
      styleVariant="outline"
    >
      <Event
        event="click"
        method="show"
        params={{ ordered: [] }}
        pluginId="modalCodeEditorRegra"
        type="widget"
        waitMs="0"
        waitType="debounce"
      />
    </Button>
    <Text id="text9" value="**Resultado**" verticalAlign="center" />
    <CustomComponent
      id="CodeEditorPayloadFiltrado2"
      iframeCode={
        '<!-- 1) CodeMirror + Python mode -->\n<script\n  src="https://cdnjs.cloudflare.com/ajax/libs/codemirror/5.65.11/codemirror.min.js"\n  integrity="sha512-rdFIN28+neM8H8zNsjRClhJb1fIYby2YCNmoqwnqBDEvZgpcp7MJiX8Wd+Oi6KcJOMOuvGztjrsI59rly9BsVQ=="\n  crossorigin="anonymous"\n  referrerpolicy="no-referrer">\n</script>\n<script\n  src="https://cdnjs.cloudflare.com/ajax/libs/codemirror/5.65.11/mode/python/python.min.js"\n  referrerpolicy="no-referrer">\n</script>\n\n<!-- 2) Basic CodeMirror CSS + theme (Eclipse or any other) -->\n<style>\n@import url("https://cdnjs.cloudflare.com/ajax/libs/codemirror/5.65.11/codemirror.min.css");\n@import url("https://cdnjs.cloudflare.com/ajax/libs/codemirror/5.65.11/theme/icecoder.min.css");\n\nhtml, body {\n  height: 100%;\n  width: 100%;\n  overflow: hidden;\n  padding: 0;\n  margin: 0;\n  box-sizing: border-box;\n}\nhtml {\n  border: 1px solid #d1d1d1;\n  border-radius: 4px;\n}\nbody {\n  padding: 0 4px;\n  overflow: auto;\n}\n.CodeMirror {\n  height: auto;\n  font-family: monospace;\n  font-size: 13px;\n}\n</style>\n\n<!-- 3) JS to manage the editor and Retool interactions -->\n<script>\n/** Our CodeMirror instance */\nlet codeEditor = null;\n/** Tracks the last code we accepted (from the user or from Retool) */\nlet mostRecentCode = "";\n/** True when we are in the middle of an external setValue() */\nlet isExternalUpdate = false;\n/** Used for debouncing calls to Retool.modelUpdate */\nlet updateTimer = null;\n\n/** Safely initialize CodeMirror */\nfunction createEditor() {\n  if (typeof CodeMirror === "undefined") {\n    setTimeout(createEditor, 50);\n    return;\n  }\n\n  codeEditor = CodeMirror(document.body, {\n    value: "",\n    mode: "python",\n    lineNumbers: true,\n    theme: "icecoder",\n    indentUnit: 4,     // Typical Python indentation is 4\n    tabSize: 4,\n    /*\n    extraKeys: {\n      // If you also want Tab indentation:\n      Tab: (cm) => {\n        if (cm.somethingSelected()) {\n          cm.indentSelection("add");\n        } else {\n          // Insert 4 spaces\n          cm.replaceSelection("    ", "end", "+input");\n        }\n      },\n      "Shift-Tab": (cm) => cm.indentSelection("subtract")\n    }\n    */\n  });\n\n  // When the user edits the code, update Retool after a small debounce\n  codeEditor.on("change", () => {\n    if (isExternalUpdate) {\n      return; // Don\'t re-fire changes caused by ourselves\n    }\n    clearTimeout(updateTimer);\n    updateTimer = setTimeout(() => {\n      const newVal = normalizeLineEndings(codeEditor.getValue());\n      // Only update if truly changed\n      if (newVal !== mostRecentCode) {\n        mostRecentCode = newVal;\n        console.log("[CodeMirror -> Retool] Updated code:", newVal);\n        window.Retool.modelUpdate({ code: newVal });\n      }\n    }, 50); // wait 200ms after user stops typing\n  });\n}\n\n/** Safely set the CodeMirror contents */\nfunction setCode(code) {\n  if (!codeEditor) {\n    setTimeout(() => setCode(code), 50);\n    return;\n  }\n  const norm = normalizeLineEndings(code);\n  const currentNorm = normalizeLineEndings(codeEditor.getValue());\n  if (norm !== currentNorm) {\n    isExternalUpdate = true;\n    console.log("[Retool -> CodeMirror] Setting code:", norm);\n    codeEditor.setValue(norm);\n    isExternalUpdate = false;\n  }\n}\n\n/** Normalize line endings to "\\n" to avoid mismatch */\nfunction normalizeLineEndings(str) {\n  return (str || "").replace(/\\r\\n/g, "\\n");\n}\n\n/** Listen for model changes from Retool */\nwindow.Retool.subscribe((model) => {\n  if (!model || typeof model.code !== "string") return;\n  const newVal = normalizeLineEndings(model.code);\n  if (newVal !== mostRecentCode) {\n    mostRecentCode = newVal;\n    setCode(newVal);\n  }\n});\n\n/** Start up the editor */\ncreateEditor();\n</script>\n'
      }
      model="{code: {{ JSON.stringify(IntegrationRule_testrun.data.modifiedRecords, null, 4) }} }"
    />
  </View>
</Container>
