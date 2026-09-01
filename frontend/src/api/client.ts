import { ApiError, type ValidationItem } from "../lib/apiErrors";
import type {
  BudgetView,
  BudgetWrite,
  ImportResult,
  JobView,
  LeagueCreate,
  LeaguePage,
  LeagueRulesView,
  LeagueRulesWrite,
  LeagueSettingsWrite,
  LeagueView,
  LineupRecommendationRequest,
  LineupRecommendationView,
  MarketImportRequest,
  MarketRecommendationRequest,
  MarketRecommendationView,
  MatchPage,
  MatchupRecommendationRequest,
  MatchupRecommendationView,
  PlayerDetail,
  PlayerFixturePrediction,
  PlayerOutlookRequest,
  PlayerOutlookView,
  PlayerPage,
  PlayerRecentFormView,
  ReadyResponse,
  RosterImportRequest,
  RosterView,
  SystemStatusView,
} from "./types";

export const API_BASE: string =
  (import.meta.env.VITE_API_BASE_URL as string | undefined) ??
  "http://localhost:8000";

const GET_TIMEOUT = 20_000;
const IMPORT_TIMEOUT = 120_000;

const DECISION_TIMEOUT = 300_000;

interface RequestOptions {
  method?: "GET" | "POST" | "PUT" | "PATCH";
  body?: unknown;
  signal?: AbortSignal;
  timeoutMs?: number;
}


function combinedSignal(
  signal: AbortSignal | undefined,
  timeoutMs: number,
): AbortSignal | undefined {
  const signals: AbortSignal[] = [];
  if (typeof AbortSignal.timeout === "function") {
    signals.push(AbortSignal.timeout(timeoutMs));
  }
  if (signal) signals.push(signal);
  if (signals.length === 0) return undefined;
  if (signals.length === 1) return signals[0];
  if (typeof AbortSignal.any === "function") return AbortSignal.any(signals);
  return signal;
}

async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { method = "GET", body, signal, timeoutMs = GET_TIMEOUT } = options;

  const response = await fetch(`${API_BASE}${path}`, {
    method,
    headers: body !== undefined ? { "Content-Type": "application/json" } : {},
    body: body !== undefined ? JSON.stringify(body) : null,
    ...(() => {
      const combined = combinedSignal(signal, timeoutMs);
      return combined ? { signal: combined } : {};
    })(),
  });

  if (!response.ok) {
    let validation: ValidationItem[] | null = null;
    try {
      const payload: unknown = await response.json();
      if (payload && typeof payload === "object" && "detail" in payload) {
        const rawDetail = (payload as { detail: unknown }).detail;
        if (Array.isArray(rawDetail)) {
          validation = rawDetail as ValidationItem[];
        }
      }
    } catch {
      validation = null;
    }
    throw new ApiError(response.status, null, validation);
  }

  return (await response.json()) as T;
}

function query(params: Record<string, string | number | boolean | undefined>): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined) search.set(key, String(value));
  }
  const text = search.toString();
  return text ? `?${text}` : "";
}

