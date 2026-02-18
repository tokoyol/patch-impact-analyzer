import PatchImpactDistribution from "@/components/charts/PatchImpactDistribution";
import PatchChangesFilterPanel from "@/components/patch/PatchChangesFilterPanel";
import GeneratePatchSummaryPanel from "@/components/patch/GeneratePatchSummaryPanel";
import { getPatchDistribution } from "@/lib/api";

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
  const apiBaseUrl =
    process.env.API_BASE_URL ??
    process.env.NEXT_PUBLIC_API_BASE_URL ??
    "http://127.0.0.1:8000";
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

    return (
      <main className="mx-auto max-w-6xl space-y-4 p-6">
        <h1 className="text-2xl font-bold">Patch {patch.version}</h1>
        <p className="text-sm text-zinc-600">Release Date: {patch.release_date}</p>

        <section className="rounded-md border p-4">
          <h2 className="mb-2 text-lg font-semibold">Patch Notes</h2>
          <p>{patch.raw_notes}</p>
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

        <section className="rounded-md border p-4">
          <h2 className="mb-2 text-lg font-semibold">
            Patch Impact Distribution (by Champion)
          </h2>
          <PatchImpactDistribution data={distribution.items} />
        </section>

        <GeneratePatchSummaryPanel version={version} />

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

