import * as React from "react"
import { format } from "date-fns"
import { Calendar as CalendarIcon } from "lucide-react"
import { cn } from "@/lib/utils"
import { Button } from "./button"
import { Input } from "./input"
import { Label } from "./label"

interface DatePickerProps {
  label?: string
  value?: Date | string | null
  onChange: (date: Date | null) => void
  minDate?: Date
  maxDate?: Date
  required?: boolean
  error?: string
  className?: string
}

export function DatePicker({
  label,
  value,
  onChange,
  minDate,
  maxDate,
  required,
  error,
  className,
}: DatePickerProps) {
  const dateValue = value
    ? typeof value === "string"
      ? new Date(value)
      : value
    : null

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const dateString = e.target.value
    if (dateString) {
      const date = new Date(dateString)
      if (!isNaN(date.getTime())) {
        onChange(date)
      }
    } else {
      onChange(null)
    }
  }

  const inputValue = dateValue ? format(dateValue, "yyyy-MM-dd") : ""

  return (
    <div className={cn("space-y-2", className)}>
      {label && (
        <Label>
          {label}
          {required && <span className="text-destructive ml-1">*</span>}
        </Label>
      )}
      <div className="relative">
        <Input
          type="date"
          value={inputValue}
          onChange={handleChange}
          min={minDate ? format(minDate, "yyyy-MM-dd") : undefined}
          max={maxDate ? format(maxDate, "yyyy-MM-dd") : undefined}
          className={cn(error && "border-destructive")}
        />
        <CalendarIcon className="absolute right-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground pointer-events-none" />
      </div>
      {error && <p className="text-sm text-destructive">{error}</p>}
    </div>
  )
}

interface DateRangePickerProps {
  label?: string
  value?: { start: Date | null; end: Date | null }
  onChange: (range: { start: Date | null; end: Date | null }) => void
  presets?: Array<{ label: string; range: { start: Date; end: Date } }>
  className?: string
}

export function DateRangePicker({
  label,
  value = { start: null, end: null },
  onChange,
  presets,
  className,
}: DateRangePickerProps) {
  const handleStartChange = (date: Date | null) => {
    onChange({ ...value, start: date })
  }

  const handleEndChange = (date: Date | null) => {
    onChange({ ...value, end: date })
  }

  return (
    <div className={cn("space-y-2", className)}>
      {label && <Label>{label}</Label>}
      {presets && presets.length > 0 && (
        <div className="flex gap-2 flex-wrap">
          {presets.map((preset, index) => (
            <Button
              key={index}
              variant="outline"
              size="sm"
              onClick={() => onChange({ start: preset.range.start, end: preset.range.end })}
            >
              {preset.label}
            </Button>
          ))}
        </div>
      )}
      <div className="flex gap-2">
        <DatePicker
          value={value.start}
          onChange={handleStartChange}
          maxDate={value.end || undefined}
        />
        <DatePicker
          value={value.end}
          onChange={handleEndChange}
          minDate={value.start || undefined}
        />
      </div>
    </div>
  )
}