export const api = {
  ready: (signal?: AbortSignal) =>
    request<ReadyResponse>("/ready", { ...(signal && { signal }) }),

  systemStatus: (signal?: AbortSignal) =>
    request<SystemStatusView>("/api/v1/system/status", {
      ...(signal && { signal }),
    }),

  listLeagues: (localIdentity: string, signal?: AbortSignal) =>
    request<LeaguePage>(
      `/api/v1/leagues${query({ local_identity: localIdentity, limit: 100 })}`,
      { ...(signal && { signal }) },
    ),

  createLeague: (body: LeagueCreate) =>
    request<LeagueView>("/api/v1/leagues", { method: "POST", body }),

  getLeague: (leagueId: string, signal?: AbortSignal) =>
    request<LeagueView>(`/api/v1/leagues/${leagueId}`, {
      ...(signal && { signal }),
    }),

  updateLeagueSettings: (leagueId: string, body: LeagueSettingsWrite) =>
    request<LeagueView>(`/api/v1/leagues/${leagueId}`, {
      method: "PATCH",
      body,
    }),

  replaceRules: (leagueId: string, body: LeagueRulesWrite) =>
    request<LeagueRulesView>(`/api/v1/leagues/${leagueId}/rules`, {
      method: "PUT",
      body,
    }),

  updateBudget: (leagueId: string, fantasyTeamId: string, body: BudgetWrite) =>
    request<BudgetView>(
      `/api/v1/leagues/${leagueId}/teams/${fantasyTeamId}/budget`,
      { method: "PUT", body },
    ),

  listRosters: (leagueId: string, signal?: AbortSignal) =>
    request<RosterView[]>(`/api/v1/leagues/${leagueId}/rosters`, {
      ...(signal && { signal }),
    }),

  importRoster: (leagueId: string, body: RosterImportRequest) =>
    request<ImportResult>(`/api/v1/leagues/${leagueId}/rosters/import`, {
      method: "POST",
      body,
      timeoutMs: IMPORT_TIMEOUT,
    }),

  importMarket: (leagueId: string, body: MarketImportRequest) =>
    request<ImportResult>(`/api/v1/leagues/${leagueId}/market/import`, {
      method: "POST",
      body,
      timeoutMs: IMPORT_TIMEOUT,
    }),

  recommendLineup: (
    leagueId: string,
    body: LineupRecommendationRequest,
    signal?: AbortSignal,
  ) =>
    request<LineupRecommendationView>(
      `/api/v1/leagues/${leagueId}/recommendations/lineup`,
      { method: "POST", body, timeoutMs: DECISION_TIMEOUT, ...(signal && { signal }) },
    ),

  recommendMarket: (
    leagueId: string,
    body: MarketRecommendationRequest,
    signal?: AbortSignal,
  ) =>
    request<MarketRecommendationView>(
      `/api/v1/leagues/${leagueId}/recommendations/market`,
      { method: "POST", body, timeoutMs: DECISION_TIMEOUT, ...(signal && { signal }) },
    ),

  recommendMatchup: (
    leagueId: string,
    body: MatchupRecommendationRequest,
    signal?: AbortSignal,
  ) =>
    request<MatchupRecommendationView>(
      `/api/v1/leagues/${leagueId}/recommendations/matchup`,
      { method: "POST", body, timeoutMs: DECISION_TIMEOUT, ...(signal && { signal }) },
    ),

  listPlayers: (
    params: {
      search?: string;
      active?: boolean;
      limit?: number;
      offset?: number;
    },
    signal?: AbortSignal,
  ) =>
    request<PlayerPage>(`/api/v1/players${query(params)}`, {
      ...(signal && { signal }),
    }),

  getPlayer: (playerId: string, signal?: AbortSignal) =>
    request<PlayerDetail>(`/api/v1/players/${playerId}`, {
      ...(signal && { signal }),
    }),

  playerPredictions: (playerId: string, signal?: AbortSignal) =>
    request<PlayerFixturePrediction[]>(
      `/api/v1/predictions/player/${playerId}`,
      { ...(signal && { signal }), timeoutMs: 60_000 },
    ),

  playerRecentForm: (playerId: string, limit: number, signal?: AbortSignal) =>
    request<PlayerRecentFormView>(
      `/api/v1/players/${playerId}/recent-form${query({ limit })}`,
      { ...(signal && { signal }), timeoutMs: 60_000 },
    ),

  playerOutlook: (
    leagueId: string,
    playerId: string,
    body: PlayerOutlookRequest,
    signal?: AbortSignal,
  ) =>
    request<PlayerOutlookView>(
      `/api/v1/leagues/${leagueId}/players/${playerId}/outlook`,
      { method: "POST", body, timeoutMs: DECISION_TIMEOUT, ...(signal && { signal }) },
    ),

  upcomingFixtures: (
    params: { team_id?: string; limit?: number; offset?: number },
    signal?: AbortSignal,
  ) =>
    request<MatchPage>(`/api/v1/fixtures/upcoming${query(params)}`, {
      ...(signal && { signal }),
    }),

  refreshData: () =>
    request<JobView>("/api/v1/admin/data/refresh", {
      method: "POST",
      body: { parameters: {} },
    }),

  trainModels: () =>
    request<JobView>("/api/v1/admin/models/train", {
      method: "POST",
      body: { parameters: {} },
    }),

  getJob: (jobId: string, signal?: AbortSignal) =>
    request<JobView>(`/api/v1/admin/jobs/${jobId}`, {
      ...(signal && { signal }),
    }),
};
