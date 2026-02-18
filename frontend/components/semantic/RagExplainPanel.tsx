"use client";

import { FormEvent, useState } from "react";

import {
  explainWithRag,
  PatchChangeCategory,
  PatchChangeDirection,
  PatchEntityType,
  RagQuery,
  RagResponse,
} from "@/lib/api";

type Props = {
  availablePatchVersions: string[];
};

const CATEGORY_OPTIONS: PatchChangeCategory[] = [
  "damage",
  "cooldown",
  "base_stat",
  "scaling",
  "cost",
  "mechanic",
];
const DIRECTION_OPTIONS: PatchChangeDirection[] = ["buff", "nerf", "adjustment"];
const ENTITY_TYPE_OPTIONS: PatchEntityType[] = ["all", "champion", "item", "system"];

export default function RagExplainPanel({ availablePatchVersions }: Props) {
  const [query, setQuery] = useState("");
  const [patchVersion, setPatchVersion] = useState("");
  const [entityType, setEntityType] = useState<PatchEntityType>("all");
  const [direction, setDirection] = useState("");
  const [category, setCategory] = useState("");
  const [tag, setTag] = useState("");
  const [entity, setEntity] = useState("");
  const [k, setK] = useState(10);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<RagResponse | null>(null);

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!query.trim()) {
      setError("Please enter a question for AI explain.");
      return;
    }

    const payload: RagQuery = {
      query: query.trim(),
      k,
      patch_version: patchVersion || undefined,
      entity_type: entityType === "all" ? undefined : entityType,
      direction: (direction || undefined) as PatchChangeDirection | undefined,
      category: (category || undefined) as PatchChangeCategory | undefined,
      tag: tag.trim() || undefined,
      entity: entity.trim() || undefined,
    };

    setLoading(true);
    setError(null);
    try {
      const response = await explainWithRag(payload);
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
      <h2 className="text-lg font-semibold">AI Explain (RAG)</h2>
      <p className="text-sm text-zinc-600">
        Query then retrieve patch chunks, generate explanation, impact summary, and reasoning.
      </p>

      <form onSubmit={onSubmit} className="grid grid-cols-1 gap-3 md:grid-cols-2">
        <label className="flex flex-col gap-1 text-sm md:col-span-2">
          Question
          <input
            className="rounded border px-2 py-1"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="e.g. Explain likely meta impact of jungle tempo buffs."
          />
        </label>

        <label className="flex flex-col gap-1 text-sm">
          Patch Version
          <select
            className="rounded border px-2 py-1"
            value={patchVersion}
            onChange={(event) => setPatchVersion(event.target.value)}
          >
            <option value="">All</option>
            {availablePatchVersions.map((version) => (
              <option key={`rag-${version}`} value={version}>
                {version}
              </option>
            ))}
          </select>
        </label>

        <label className="flex flex-col gap-1 text-sm">
          Entity Type
          <select
            className="rounded border px-2 py-1"
            value={entityType}
            onChange={(event) => setEntityType(event.target.value as PatchEntityType)}
          >
            {ENTITY_TYPE_OPTIONS.map((option) => (
              <option key={`rag-entity-type-${option}`} value={option}>
                {option}
              </option>
            ))}
          </select>
        </label>

        <label className="flex flex-col gap-1 text-sm">
          Direction
          <select
            className="rounded border px-2 py-1"
            value={direction}
            onChange={(event) => setDirection(event.target.value)}
          >
            <option value="">All</option>
            {DIRECTION_OPTIONS.map((option) => (
              <option key={`rag-direction-${option}`} value={option}>
                {option}
              </option>
            ))}
          </select>
        </label>

        <label className="flex flex-col gap-1 text-sm">
          Category
          <select
            className="rounded border px-2 py-1"
            value={category}
            onChange={(event) => setCategory(event.target.value)}
          >
            <option value="">All</option>
            {CATEGORY_OPTIONS.map((option) => (
              <option key={`rag-category-${option}`} value={option}>
                {option}
              </option>
            ))}
          </select>
        </label>

        <label className="flex flex-col gap-1 text-sm">
          Top K
          <input
            className="rounded border px-2 py-1"
            type="number"
            min={1}
            max={30}
            value={k}
            onChange={(event) => setK(Math.max(1, Math.min(30, Number(event.target.value) || 10)))}
          />
        </label>

        <label className="flex flex-col gap-1 text-sm">
          Tag
          <input
            className="rounded border px-2 py-1"
            value={tag}
            onChange={(event) => setTag(event.target.value)}
            placeholder="e.g. jungle"
          />
        </label>

        <label className="flex flex-col gap-1 text-sm">
          Champion
          <input
            className="rounded border px-2 py-1"
            value={entity}
            onChange={(event) => setEntity(event.target.value)}
            placeholder="e.g. Taliyah"
          />
        </label>

        <div className="md:col-span-2">
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
            {result.citations.length ? (
              <ul className="text-sm">
                {result.citations.map((citation, index) => (
                  <li key={`citation-${index}`}>
                    #{citation.index ?? "?"} {citation.entity ?? "Unknown"} ({citation.patch_version ?? "N/A"})
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-sm text-zinc-600">No citations returned.</p>
            )}
          </div>
        </div>
      ) : null}
    </section>
  );
}
