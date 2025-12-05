<Container
  id="group88"
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
      id="text61"
      heightType="fixed"
      value="**Bank Filter**"
      verticalAlign="bottom"
    />
    <Filter id="filterBank2" linkedTableId="tableBank3" linkToTable={true} />
    <JSONEditor
      id="bankFiltersInput2"
      formDataKey="bank_filters"
      hidden="true"
      label="Bank filters"
      required={false}
      value="{{ filterBank2.value }}"
    />
    <Text
      id="text60"
      heightType="fixed"
      value="**Book Filter**"
      verticalAlign="bottom"
    />
    <Filter id="filterBook2" linkedTableId="tableBook3" linkToTable={true} />
    <JSONEditor
      id="bookFiltersInput2"
      formDataKey="book_filters"
      hidden="true"
      label="Book filters"
      required={false}
      value="{{ filterBook2.value }}"
    />
    <Switch id="switch6" label="copy filters from Bank Table">
      <Event
        event="change"
        method="run"
        params={{
          map: {
            src: '(async () => {\n  try {\n    console.log("[CopyFilters] start (property mode)");\n    const src = tableBank.filterStack ?? null;\n    console.log("[CopyFilters] tableBanok.filterStack =", src);\n\n    // Normalize: accept {filters, operator} or an array\n    const raw = Array.isArray(src) ? src : (Array.isArray(src?.filters) ? src.filters : []);\n    const operator = (src && src.operator) ? src.operator : "and";\n\n    const norm = {\n      operator,\n      filters: raw.map((f, i) => ({\n        id: f?.id ?? `copied-${i}-${Date.now()}`,\n        columnId: f?.columnId ?? f?.key ?? f?.column ?? "",\n        operator: f?.operator || "includes",\n        value: f?.value,\n        disabled: !!f?.disabled\n      }))\n    };\n\n    console.log("[CopyFilters] normalized =", norm);\n\n    if (typeof filterBank2.setFilterStack === "function") {\n      console.log("[CopyFilters] applying via filterBook.setFilterStack(norm)");\n      await filterBank2.setFilterStack(norm);\n    } else if (typeof filterBank2.setValue === "function") {\n      console.log("[CopyFilters] applying via filterBook.setValue(norm)");\n      await filterBank2.setValue(norm);\n    } else {\n      console.warn("[CopyFilters] Target filter component has no setFilterStack/setValue", filterBank2);\n      utils.showNotification({\n        title: "Cannot paste filters",\n        description: "Target filter component is not settable.",\n        intent: "warning"\n      });\n      return;\n    }\n\n    console.log("[CopyFilters] done; count =", norm.filters.length);\n    utils.showNotification({\n      title: "Filters copied",\n      description: `${norm.filters.length} filter(s) pasted.`,\n      intent: norm.filters.length ? "success" : "info"\n    });\n  } catch (err) {\n    console.error("[CopyFilters] error:", err);\n    utils.showNotification({\n      title: "Copy failed",\n      description: String(err?.message || err),\n      intent: "danger"\n    });\n  }\n})()',
          },
        }}
        pluginId=""
        type="script"
        waitMs="0"
        waitType="debounce"
      />
    </Switch>
    <Switch id="switch7" label="copy filters from Book Table">
      <Event
        event="change"
        method="run"
        params={{
          map: {
            src: '(async () => {\n  try {\n    console.log("[CopyFilters] start (property mode)");\n    const src = tableBook.filterStack ?? null;\n    console.log("[CopyFilters] tableBook.filterStack =", src);\n\n    // Normalize: accept {filters, operator} or an array\n    const raw = Array.isArray(src) ? src : (Array.isArray(src?.filters) ? src.filters : []);\n    const operator = (src && src.operator) ? src.operator : "and";\n\n    const norm = {\n      operator,\n      filters: raw.map((f, i) => ({\n        id: f?.id ?? `copied-${i}-${Date.now()}`,\n        columnId: f?.columnId ?? f?.key ?? f?.column ?? "",\n        operator: f?.operator || "includes",\n        value: f?.value,\n        disabled: !!f?.disabled\n      }))\n    };\n\n    console.log("[CopyFilters] normalized =", norm);\n\n    if (typeof filterBook2.setFilterStack === "function") {\n      console.log("[CopyFilters] applying via filterBook.setFilterStack(norm)");\n      await filterBook2.setFilterStack(norm);\n    } else if (typeof filterBook2.setValue === "function") {\n      console.log("[CopyFilters] applying via filterBook.setValue(norm)");\n      await filterBook2.setValue(norm);\n    } else {\n      console.warn("[CopyFilters] Target filter component has no setFilterStack/setValue", filterBook2);\n      utils.showNotification({\n        title: "Cannot paste filters",\n        description: "Target filter component is not settable.",\n        intent: "warning"\n      });\n      return;\n    }\n\n    console.log("[CopyFilters] done; count =", norm.filters.length);\n    utils.showNotification({\n      title: "Filters copied",\n      description: `${norm.filters.length} filter(s) pasted.`,\n      intent: norm.filters.length ? "success" : "info"\n    });\n  } catch (err) {\n    console.error("[CopyFilters] error:", err);\n    utils.showNotification({\n      title: "Copy failed",\n      description: String(err?.message || err),\n      intent: "danger"\n    });\n  }\n})()',
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
