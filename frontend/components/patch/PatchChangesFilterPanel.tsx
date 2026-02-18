"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";

import {
  getPatchChanges,
  PatchChangeCategory,
  PatchChangeDirection,
  PatchChangeItem,
  PatchChangesQuery,
} from "@/lib/api";

type Props = {
  version: string;
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

function formatValue(value: unknown): string {
  if (value === null || value === undefined) {
    return "-";
  }
  if (typeof value === "string" || typeof value === "number" || typeof value === "boolean") {
    return String(value);
  }
  return JSON.stringify(value);
}

export default function PatchChangesFilterPanel({ version }: Props) {
  const [draft, setDraft] = useState<PatchChangesQuery>({});
  const [applied, setApplied] = useState<PatchChangesQuery>({});
  const [rows, setRows] = useState<PatchChangeItem[]>([]);
  const [count, setCount] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const hasActiveFilters = useMemo(
    () =>
      Boolean(applied.category || applied.direction || applied.tag || applied.entity || applied.ability),
    [applied],
  );

  useEffect(() => {
    let cancelled = false;

    async function run() {
      setLoading(true);
      setError(null);
      try {
        const response = await getPatchChanges(version, applied);
        if (cancelled) {
          return;
        }
        setRows(response.items);
        setCount(response.count);
      } catch (err) {
        if (cancelled) {
          return;
        }
        setError(err instanceof Error ? err.message : "Failed to load filtered changes.");
        setRows([]);
        setCount(0);
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    }

    run();
    return () => {
      cancelled = true;
    };
  }, [version, applied]);

  function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setApplied(draft);
  }

  function onReset() {
    const empty = {};
    setDraft(empty);
    setApplied(empty);
  }

  return (
    <section className="rounded-md border p-4">
      <h2 className="mb-3 text-lg font-semibold">Change Filters</h2>

      <form onSubmit={onSubmit} className="grid grid-cols-1 gap-3 md:grid-cols-2">
        <label className="flex flex-col gap-1 text-sm">
          Category
          <select
            className="rounded border px-2 py-1"
            value={draft.category ?? ""}
            onChange={(e) =>
              setDraft((prev) => ({
                ...prev,
                category: (e.target.value || undefined) as PatchChangeCategory | undefined,
              }))
            }
          >
            <option value="">All</option>
            {CATEGORY_OPTIONS.map((category) => (
              <option key={category} value={category}>
                {category}
              </option>
            ))}
          </select>
        </label>

        <label className="flex flex-col gap-1 text-sm">
          Direction
          <select
            className="rounded border px-2 py-1"
            value={draft.direction ?? ""}
            onChange={(e) =>
              setDraft((prev) => ({
                ...prev,
                direction: (e.target.value || undefined) as PatchChangeDirection | undefined,
              }))
            }
          >
            <option value="">All</option>
            {DIRECTION_OPTIONS.map((direction) => (
              <option key={direction} value={direction}>
                {direction}
              </option>
            ))}
          </select>
        </label>

        <label className="flex flex-col gap-1 text-sm">
          Tag
          <input
            className="rounded border px-2 py-1"
            value={draft.tag ?? ""}
            onChange={(e) => setDraft((prev) => ({ ...prev, tag: e.target.value || undefined }))}
            placeholder="e.g. jungle"
          />
        </label>

        <label className="flex flex-col gap-1 text-sm">
          Champion
          <input
            className="rounded border px-2 py-1"
            value={draft.entity ?? ""}
            onChange={(e) => setDraft((prev) => ({ ...prev, entity: e.target.value || undefined }))}
            placeholder="e.g. Elise"
          />
        </label>

        <label className="flex flex-col gap-1 text-sm md:col-span-2">
          Ability
          <input
            className="rounded border px-2 py-1"
            value={draft.ability ?? ""}
            onChange={(e) => setDraft((prev) => ({ ...prev, ability: e.target.value || undefined }))}
            placeholder="e.g. Q"
          />
        </label>

        <div className="flex gap-2 md:col-span-2">
          <button className="rounded bg-black px-3 py-1 text-sm text-white" type="submit">
            Apply Filters
          </button>
          <button className="rounded border px-3 py-1 text-sm" type="button" onClick={onReset}>
            Reset
          </button>
        </div>
      </form>

      <div className="mt-4 text-sm text-zinc-700">
        {loading ? "Loading changes..." : `${count} change(s)`}
        {hasActiveFilters ? " with filters applied" : ""}
      </div>

      {error ? <p className="mt-2 text-sm text-red-600">{error}</p> : null}

      <div className="mt-3 max-h-96 overflow-auto rounded border">
        <table className="w-full text-left text-sm">
          <thead className="bg-zinc-50">
            <tr>
              <th className="px-2 py-2">Champion</th>
              <th className="px-2 py-2">Ability</th>
              <th className="px-2 py-2">Stat</th>
              <th className="px-2 py-2">Direction</th>
              <th className="px-2 py-2">Old</th>
              <th className="px-2 py-2">New</th>
              <th className="px-2 py-2">Delta</th>
              <th className="px-2 py-2">Tags</th>
            </tr>
          </thead>
          <tbody>
            {rows.length === 0 && !loading ? (
              <tr>
                <td className="px-2 py-3 text-zinc-500" colSpan={8}>
                  No changes match the current filters.
                </td>
              </tr>
            ) : null}
            {rows.map((row, index) => (
              <tr key={`${row.entity}-${row.stat_name}-${index}`} className="border-t">
                <td className="px-2 py-2">{row.entity}</td>
                <td className="px-2 py-2">{row.ability_slot ?? "-"}</td>
                <td className="px-2 py-2">{row.stat_name}</td>
                <td className="px-2 py-2">{row.direction}</td>
                <td className="px-2 py-2">{formatValue(row.old_value)}</td>
                <td className="px-2 py-2">{formatValue(row.new_value)}</td>
                <td className="px-2 py-2">{row.delta_value ?? "-"}</td>
                <td className="px-2 py-2">{row.tags.length ? row.tags.join(", ") : "-"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

