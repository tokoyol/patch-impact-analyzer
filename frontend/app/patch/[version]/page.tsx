import PatchImpactDistribution from "@/components/charts/PatchImpactDistribution";
import PatchChangesFilterPanel from "@/components/patch/PatchChangesFilterPanel";
import GeneratePatchSummaryPanel from "@/components/patch/GeneratePatchSummaryPanel";
import { getPatchDistribution, getPatchSummaryReport, PatchSummaryReport } from "@/lib/api";

type TopImpacted = {
  name: string;
  score: number;
};

type PatchSummary = {
  version: string;
  release_date: string;
  raw_notes: string;
  total_buffs: number;
  total_nerfs: number;
  top_impacted: TopImpacted[];
};

type PageProps = {
  params: Promise<{ version: string }>;
};

async function getPatchSummary(version: string): Promise<PatchSummary> {
  const configuredBaseUrl = process.env.API_BASE_URL ?? process.env.NEXT_PUBLIC_API_BASE_URL;
  const apiBaseUrl =
    configuredBaseUrl && configuredBaseUrl.startsWith("/")
      ? "http://127.0.0.1:8000"
      : configuredBaseUrl ?? "http://127.0.0.1:8000";
  const response = await fetch(`${apiBaseUrl}/patch/${version}`, {
    cache: "no-store",
  });

  if (!response.ok) {
    throw new Error(`Failed to load patch ${version} (${response.status})`);
  }

  return (await response.json()) as PatchSummary;
}

export default async function Page({ params }: PageProps) {
  const { version } = await params;

  try {
    const [patch, distribution] = await Promise.all([
      getPatchSummary(version),
      getPatchDistribution(version),
    ]);
    let aiSummary: PatchSummaryReport | null = null;
    try {
      aiSummary = await getPatchSummaryReport(version);
    } catch {
      aiSummary = null;
    }

    return (
      <main className="mx-auto max-w-6xl space-y-4 p-6">
        <h1 className="text-2xl font-bold">Patch {patch.version}</h1>
        <p className="text-sm text-zinc-600">Release Date: {patch.release_date}</p>

        <section className="rounded-md border p-4">
          <h2 className="mb-2 text-lg font-semibold">AI Patch Summary</h2>
          <p className="mb-2 text-sm text-zinc-600">
            Impact score is a weighted net change estimate from this patch. Higher positive values suggest stronger net buffs,
            while lower/negative values suggest stronger net nerfs. Larger magnitude means bigger projected meta impact.
          </p>
          {aiSummary ? (
            <div className="space-y-3">
              <p className="text-sm">{aiSummary.risk_analysis_paragraph}</p>
              {aiSummary.top_5_impacted_champions.length ? (
                <div>
                  <h3 className="font-semibold text-sm">Top Impacted Champions</h3>
                  <ul className="list-disc pl-5 text-sm">
                    {aiSummary.top_5_impacted_champions.map((champion) => (
                      <li key={champion.name}>
                        {champion.name}: {champion.net_impact_score.toFixed(2)}
                      </li>
                    ))}
                  </ul>
                </div>
              ) : null}
            </div>
          ) : (
            <p className="text-sm text-zinc-600">
              AI summary is unavailable for this patch right now. Try Generate Patch Summary again.
            </p>
          )}
        </section>

        <GeneratePatchSummaryPanel version={version} />

        <section className="rounded-md border p-4">
          <h2 className="mb-2 text-lg font-semibold">
            Patch Impact Distribution (by Champion)
          </h2>
          <PatchImpactDistribution data={distribution.items} />
        </section>

        <section className="rounded-md border p-4">
          <h2 className="mb-2 text-lg font-semibold">Impact Summary</h2>
          <p>Total Buffs: {patch.total_buffs}</p>
          <p>Total Nerfs: {patch.total_nerfs}</p>
        </section>

        <section className="rounded-md border p-4">
          <h2 className="mb-2 text-lg font-semibold">Top Impacted</h2>
          {patch.top_impacted.length === 0 ? (
            <p>No impacted entities yet.</p>
          ) : (
            <ul className="space-y-1">
              {patch.top_impacted.map((entity) => (
                <li key={entity.name}>
                  {entity.name}: {entity.score}
                </li>
              ))}
            </ul>
          )}
        </section>

        <PatchChangesFilterPanel version={version} />
      </main>
    );
  } catch (error) {
    const message =
      error instanceof Error ? error.message : "Unexpected error occurred.";
    return (
      <main className="mx-auto max-w-3xl p-6">
        <h1 className="text-2xl font-bold">Patch {version}</h1>
        <p className="mt-3 text-red-600">
          Could not load patch data. {message}
        </p>
      </main>
    );
  }
}

