export type DistributionItem = {
  champion: string;
  value: number;
  buffs: number;
  nerfs: number;
};

export type PatchDistribution = {
  version: string;
  metric: "net_impact_score";
  items: DistributionItem[];
};

export type PatchChangeDirection = "buff" | "nerf" | "adjustment";
export type PatchEntityType = "champion" | "item" | "system" | "all";
export type PatchChangeCategory =
  | "damage"
  | "cooldown"
  | "base_stat"
  | "scaling"
  | "cost"
  | "mechanic";

export type PatchChangeItem = {
  entity: string;
  ability_slot: string | null;
  category: PatchChangeCategory;
  direction: PatchChangeDirection;
  stat_name: string;
  old_value: unknown;
  new_value: unknown;
  delta_value: number | null;
  impact_score: number;
  tags: string[];
};

export type PatchChangesResponse = {
  version: string;
  filters: {
    category: string | null;
    direction: string | null;
    tag: string | null;
    entity: string | null;
    ability: string | null;
  };
  count: number;
  items: PatchChangeItem[];
};

export type PatchChangesQuery = {
  category?: PatchChangeCategory;
  direction?: PatchChangeDirection;
  tag?: string;
  entity?: string;
  ability?: string;
};

export type PatchListItem = {
  version: string;
  release_date: string;
  is_test: boolean;
  note: string | null;
};

export type PatchListResponse = {
  patches: PatchListItem[];
};

export type RoleDistributionBucket = {
  buffs: number;
  nerfs: number;
  adjustments: number;
  total_changes: number;
};

export type RoleDistributionDeltaBucket = {
  delta_total_changes: number;
  delta_buffs: number;
  delta_nerfs: number;
  delta_adjustments: number;
};

export type PatchComparisonIntelligence = {
  base_version: string;
  target_version: string;
  base: {
    version: string;
    buff_count: number;
    nerf_count: number;
    adjustment_count: number;
    risk_score: number;
    role_distribution: Record<string, RoleDistributionBucket>;
  };
  target: {
    version: string;
    buff_count: number;
    nerf_count: number;
    adjustment_count: number;
    risk_score: number;
    role_distribution: Record<string, RoleDistributionBucket>;
  };
  delta: {
    net_buff_count: number;
    net_nerf_count: number;
    risk_score_delta: number;
    role_distribution_changes: Record<string, RoleDistributionDeltaBucket>;
  };
};

export type SemanticSearchItem = {
  score: number;
  distance: number;
  patch_version: string;
  entity: string;
  entity_type: PatchEntityType;
  ability_slot: string | null;
  direction: PatchChangeDirection;
  category: PatchChangeCategory;
  stat_name: string;
  old_value: unknown;
  new_value: unknown;
  delta_value: number | null;
  impact_score: number;
  tags: string[];
  embedding_model: string;
};

export type SemanticSearchResponse = {
  query: string;
  count: number;
  filters: {
    patch_version?: string;
    direction?: string;
    category?: string;
    tag?: string;
    entity?: string;
  };
  items: SemanticSearchItem[];
};

export type SemanticSearchQuery = {
  query: string;
  k?: number;
  patch_version?: string;
  entity_type?: PatchEntityType;
  direction?: PatchChangeDirection;
  category?: PatchChangeCategory;
  tag?: string;
  entity?: string;
};

export type RagCitation = {
  index?: number;
  entity?: string;
  patch_version?: string;
};

export type RagResponse = {
  query: string;
  retrieved_count?: number;
  retrieval_entity_type?: PatchEntityType | "all" | string;
  retrieval_entity?: string | null;
  retrieved_items?: SemanticSearchItem[];
  explanation: string;
  impact_summary: string[];
  reasoning: string[];
  citations: RagCitation[];
};

export type RagQuery = {
  query: string;
  k?: number;
  patch_version?: string;
  entity_type?: PatchEntityType;
  direction?: PatchChangeDirection;
  category?: PatchChangeCategory;
  tag?: string;
  entity?: string;
};

export type PatchSummaryTopChampion = {
  name: string;
  net_impact_score: number;
};

