"use client";

/**
 * A small set of single-series charts (one hue, recessive grid, hover tooltips, tabular fallback via <details>).
 * Identity is never color-alone: each chart's title names its single series.
 */
import { Bar, BarChart, CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { Empty } from "./ui";

const axis = { stroke: "var(--ink-3)", fontSize: 11, tickLine: false, axisLine: false } as const;
const tip = {
  contentStyle: { background: "var(--card-solid)", border: "1px solid var(--border)", borderRadius: 8, fontSize: 12, color: "var(--ink)" },
  labelStyle: { color: "var(--ink-2)" },
  cursor: { stroke: "var(--ink-3)", strokeWidth: 1 },
};

function DataTable({ rows, x, y }: { rows: Record<string, unknown>[]; x: string; y: string }) {
  return (
    <details className="mt-2 text-xs muted">
      <summary className="cursor-pointer">View as table</summary>
      <table className="mt-2 w-full">
        <tbody>
          {rows.map((r, i) => (
            <tr key={i}><td className="py-0.5 pr-4">{String(r[x])}</td><td className="tabular-nums">{String(r[y])}</td></tr>
          ))}
        </tbody>
      </table>
    </details>
  );
}

export function TrendChart({ data, x, y, height = 220, yMax = 100 }:
  { data: Record<string, unknown>[]; x: string; y: string; height?: number; yMax?: number }) {
  if (!data.length) return <Empty title="No completed interviews yet" />;
  return (
    <div>
      <ResponsiveContainer width="100%" height={height}>
        <LineChart data={data} margin={{ top: 8, right: 12, left: -16, bottom: 0 }}>
          <CartesianGrid stroke="var(--grid)" vertical={false} />
          <XAxis dataKey={x} {...axis} minTickGap={24} />
          <YAxis domain={[0, yMax]} {...axis} />
          <Tooltip {...tip} />
          <Line type="monotone" dataKey={y} stroke="var(--series-1)" strokeWidth={2} dot={{ r: 4, strokeWidth: 2, fill: "var(--card-solid)" }}
            activeDot={{ r: 5 }} isAnimationActive={false} />
        </LineChart>
      </ResponsiveContainer>
      <DataTable rows={data} x={x} y={y} />
    </div>
  );
}

export function BarsChart({ data, x, y, height = 220, yMax = 100 }:
  { data: Record<string, unknown>[]; x: string; y: string; height?: number; yMax?: number }) {
  if (!data.length) return <Empty title="No data yet" />;
  return (
    <div>
      <ResponsiveContainer width="100%" height={height}>
        <BarChart data={data} layout="vertical" margin={{ top: 4, right: 16, left: 8, bottom: 0 }} barCategoryGap={6}>
          <CartesianGrid stroke="var(--grid)" horizontal={false} />
          <XAxis type="number" domain={[0, yMax]} {...axis} />
          <YAxis type="category" dataKey={x} {...axis} width={140} />
          <Tooltip {...tip} cursor={{ fill: "var(--grid)" }} />
          <Bar dataKey={y} fill="var(--series-1)" radius={[0, 4, 4, 0]} maxBarSize={18} isAnimationActive={false} />
        </BarChart>
      </ResponsiveContainer>
      <DataTable rows={data} x={x} y={y} />
    </div>
  );
}

export function DifficultyChart({ data }: { data: { sequence: number; difficulty: string; score: number }[] }) {
  const lvl: Record<string, number> = { easy: 1, medium: 2, hard: 3 };
  const rows = data.map((d) => ({ question: `Q${d.sequence}`, level: lvl[d.difficulty] ?? 2, score: d.score, difficulty: d.difficulty }));
  if (!rows.length) return <Empty title="No answers yet" />;
  return (
    <div>
      <ResponsiveContainer width="100%" height={180}>
        <LineChart data={rows} margin={{ top: 8, right: 12, left: -16, bottom: 0 }}>
          <CartesianGrid stroke="var(--grid)" vertical={false} />
          <XAxis dataKey="question" {...axis} />
          <YAxis domain={[0.5, 3.5]} ticks={[1, 2, 3]} tickFormatter={(v) => ["", "Easy", "Medium", "Hard"][v] ?? ""} {...axis} />
          <Tooltip {...tip} formatter={(_v, _n, p) => [`${p.payload.difficulty} · score ${p.payload.score}`, "Difficulty"]} />
          <Line type="stepAfter" dataKey="level" stroke="var(--series-1)" strokeWidth={2} dot={{ r: 4 }} isAnimationActive={false} />
        </LineChart>
      </ResponsiveContainer>
      <DataTable rows={rows} x="question" y="difficulty" />
    </div>
  );
}
