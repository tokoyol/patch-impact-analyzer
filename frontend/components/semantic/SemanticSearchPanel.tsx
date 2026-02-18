"use client";

import { FormEvent, useState } from "react";

import {
  PatchChangeCategory,
  PatchChangeDirection,
  semanticSearch,
  SemanticSearchItem,
  SemanticSearchQuery,
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

function valueToText(value: unknown): string {
  if (value === null || value === undefined) {
    return "-";
  }
  if (typeof value === "string" || typeof value === "number" || typeof value === "boolean") {
    return String(value);
  }
  return JSON.stringify(value);
}

export default function SemanticSearchPanel({ availablePatchVersions }: Props) {
  const [query, setQuery] = useState("");
  const [patchVersion, setPatchVersion] = useState("");
  const [direction, setDirection] = useState("");
  const [category, setCategory] = useState("");
  const [tag, setTag] = useState("");
  const [entity, setEntity] = useState("");
  const [k, setK] = useState(10);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [items, setItems] = useState<SemanticSearchItem[]>([]);

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!query.trim()) {
      setError("Please enter a semantic query.");
      return;
    }

    const payload: SemanticSearchQuery = {
      query: query.trim(),
      k,
      patch_version: patchVersion || undefined,
      direction: (direction || undefined) as PatchChangeDirection | undefined,
      category: (category || undefined) as PatchChangeCategory | undefined,
      tag: tag.trim() || undefined,
      entity: entity.trim() || undefined,
    };

    setLoading(true);
    setError(null);
    try {
      const response = await semanticSearch(payload);
      setItems(response.items);
    } catch (searchError) {
      const message =
        searchError instanceof Error
          ? searchError.message
          : "Semantic search failed unexpectedly.";
      setError(message);
      setItems([]);
    } finally {
      setLoading(false);
    }
  }

  return (
    <section className="rounded-md border p-4 space-y-3">
      <h2 className="text-lg font-semibold">Semantic Search</h2>
      <p className="text-sm text-zinc-600">
        Ask natural language questions like “Who got stronger early game?”.
      </p>

      <form onSubmit={onSubmit} className="grid grid-cols-1 gap-3 md:grid-cols-2">
        <label className="flex flex-col gap-1 text-sm md:col-span-2">
          Query
          <input
            className="rounded border px-2 py-1"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="e.g. What buffs increase jungle tempo?"
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
              <option key={version} value={version}>
                {version}
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
              <option key={option} value={option}>
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
              <option key={option} value={option}>
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
            max={50}
            value={k}
            onChange={(event) => setK(Math.max(1, Math.min(50, Number(event.target.value) || 10)))}
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
          Entity
          <input
            className="rounded border px-2 py-1"
            value={entity}
            onChange={(event) => setEntity(event.target.value)}
            placeholder="e.g. Nunu, Dusk and Dawn, Phase Rush"
          />
        </label>

        <div className="md:col-span-2">
          <button
            type="submit"
            className="rounded bg-zinc-900 px-4 py-2 text-white hover:bg-zinc-700 disabled:opacity-50"
            disabled={loading}
          >
            {loading ? "Searching..." : "Run Semantic Search"}
          </button>
        </div>
      </form>

      {error ? <p className="text-sm text-red-600">{error}</p> : null}

      <div className="space-y-2">
        {items.map((item, index) => (
          <div key={`${item.patch_version}-${item.entity}-${item.stat_name}-${index}`} className="rounded border p-3">
            <div className="flex flex-wrap items-center gap-2">
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
    </section>
  );
}
