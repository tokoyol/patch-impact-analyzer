import Link from "next/link";

import RagExplainPanel from "@/components/semantic/RagExplainPanel";
import SemanticSearchPanel from "@/components/semantic/SemanticSearchPanel";
import { getPatchList } from "@/lib/api";

export default async function Page() {
  try {
    const patchListResponse = await getPatchList();
    const patches = patchListResponse.patches;
    return (
      <main className="mx-auto max-w-3xl space-y-4 p-6">
        <h1 className="text-2xl font-bold">Patch Dashboard</h1>
        <p className="text-sm text-zinc-600">
          Select a patch to view notes, ranking, and impact distribution.
        </p>

        <section className="space-y-3">
          {patches.length === 0 ? (
            <p>No patches available yet.</p>
          ) : (
            patches.map((patch) => (
              <div key={patch.version} className="rounded-md border p-4">
                <div className="flex items-center justify-between gap-3">
                  <div>
                    <p className="font-semibold">Patch {patch.version}</p>
                    <p className="text-sm text-zinc-600">
                      Release Date: {patch.release_date}
                    </p>
                  </div>
                  <Link
                    href={`/patch/${patch.version}`}
                    className="rounded border px-3 py-1 text-sm hover:bg-zinc-100"
                  >
                    Open
                  </Link>
                </div>
                {patch.is_test ? (
                  <p className="mt-2 inline-block rounded bg-amber-100 px-2 py-1 text-xs text-amber-800">
                    {patch.note}
                  </p>
                ) : null}
              </div>
            ))
          )}
        </section>

        <SemanticSearchPanel availablePatchVersions={patches.map((patch) => patch.version)} />
        <RagExplainPanel availablePatchVersions={patches.map((patch) => patch.version)} />
      </main>
    );
  } catch (error) {
    const message = error instanceof Error ? error.message : "Unexpected error occurred.";
    return (
      <main className="mx-auto max-w-3xl p-6">
        <h1 className="text-2xl font-bold">Patch Dashboard</h1>
        <p className="mt-3 text-red-600">Could not load patch list. {message}</p>
      </main>
    );
  }
}
