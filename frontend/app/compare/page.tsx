"use client";

import { useEffect, useMemo, useState } from "react";

import PatchImpactDistribution from "@/components/charts/PatchImpactDistribution";
import {
  getPatchComparisonIntelligence,
  getPatchDistribution,
  getPatchList,
  PatchComparisonIntelligence,
  PatchListItem,
} from "@/lib/api";

type CompareRow = {
  champion: string;
  aValue: number;
  bValue: number;
  delta: number;
};

export default function Page() {
  const [patches, setPatches] = useState<PatchListItem[]>([]);
  const [patchA, setPatchA] = useState("");
  const [patchB, setPatchB] = useState("");
  const [showTestPatches, setShowTestPatches] = useState(false);
  const [rows, setRows] = useState<CompareRow[]>([]);
  const [intelligence, setIntelligence] = useState<PatchComparisonIntelligence | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const visiblePatches = useMemo(
    () => patches.filter((patch) => showTestPatches || !patch.is_test),
    [patches, showTestPatches],
  );

  useEffect(() => {
    let active = true;
    async function loadPatches() {
      try {
        const data = await getPatchList();
        if (!active) {
          return;
        }
        setPatches(data.patches);
      } catch (loadError) {
        if (!active) {
          return;
        }
        const message =
          loadError instanceof Error
            ? loadError.message
            : "Unexpected error while loading patches.";
        setError(message);
      }
    }

    loadPatches();
    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    if (!visiblePatches.length) {
      setPatchA("");
      setPatchB("");
      return;
    }

    if (!visiblePatches.some((patch) => patch.version === patchA)) {
      setPatchA(visiblePatches[0].version);
    }

    if (!visiblePatches.some((patch) => patch.version === patchB)) {
      const fallbackB =
        visiblePatches.find((patch) => patch.version !== visiblePatches[0].version)?.version ??
        visiblePatches[0].version;
      setPatchB(fallbackB);
    }
  }, [visiblePatches, patchA, patchB]);

  useEffect(() => {
    let active = true;
    async function loadCompareData() {
      if (!patchA || !patchB) {
        setRows([]);
        setLoading(false);
        return;
      }

      setLoading(true);
      setError(null);
      try {
        const [aDistribution, bDistribution, compareIntelligence] = await Promise.all([
          getPatchDistribution(patchA),
          getPatchDistribution(patchB),
          getPatchComparisonIntelligence(patchA, patchB),
        ]);

        if (!active) {
          return;
        }

        const aMap = new Map(aDistribution.items.map((item) => [item.champion, item.value]));
        const bMap = new Map(bDistribution.items.map((item) => [item.champion, item.value]));
        const championSet = new Set<string>([...aMap.keys(), ...bMap.keys()]);

        const computedRows = Array.from(championSet)
          .map((champion) => {
            const aValue = aMap.get(champion) ?? 0;
            const bValue = bMap.get(champion) ?? 0;
            return {
              champion,
              aValue,
              bValue,
              delta: bValue - aValue,
            };
          })
          .sort((left, right) => Math.abs(right.delta) - Math.abs(left.delta));

        setRows(computedRows);
        setIntelligence(compareIntelligence);
      } catch (compareError) {
        if (!active) {
          return;
        }
        const message =
          compareError instanceof Error
            ? compareError.message
            : "Unexpected error while comparing patches.";
        setError(message);
        setRows([]);
        setIntelligence(null);
      } finally {
        if (active) {
          setLoading(false);
        }
      }
    }

    loadCompareData();
    return () => {
      active = false;
    };
  }, [patchA, patchB]);

  const chartData = useMemo(
    () =>
      rows.slice(0, 15).map((row) => ({
        champion: row.champion,
        value: row.delta,
        buffs: 0,
        nerfs: 0,
      })),
    [rows],
  );

  return (
    <main className="mx-auto max-w-6xl space-y-4 p-6">
      <h1 className="text-2xl font-bold">Patch Compare</h1>
      <p className="text-sm text-zinc-600">
        Compare champion net impact between two patches ({`Patch B - Patch A`}).
      </p>

      <section className="rounded-md border p-4 space-y-3">
        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={showTestPatches}
            onChange={(event) => setShowTestPatches(event.target.checked)}
          />
          Show test patches
        </label>

        <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
          <label className="flex flex-col gap-1 text-sm">
            Patch A
            <select
              className="rounded border px-2 py-1"
              value={patchA}
              onChange={(event) => setPatchA(event.target.value)}
              disabled={!visiblePatches.length}
            >
              {visiblePatches.map((patch) => (
                <option key={`a-${patch.version}`} value={patch.version}>
                  {patch.version}
                </option>
              ))}
            </select>
          </label>

          <label className="flex flex-col gap-1 text-sm">
            Patch B
            <select
              className="rounded border px-2 py-1"
              value={patchB}
              onChange={(event) => setPatchB(event.target.value)}
              disabled={!visiblePatches.length}
            >
              {visiblePatches.map((patch) => (
                <option key={`b-${patch.version}`} value={patch.version}>
                  {patch.version}
                </option>
              ))}
            </select>
          </label>
        </div>
      </section>

      {loading ? <p>Loading comparison...</p> : null}
      {error ? <p className="text-red-600">Could not compare patches. {error}</p> : null}

      {!loading && !error ? (
        <>
          {intelligence ? (
            <section className="rounded-md border p-4">
              <h2 className="mb-3 text-lg font-semibold">Patch Comparison Intelligence</h2>
              <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
                <div className="rounded border p-3">
                  <p className="text-xs text-zinc-600">Net Buff Count (B - A)</p>
                  <p
                    className={`text-xl font-semibold ${intelligence.delta.net_buff_count > 0 ? "text-green-700" : intelligence.delta.net_buff_count < 0 ? "text-red-700" : ""}`}
                  >
                    {intelligence.delta.net_buff_count}
                  </p>
                </div>
                <div className="rounded border p-3">
                  <p className="text-xs text-zinc-600">Net Nerf Count (B - A)</p>
                  <p
                    className={`text-xl font-semibold ${intelligence.delta.net_nerf_count > 0 ? "text-red-700" : intelligence.delta.net_nerf_count < 0 ? "text-green-700" : ""}`}
                  >
                    {intelligence.delta.net_nerf_count}
                  </p>
                </div>
                <div className="rounded border p-3">
                  <p className="text-xs text-zinc-600">Risk Score Delta (B - A)</p>
                  <p
                    className={`text-xl font-semibold ${intelligence.delta.risk_score_delta > 0 ? "text-red-700" : intelligence.delta.risk_score_delta < 0 ? "text-green-700" : ""}`}
                  >
                    {intelligence.delta.risk_score_delta.toFixed(3)}
                  </p>
                </div>
              </div>

              <div className="mt-4">
                <h3 className="mb-2 font-semibold">Role Distribution Changes</h3>
                <div className="max-h-64 overflow-auto rounded border">
                  <table className="w-full text-left text-sm">
                    <thead className="bg-zinc-50">
                      <tr>
                        <th className="px-2 py-2">Role</th>
                        <th className="px-2 py-2">Delta Total</th>
                        <th className="px-2 py-2">Delta Buffs</th>
                        <th className="px-2 py-2">Delta Nerfs</th>
                        <th className="px-2 py-2">Delta Adjustments</th>
                      </tr>
                    </thead>
                    <tbody>
                      {Object.entries(intelligence.delta.role_distribution_changes).map(([role, delta]) => (
                        <tr key={role} className="border-t">
                          <td className="px-2 py-2">{role}</td>
                          <td className="px-2 py-2">{delta.delta_total_changes}</td>
                          <td className="px-2 py-2">{delta.delta_buffs}</td>
                          <td className="px-2 py-2">{delta.delta_nerfs}</td>
                          <td className="px-2 py-2">{delta.delta_adjustments}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            </section>
          ) : null}

          <section className="rounded-md border p-4">
            <h2 className="mb-2 text-lg font-semibold">Top Delta (Patch B - Patch A)</h2>
            <PatchImpactDistribution data={chartData} />
          </section>

          <section className="rounded-md border p-4">
            <h2 className="mb-2 text-lg font-semibold">Champion Impact Delta Table</h2>
            <div className="max-h-[28rem] overflow-auto">
              <table className="w-full text-left text-sm">
                <thead className="bg-zinc-50">
                  <tr>
                    <th className="px-2 py-2">Champion</th>
                    <th className="px-2 py-2">Patch A ({patchA})</th>
                    <th className="px-2 py-2">Patch B ({patchB})</th>
                    <th className="px-2 py-2">Delta</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((row) => (
                    <tr key={row.champion} className="border-t">
                      <td className="px-2 py-2">{row.champion}</td>
                      <td className="px-2 py-2">{row.aValue.toFixed(3)}</td>
                      <td className="px-2 py-2">{row.bValue.toFixed(3)}</td>
                      <td
                        className={`px-2 py-2 ${row.delta > 0 ? "text-green-700" : row.delta < 0 ? "text-red-700" : ""}`}
                      >
                        {row.delta.toFixed(3)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        </>
      ) : null}
    </main>
  );
}

