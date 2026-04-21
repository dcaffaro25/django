import { LineChart, Line, ResponsiveContainer, Tooltip, YAxis } from "recharts"

/**
 * Inline sparkline — a thin per-row chart rendered when a line has more
 * than three concrete (non-variance) periods. Helpful for multi-month or
 * YTD templates where the trend matters more than individual values.
 */
export function LineSparkline({
  data,
  color = "hsl(var(--primary))",
}: {
  data: Array<{ label: string; value: number }>
  color?: string
}) {
  if (data.length < 2) return null
  return (
    <div className="h-6 w-24">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={data}>
          <YAxis hide domain={["auto", "auto"]} />
          <Tooltip
            contentStyle={{
              fontSize: 10,
              padding: "2px 6px",
              border: "1px solid hsl(var(--border))",
              borderRadius: 4,
            }}
            labelFormatter={(label) => String(label)}
            formatter={(val: number) =>
              val.toLocaleString("pt-BR", {
                minimumFractionDigits: 2,
                maximumFractionDigits: 2,
              })
            }
          />
          <Line
            type="monotone"
            dataKey="value"
            stroke={color}
            strokeWidth={1.5}
            dot={false}
            isAnimationActive={false}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  )
}
