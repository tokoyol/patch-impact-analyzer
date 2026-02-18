"use client";

import { useState } from "react";

import {
  getPatchSummaryReport,
  PatchSummaryReport,
  PatchSummaryVolatilityChange,
} from "@/lib/api";

type Props = {
  version: string;
};

function formatDelta(change: PatchSummaryVolatilityChange): string {
  if (change.delta_value === null || change.delta_value === undefined) {
    return "-";
  }
  return String(change.delta_value);
}

function buildPrintableHtml(summary: PatchSummaryReport): string {
  const topImpacted = summary.top_5_impacted_champions
    .map(
      (item) =>
        `<li><strong>${item.name}</strong> - Net impact: ${item.net_impact_score.toFixed(3)}</li>`,
    )
    .join("");

  const volatility = summary.highest_volatility_changes
    .map(
      (item) =>
        `<li><strong>${item.champion}</strong> - ${item.direction} ${item.stat_name} (impact ${item.impact_score.toFixed(3)}, delta ${formatDelta(item)})</li>`,
    )
    .join("");

  const watchList = summary.suggested_watch_list
    .map((item) => `<li><strong>${item.champion}</strong>: ${item.reason}</li>`)
    .join("");

  return `<!doctype html>
<html>
  <head>
    <meta charset="utf-8" />
    <title>Patch ${summary.version} Summary</title>
    <style>
      body { font-family: Arial, sans-serif; margin: 24px; color: #111; line-height: 1.4; }
      h1, h2 { margin: 0 0 10px 0; }
      section { margin-bottom: 18px; }
      ul { margin: 0; padding-left: 20px; }
      li { margin-bottom: 6px; }
      p { margin: 0; }
    </style>
  </head>
  <body>
    <h1>Patch ${summary.version} Summary Report</h1>
    <section>
      <h2>Top 5 Impacted Champions</h2>
      <ul>${topImpacted}</ul>
    </section>
    <section>
      <h2>Highest Volatility Changes</h2>
      <ul>${volatility}</ul>
    </section>
    <section>
      <h2>Risk Analysis</h2>
      <p>${summary.risk_analysis_paragraph}</p>
    </section>
    <section>
      <h2>Suggested Watch List</h2>
      <ul>${watchList}</ul>
    </section>
  </body>
</html>`;
}

export default function GeneratePatchSummaryPanel({ version }: Props) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [summary, setSummary] = useState<PatchSummaryReport | null>(null);

  async function onGenerateSummary() {
    setLoading(true);
    setError(null);
    try {
      const response = await getPatchSummaryReport(version);
      setSummary(response);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to generate summary.");
      setSummary(null);
    } finally {
      setLoading(false);
    }
  }

  function onExportPdf() {
    if (!summary) {
      return;
    }
    const popup = window.open("", "_blank", "noopener,noreferrer,width=960,height=700");
    if (!popup) {
      setError("Pop-up blocked. Please allow pop-ups to export as PDF.");
      return;
    }
    popup.document.open();
    popup.document.write(buildPrintableHtml(summary));
    popup.document.close();
    popup.focus();
    popup.print();
  }

  return (
    <section className="rounded-md border p-4 space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-lg font-semibold">Generate Patch Summary</h2>
        <div className="flex gap-2">
          <button
            type="button"
            className="rounded bg-zinc-900 px-3 py-1.5 text-sm text-white hover:bg-zinc-700 disabled:opacity-50"
            onClick={onGenerateSummary}
            disabled={loading}
          >
            {loading ? "Generating..." : "Generate Patch Summary"}
          </button>
          <button
            type="button"
            className="rounded border px-3 py-1.5 text-sm disabled:opacity-50"
            onClick={onExportPdf}
            disabled={!summary}
          >
            Export as PDF
          </button>
        </div>
      </div>

      {error ? <p className="text-sm text-red-600">{error}</p> : null}

      {summary ? (
        <div className="space-y-4">
          <section>
            <h3 className="font-semibold">Top 5 Impacted Champions</h3>
            <ul className="list-disc pl-5 text-sm">
              {summary.top_5_impacted_champions.map((item) => (
                <li key={item.name}>
                  {item.name}: {item.net_impact_score.toFixed(3)}
                </li>
              ))}
            </ul>
          </section>

          <section>
            <h3 className="font-semibold">Highest Volatility Changes</h3>
            <ul className="list-disc pl-5 text-sm">
              {summary.highest_volatility_changes.map((item, index) => (
                <li key={`${item.champion}-${item.stat_name}-${index}`}>
                  {item.champion} - {item.direction} {item.stat_name} (impact {item.impact_score.toFixed(3)}, delta{" "}
                  {formatDelta(item)})
                </li>
              ))}
            </ul>
          </section>

          <section>
            <h3 className="font-semibold">Risk Analysis</h3>
            <p className="text-sm">{summary.risk_analysis_paragraph}</p>
          </section>

          <section>
            <h3 className="font-semibold">Suggested Watch List</h3>
            <ul className="list-disc pl-5 text-sm">
              {summary.suggested_watch_list.map((item) => (
                <li key={item.champion}>
                  {item.champion}: {item.reason}
                </li>
              ))}
            </ul>
          </section>
        </div>
      ) : null}
    </section>
  );
}
