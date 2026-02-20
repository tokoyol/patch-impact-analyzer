"use client";

import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

type DistributionItem = {
  champion: string;
  value: number;
  buffs: number;
  nerfs: number;
};

type PatchImpactDistributionProps = {
  data: DistributionItem[];
};

export default function PatchImpactDistribution({
  data,
}: PatchImpactDistributionProps) {
  if (!data.length) {
    return <p>No champion impact data available for this patch.</p>;
  }

  return (
    <div className="h-72 w-full">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={data}>
          <CartesianGrid strokeDasharray="3 3" stroke="var(--chart-grid)" />
          <XAxis dataKey="champion" stroke="var(--chart-axis)" tick={{ fill: "var(--chart-axis)" }} />
          <YAxis stroke="var(--chart-axis)" tick={{ fill: "var(--chart-axis)" }} />
          <Tooltip
            cursor={{ fill: "rgba(100, 116, 139, 0.12)" }}
            contentStyle={{
              backgroundColor: "var(--chart-tooltip-bg)",
              borderColor: "var(--chart-tooltip-border)",
              color: "var(--chart-tooltip-text)",
            }}
            labelStyle={{ color: "var(--chart-tooltip-text)" }}
            itemStyle={{ color: "var(--chart-tooltip-text)" }}
          />
          <Bar dataKey="value" fill="var(--chart-bar)" />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

