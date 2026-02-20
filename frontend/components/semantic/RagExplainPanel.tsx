"use client";

import { FormEvent, useState } from "react";

import {
  explainWithRag,
  RagResponse,
} from "@/lib/api";

type Props = {
  availablePatchVersions: string[];
};

function valueToText(value: unknown): string {
  if (value === null || value === undefined) {
    return "-";
  }
  if (typeof value === "string" || typeof value === "number" || typeof value === "boolean") {
    return String(value);
  }
  return JSON.stringify(value);
}

export default function RagExplainPanel({ availablePatchVersions }: Props) {
  const [query, setQuery] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<RagResponse | null>(null);

  const citedIndexes = new Set(
    (result?.citations ?? [])
      .map((citation) => citation.index)
      .filter((index): index is number => typeof index === "number" && Number.isFinite(index)),
  );
  const citedRetrievedItems =
    result?.retrieved_items?.filter((_item, index) => citedIndexes.has(index)) ?? [];

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!query.trim()) {
      setError("Please enter a question for AI explain.");
      return;
    }

    setLoading(true);
    setError(null);
    try {
      const response = await explainWithRag({ query: query.trim() });
      setResult(response);
    } catch (ragError) {
      const message = ragError instanceof Error ? ragError.message : "RAG explain failed unexpectedly.";
      setError(message);
      setResult(null);
    } finally {
      setLoading(false);
    }
  }

  return (
    <section className="rounded-md border p-4 space-y-3">
      <h2 className="text-lg font-semibold">AI Search + Explain (RAG)</h2>
      <p className="text-sm text-zinc-600">
        Ask naturally. The AI infers patch scope, direction, category, and entity context from your question.
      </p>

      <form onSubmit={onSubmit} className="grid grid-cols-1 gap-3">
        <label className="flex flex-col gap-1 text-sm">
          Question
          <input
            className="rounded border px-2 py-1"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder='e.g. "For this patch, which jungle champs gained the most?"'
          />
        </label>

        <div>
          <button
            type="submit"
            className="rounded bg-zinc-900 px-4 py-2 text-white hover:bg-zinc-700 disabled:opacity-50"
            disabled={loading}
          >
            {loading ? "Generating..." : "Generate AI Explain"}
          </button>
        </div>
      </form>

      {error ? <p className="text-sm text-red-600">{error}</p> : null}

      {result ? (
        <div className="space-y-3 rounded border p-3">
          <div>
            <h3 className="font-semibold">Explanation</h3>
            <p className="text-sm">{result.explanation || "No explanation returned."}</p>
          </div>

          <div>
            <h3 className="font-semibold">Impact Summary</h3>
            {result.impact_summary.length ? (
              <ul className="list-disc pl-5 text-sm">
                {result.impact_summary.map((line, index) => (
                  <li key={`summary-${index}`}>{line}</li>
                ))}
              </ul>
            ) : (
              <p className="text-sm text-zinc-600">No summary lines returned.</p>
            )}
          </div>

          <div>
            <h3 className="font-semibold">Reasoning</h3>
            {result.reasoning.length ? (
              <ul className="list-disc pl-5 text-sm">
                {result.reasoning.map((line, index) => (
                  <li key={`reasoning-${index}`}>{line}</li>
                ))}
              </ul>
            ) : (
              <p className="text-sm text-zinc-600">No reasoning lines returned.</p>
            )}
          </div>

          <div>
            <h3 className="font-semibold">Citations</h3>
            {citedRetrievedItems.length ? (
              <div className="space-y-2">
                {citedRetrievedItems.map((item, index) => (
                  <div
                    key={`${item.patch_version}-${item.entity}-${item.stat_name}-${index}`}
                    className="rounded border p-3"
                  >
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="text-xs text-zinc-600">
                        #{result.retrieved_items?.findIndex(
                          (candidate) =>
                            candidate.patch_version === item.patch_version &&
                            candidate.entity === item.entity &&
                            candidate.stat_name === item.stat_name &&
                            candidate.direction === item.direction,
                        ) ?? "?"}
                      </span>
                      <span className="font-medium">{item.entity}</span>
                      <span className="text-xs text-zinc-600">{item.entity_type}</span>
                      <span className="text-xs text-zinc-600">Patch {item.patch_version}</span>
                      <span className="text-xs text-zinc-600">score {item.score.toFixed(4)}</span>
                    </div>
                    <p className="text-sm">
                      {item.direction} {item.category} - {item.stat_name}
                    </p>
                    <p className="text-xs text-zinc-600">
                      old: {valueToText(item.old_value)} | new: {valueToText(item.new_value)} | delta:{" "}
                      {item.delta_value ?? "-"}
                    </p>
                    <p className="text-xs text-zinc-600">
                      tags: {item.tags.length ? item.tags.join(", ") : "-"}
                    </p>
                  </div>
                ))}
              </div>
            ) : result.citations.length ? (
              <ul className="text-sm">
                {result.citations.map((citation, index) => (
                  <li key={`citation-${index}`}>
                    #{citation.index ?? "?"} {citation.entity ?? "Unknown"} ({citation.patch_version ?? "N/A"})
                  </li>
                ))}
              </ul>
            ) : result.retrieved_items?.length ? (
              <p className="text-sm text-zinc-600">
                No explicit citation indices were returned, so no evidence items are shown.
              </p>
            ) : (
              <p className="text-sm text-zinc-600">No citations returned.</p>
            )}
          </div>
        </div>
      ) : null}
    </section>
  );
}
