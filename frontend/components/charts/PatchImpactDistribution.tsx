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
          <CartesianGrid strokeDasharray="3 3" />
          <XAxis dataKey="champion" />
          <YAxis />
          <Tooltip />
          <Bar dataKey="value" />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

