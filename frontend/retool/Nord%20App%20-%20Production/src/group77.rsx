<Container
  id="group77"
  _direction="vertical"
  _gap="0px"
  _type="stack"
  footerPadding="4px 12px"
  headerPadding="4px 12px"
  margin="0"
  padding="0"
  showBody={true}
  showBorder={false}
  style={{ map: { background: "rgba(255, 255, 255, 0)" } }}
>
  <View id="00030" viewKey="View 1">
    <Text
      id="text48"
      heightType="fixed"
      value="**Bank Filter**"
      verticalAlign="bottom"
    />
    <Filter id="filterBank" linkedTableId="tableBank3" linkToTable={true} />
    <JSONEditor
      id="bankFiltersInput"
      formDataKey="bank_filters"
      hidden="true"
      label="Bank filters"
      required={false}
      value="{{ filterBank.value }}"
    />
    <Text
      id="text45"
      heightType="fixed"
      value="**Book Filter**"
      verticalAlign="bottom"
    />
    <Filter id="filterBook" linkedTableId="tableBook3" linkToTable={true} />
    <JSONEditor
      id="bookFiltersInput"
      formDataKey="book_filters"
      hidden="true"
      label="Book filters"
      required={false}
      value="{{ filterBook.value }}"
    />
    <Switch id="switch4" label="copy filters from Bank Table">
      <Event
        event="change"
        method="run"
        params={{
          map: {
            src: '(async () => {\n  try {\n    console.log("[CopyFilters] start (property mode)");\n    const src = tableBank.filterStack ?? null;\n    console.log("[CopyFilters] tableBanok.filterStack =", src);\n\n    // Normalize: accept {filters, operator} or an array\n    const raw = Array.isArray(src) ? src : (Array.isArray(src?.filters) ? src.filters : []);\n    const operator = (src && src.operator) ? src.operator : "and";\n\n    const norm = {\n      operator,\n      filters: raw.map((f, i) => ({\n        id: f?.id ?? `copied-${i}-${Date.now()}`,\n        columnId: f?.columnId ?? f?.key ?? f?.column ?? "",\n        operator: f?.operator || "includes",\n        value: f?.value,\n        disabled: !!f?.disabled\n      }))\n    };\n\n    console.log("[CopyFilters] normalized =", norm);\n\n    if (typeof filterBank.setFilterStack === "function") {\n      console.log("[CopyFilters] applying via filterBook.setFilterStack(norm)");\n      await filterBank.setFilterStack(norm);\n    } else if (typeof filterBank.setValue === "function") {\n      console.log("[CopyFilters] applying via filterBook.setValue(norm)");\n      await filterBank.setValue(norm);\n    } else {\n      console.warn("[CopyFilters] Target filter component has no setFilterStack/setValue", filterBank);\n      utils.showNotification({\n        title: "Cannot paste filters",\n        description: "Target filter component is not settable.",\n        intent: "warning"\n      });\n      return;\n    }\n\n    console.log("[CopyFilters] done; count =", norm.filters.length);\n    utils.showNotification({\n      title: "Filters copied",\n      description: `${norm.filters.length} filter(s) pasted.`,\n      intent: norm.filters.length ? "success" : "info"\n    });\n  } catch (err) {\n    console.error("[CopyFilters] error:", err);\n    utils.showNotification({\n      title: "Copy failed",\n      description: String(err?.message || err),\n      intent: "danger"\n    });\n  }\n})()',
          },
        }}
        pluginId=""
        type="script"
        waitMs="0"
        waitType="debounce"
      />
    </Switch>
    <Switch id="switch5" label="copy filters from Book Table">
      <Event
        event="change"
        method="run"
        params={{
          map: {
            src: '(async () => {\n  try {\n    console.log("[CopyFilters] start (property mode)");\n    const src = tableBook.filterStack ?? null;\n    console.log("[CopyFilters] tableBook.filterStack =", src);\n\n    // Normalize: accept {filters, operator} or an array\n    const raw = Array.isArray(src) ? src : (Array.isArray(src?.filters) ? src.filters : []);\n    const operator = (src && src.operator) ? src.operator : "and";\n\n    const norm = {\n      operator,\n      filters: raw.map((f, i) => ({\n        id: f?.id ?? `copied-${i}-${Date.now()}`,\n        columnId: f?.columnId ?? f?.key ?? f?.column ?? "",\n        operator: f?.operator || "includes",\n        value: f?.value,\n        disabled: !!f?.disabled\n      }))\n    };\n\n    console.log("[CopyFilters] normalized =", norm);\n\n    if (typeof filterBook.setFilterStack === "function") {\n      console.log("[CopyFilters] applying via filterBook.setFilterStack(norm)");\n      await filterBook.setFilterStack(norm);\n    } else if (typeof filterBook.setValue === "function") {\n      console.log("[CopyFilters] applying via filterBook.setValue(norm)");\n      await filterBook.setValue(norm);\n    } else {\n      console.warn("[CopyFilters] Target filter component has no setFilterStack/setValue", filterBook);\n      utils.showNotification({\n        title: "Cannot paste filters",\n        description: "Target filter component is not settable.",\n        intent: "warning"\n      });\n      return;\n    }\n\n    console.log("[CopyFilters] done; count =", norm.filters.length);\n    utils.showNotification({\n      title: "Filters copied",\n      description: `${norm.filters.length} filter(s) pasted.`,\n      intent: norm.filters.length ? "success" : "info"\n    });\n  } catch (err) {\n    console.error("[CopyFilters] error:", err);\n    utils.showNotification({\n      title: "Copy failed",\n      description: String(err?.message || err),\n      intent: "danger"\n    });\n  }\n})()',
          },
        }}
        pluginId=""
        type="script"
        waitMs="0"
        waitType="debounce"
      />
    </Switch>
  </View>
</Container>
