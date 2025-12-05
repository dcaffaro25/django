import * as React from "react"
import { Check, ChevronsUpDown, X } from "lucide-react"
import { cn } from "@/lib/utils"
import { Button } from "./button"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "./select"
import { Badge } from "./badge"

interface MultiSelectOption {
  value: string | number
  label: string
}

interface MultiSelectProps {
  options: MultiSelectOption[]
  value: Array<string | number>
  onChange: (value: Array<string | number>) => void
  placeholder?: string
  className?: string
  maxSelected?: number
}

export function MultiSelect({
  options,
  value,
  onChange,
  placeholder = "Select items...",
  className,
  maxSelected,
}: MultiSelectProps) {
  const [open, setOpen] = React.useState(false)

  const handleUnselect = (item: string | number) => {
    onChange(value.filter((i) => i !== item))
  }

  const handleSelect = (item: string | number) => {
    if (maxSelected && value.length >= maxSelected) {
      return
    }
    if (!value.includes(item)) {
      onChange([...value, item])
    }
  }

  return (
    <div className={cn("space-y-2", className)}>
      <Select open={open} onOpenChange={setOpen}>
        <SelectTrigger
          className={cn(
            "min-h-10 h-auto w-full",
            value.length > 0 && "h-10"
          )}
        >
          <div className="flex flex-wrap gap-1">
            {value.length > 0 ? (
              value.map((item) => {
                const option = options.find((opt) => opt.value === item)
                return (
                  <Badge
                    key={item}
                    variant="secondary"
                    className="mr-1 mb-1"
                    onClick={(e) => {
                      e.preventDefault()
                      e.stopPropagation()
                      handleUnselect(item)
                    }}
                  >
                    {option?.label || item}
                    <button
                      className="ml-1 ring-offset-background rounded-full outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2"
                      onKeyDown={(e) => {
                        if (e.key === "Enter") {
                          handleUnselect(item)
                        }
                      }}
                      onMouseDown={(e) => {
                        e.preventDefault()
                        e.stopPropagation()
                      }}
                      onClick={(e) => {
                        e.preventDefault()
                        e.stopPropagation()
                        handleUnselect(item)
                      }}
                    >
                      <X className="h-3 w-3 text-muted-foreground hover:text-foreground" />
                    </button>
                  </Badge>
                )
              })
            ) : (
              <SelectValue placeholder={placeholder} />
            )}
          </div>
        </SelectTrigger>
        <SelectContent>
          {options.map((option) => (
            <SelectItem
              key={option.value}
              value={String(option.value)}
              onSelect={() => {
                handleSelect(option.value)
                setOpen(false)
              }}
            >
              <div className="flex items-center">
                {value.includes(option.value) && (
                  <Check className="mr-2 h-4 w-4" />
                )}
                {option.label}
              </div>
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </div>
  )
}

