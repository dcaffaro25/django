import * as React from "react"
import { X } from "lucide-react"
import { Button } from "./button"
import { Input } from "./input"
import { Label } from "./label"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "./select"
import { DateRangePicker } from "./date-picker"
import { MultiSelect } from "./multi-select"
import { Badge } from "./badge"
import { cn } from "@/lib/utils"

export type FilterType =
  | "text"
  | "select"
  | "multiselect"
  | "date"
  | "daterange"
  | "number"
  | "numberrange"

export interface FilterConfig {
  id: string
  type: FilterType
  label: string
  options?: Array<{ value: string | number; label: string }>
  placeholder?: string
}

interface FilterBarProps {
  filters: Record<string, unknown>
  onFilterChange: (filters: Record<string, unknown>) => void
  filterConfig: FilterConfig[]
  onClear?: () => void
  savedFilters?: Array<{ id: string; label: string; filters: Record<string, unknown> }>
  onSaveFilter?: (label: string, filters: Record<string, unknown>) => void
  className?: string
}

export function FilterBar({
  filters,
  onFilterChange,
  filterConfig,
  onClear,
  savedFilters,
  onSaveFilter,
  className,
}: FilterBarProps) {
  const updateFilter = (id: string, value: unknown) => {
    onFilterChange({ ...filters, [id]: value })
  }

  const removeFilter = (id: string) => {
    const newFilters = { ...filters }
    delete newFilters[id]
    onFilterChange(newFilters)
  }

  const activeFilters = filterConfig.filter((config) => {
    const value = filters[config.id]
    return value !== undefined && value !== null && value !== "" && 
           (!Array.isArray(value) || value.length > 0)
  })

  return (
    <div className={cn("space-y-4", className)}>
      <div className="flex flex-wrap gap-4">
        {filterConfig.map((config) => {
          const value = filters[config.id]
          
          switch (config.type) {
            case "text":
              return (
                <div key={config.id} className="flex-1 min-w-[200px]">
                  <Label>{config.label}</Label>
                  <Input
                    value={(value as string) || ""}
                    onChange={(e) => updateFilter(config.id, e.target.value)}
                    placeholder={config.placeholder}
                  />
                </div>
              )
            
            case "select":
              return (
                <div key={config.id} className="flex-1 min-w-[200px]">
                  <Label>{config.label}</Label>
                  <Select
                    value={value ? String(value) : undefined}
                    onValueChange={(val) => updateFilter(config.id, val)}
                  >
                    <SelectTrigger>
                      <SelectValue placeholder={config.placeholder || "Select..."} />
                    </SelectTrigger>
                    <SelectContent>
                      {config.options?.map((option) => (
                        <SelectItem key={option.value} value={String(option.value)}>
                          {option.label}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
              )
            
            case "multiselect":
              return (
                <div key={config.id} className="flex-1 min-w-[200px]">
                  <Label>{config.label}</Label>
                  <MultiSelect
                    options={config.options || []}
                    value={(value as Array<string | number>) || []}
                    onChange={(val) => updateFilter(config.id, val)}
                    placeholder={config.placeholder}
                  />
                </div>
              )
            
            case "daterange":
              return (
                <div key={config.id} className="flex-1 min-w-[300px]">
                  <DateRangePicker
                    label={config.label}
                    value={
                      value
                        ? {
                            start: value.start ? new Date(value.start as string) : null,
                            end: value.end ? new Date(value.end as string) : null,
                          }
                        : { start: null, end: null }
                    }
                    onChange={(range) =>
                      updateFilter(config.id, {
                        start: range.start?.toISOString().split("T")[0],
                        end: range.end?.toISOString().split("T")[0],
                      })
                    }
                  />
                </div>
              )
            
            case "number":
              return (
                <div key={config.id} className="flex-1 min-w-[150px]">
                  <Label>{config.label}</Label>
                  <Input
                    type="number"
                    value={(value as number) || ""}
                    onChange={(e) =>
                      updateFilter(config.id, e.target.value ? Number(e.target.value) : null)
                    }
                    placeholder={config.placeholder}
                  />
                </div>
              )
            
            default:
              return null
          }
        })}
      </div>

      {activeFilters.length > 0 && (
        <div className="flex items-center gap-2 flex-wrap">
          <span className="text-sm text-muted-foreground">Active filters:</span>
          {activeFilters.map((config) => {
            const value = filters[config.id]
            let displayValue: string

            if (Array.isArray(value)) {
              displayValue = value.length > 0 ? `${value.length} selected` : ""
            } else if (typeof value === "object" && value !== null) {
              const range = value as { start?: string; end?: string }
              displayValue = range.start && range.end
                ? `${range.start} to ${range.end}`
                : ""
            } else {
              displayValue = String(value)
            }

            return (
              <Badge
                key={config.id}
                variant="secondary"
                className="gap-1"
              >
                {config.label}: {displayValue}
                <button
                  onClick={() => removeFilter(config.id)}
                  className="ml-1 rounded-full hover:bg-muted"
                >
                  <X className="h-3 w-3" />
                </button>
              </Badge>
            )
          })}
          {onClear && (
            <Button variant="ghost" size="sm" onClick={onClear}>
              Clear all
            </Button>
          )}
        </div>
      )}
    </div>
  )
}