export type PatchSummaryVolatilityChange = {
  champion: string;
  stat_name: string;
  direction: PatchChangeDirection;
  impact_score: number;
  delta_value: number | null;
  tags: string[];
};

export type PatchSummaryWatchItem = {
  champion: string;
  reason: string;
};

export type PatchSummaryReport = {
  version: string;
  top_5_impacted_champions: PatchSummaryTopChampion[];
  highest_volatility_changes: PatchSummaryVolatilityChange[];
  risk_analysis_paragraph: string;
  suggested_watch_list: PatchSummaryWatchItem[];
};

function getApiBaseUrl() {
  const configuredBaseUrl =
    process.env.API_BASE_URL ?? process.env.NEXT_PUBLIC_API_BASE_URL;

  if (!configuredBaseUrl) {
    return "http://127.0.0.1:8000";
  }

  // Server-side fetch in Node needs an absolute URL.
  // If env is set to a browser-relative proxy path like "/api",
  // call the colocated FastAPI process directly from SSR.
  if (configuredBaseUrl.startsWith("/") && typeof window === "undefined") {
    return "http://127.0.0.1:8000";
  }

  return configuredBaseUrl;
}

async function handleJsonResponse<T>(response: Response, message: string): Promise<T> {
  if (!response.ok) {
    throw new Error(`${message} (${response.status})`);
  }
  return (await response.json()) as T;
}

export async function getPatchDistribution(version: string): Promise<PatchDistribution> {
  const response = await fetch(`${getApiBaseUrl()}/patch/${version}/distribution`, {
    cache: "no-store",
  });
  return handleJsonResponse<PatchDistribution>(response, "Failed to load distribution");
}

export async function getPatchChanges(
  version: string,
  query: PatchChangesQuery = {},
): Promise<PatchChangesResponse> {
  const searchParams = new URLSearchParams();
  for (const [key, value] of Object.entries(query)) {
    const normalized = typeof value === "string" ? value.trim() : value;
    if (!normalized) {
      continue;
    }
    searchParams.set(key, String(normalized));
  }

  const queryString = searchParams.toString();
  const url = `${getApiBaseUrl()}/patch/${version}/changes${queryString ? `?${queryString}` : ""}`;
  const response = await fetch(url, { cache: "no-store" });
  return handleJsonResponse<PatchChangesResponse>(response, "Failed to load filtered changes");
}

export async function getPatchList(): Promise<PatchListResponse> {
  const response = await fetch(`${getApiBaseUrl()}/patch/list`, { cache: "no-store" });
  return handleJsonResponse<PatchListResponse>(response, "Failed to load patch list");
}

export async function getPatchComparisonIntelligence(
  baseVersion: string,
  targetVersion: string,
): Promise<PatchComparisonIntelligence> {
  const params = new URLSearchParams({
    base_version: baseVersion,
    target_version: targetVersion,
  });
  const response = await fetch(`${getApiBaseUrl()}/patch/compare/intelligence?${params.toString()}`, {
    cache: "no-store",
  });
  return handleJsonResponse<PatchComparisonIntelligence>(
    response,
    "Failed to load patch comparison intelligence",
  );
}

export async function semanticSearch(
  payload: SemanticSearchQuery,
): Promise<SemanticSearchResponse> {
  const response = await fetch(`${getApiBaseUrl()}/search/semantic`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
    cache: "no-store",
  });
  return handleJsonResponse<SemanticSearchResponse>(response, "Semantic search failed");
}

export async function explainWithRag(payload: RagQuery): Promise<RagResponse> {
  const response = await fetch(`${getApiBaseUrl()}/rag/explain`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
    cache: "no-store",
  });
  return handleJsonResponse<RagResponse>(response, "RAG explain failed");
}

export async function getPatchSummaryReport(version: string): Promise<PatchSummaryReport> {
  const response = await fetch(`${getApiBaseUrl()}/patch/${version}/summary-report`, {
    cache: "no-store",
  });
  return handleJsonResponse<PatchSummaryReport>(response, "Failed to generate patch summary");
}

