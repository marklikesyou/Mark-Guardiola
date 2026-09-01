import {
  useMutation,
  useQuery,
  useQueryClient,
  type QueryClient,
} from "@tanstack/react-query";
import { getLocalIdentity } from "../lib/prefs";
import { api } from "./client";
import type {
  BudgetWrite,
  LeagueCreate,
  LeagueRulesWrite,
  LeagueSettingsWrite,
  MarketImportRequest,
  RiskMode,
  RosterImportRequest,
} from "./types";

export const keys = {
  leagues: (identity: string) => ["leagues", identity] as const,
  league: (id: string) => ["league", id] as const,
  rosters: (leagueId: string) => ["rosters", leagueId] as const,
  lineup: (leagueId: string, risk: RiskMode) =>
    ["lineup", leagueId, risk] as const,
  market: (leagueId: string, horizon: number, recover: boolean) =>
    ["market", leagueId, horizon, recover] as const,
  matchup: (leagueId: string, opponentId: string) =>
    ["matchup", leagueId, opponentId] as const,
  players: (search: string, active: boolean, offset: number) =>
    ["players", search, active, offset] as const,
  player: (id: string) => ["player", id] as const,
  predictions: (playerId: string) => ["predictions", playerId] as const,
  recentForm: (playerId: string, limit: number) =>
    ["recent-form", playerId, limit] as const,
  outlook: (leagueId: string, playerId: string, horizon: number) =>
    ["outlook", leagueId, playerId, horizon] as const,
  system: ["system"] as const,
  job: (id: string) => ["job", id] as const,
};





export function invalidateDecisions(client: QueryClient): void {
  void client.invalidateQueries({ queryKey: ["lineup"] });
  void client.invalidateQueries({ queryKey: ["market"] });
  void client.invalidateQueries({ queryKey: ["matchup"] });
  void client.invalidateQueries({ queryKey: ["outlook"] });
}

export function useLeagues() {
  const identity = getLocalIdentity();
  return useQuery({
    queryKey: keys.leagues(identity),
    queryFn: ({ signal }) => api.listLeagues(identity, signal),
  });
}

export function useLeague(leagueId: string | null) {
  return useQuery({
    queryKey: keys.league(leagueId ?? "nessuna"),
    queryFn: ({ signal }) => api.getLeague(leagueId as string, signal),
    enabled: leagueId !== null,
  });
}

export function useCreateLeague() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: LeagueCreate) => api.createLeague(body),
    onSuccess: (league) => {
      client.setQueryData(keys.league(league.id), league);
      void client.invalidateQueries({ queryKey: ["leagues"] });
    },
  });
}

export function useUpdateLeagueSettings(leagueId: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: LeagueSettingsWrite) =>
      api.updateLeagueSettings(leagueId, body),
    onSuccess: (league) => {
      client.setQueryData(keys.league(leagueId), league);
      void client.invalidateQueries({ queryKey: ["leagues"] });

      void client.invalidateQueries({ queryKey: ["matchup"] });
    },
  });
}

export function useReplaceRules(leagueId: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: LeagueRulesWrite) => api.replaceRules(leagueId, body),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: keys.league(leagueId) });

      void client.invalidateQueries({ queryKey: keys.rosters(leagueId) });
      invalidateDecisions(client);
    },
  });
}

export function useUpdateBudget(leagueId: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({
      fantasyTeamId,
      body,
    }: {
      fantasyTeamId: string;
      body: BudgetWrite;
    }) => api.updateBudget(leagueId, fantasyTeamId, body),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: keys.league(leagueId) });
      void client.invalidateQueries({ queryKey: keys.rosters(leagueId) });

      void client.invalidateQueries({ queryKey: ["market"] });
    },
  });
}

export function useRosters(leagueId: string) {
  return useQuery({
    queryKey: keys.rosters(leagueId),
    queryFn: ({ signal }) => api.listRosters(leagueId, signal),
  });
}

export function useImportRoster(leagueId: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: RosterImportRequest) => api.importRoster(leagueId, body),
    onSuccess: () => {
      void client.invalidateQueries({ queryKey: keys.rosters(leagueId) });
      void client.invalidateQueries({ queryKey: keys.league(leagueId) });
      invalidateDecisions(client);
    },
  });
}

export function useImportMarket(leagueId: string) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: MarketImportRequest) => api.importMarket(leagueId, body),
    onSuccess: () => {

      void client.invalidateQueries({ queryKey: keys.rosters(leagueId) });
      invalidateDecisions(client);
    },
  });
}

export function useLineup(leagueId: string, risk: RiskMode) {
  return useQuery({
    queryKey: keys.lineup(leagueId, risk),
    queryFn: ({ signal }) =>
      api.recommendLineup(leagueId, { risk_mode: risk }, signal),
    staleTime: Infinity,
    retry: false,
    refetchOnWindowFocus: false,
  });
}

export function useMarket(
  leagueId: string,
  horizon: 1 | 3 | 5 | 10,
  recoverPrice: boolean,
  enabled: boolean,
) {
  return useQuery({
    queryKey: keys.market(leagueId, horizon, recoverPrice),
    queryFn: ({ signal }) =>
      api.recommendMarket(
        leagueId,
        { horizon, recover_purchase_price: recoverPrice },
        signal,
      ),
    staleTime: Infinity,
    retry: false,
    refetchOnWindowFocus: false,
    enabled,
  });
}

export function useMatchup(leagueId: string, opponentId: string, enabled: boolean) {
  return useQuery({
    queryKey: keys.matchup(leagueId, opponentId),
    queryFn: ({ signal }) =>
      api.recommendMatchup(leagueId, { opponent_fantasy_team_id: opponentId }, signal),
    enabled: enabled && opponentId !== "",
    staleTime: Infinity,
    retry: false,
    refetchOnWindowFocus: false,
  });
}

export function usePlayers(search: string, onlyActive: boolean, offset: number) {
  return useQuery({
    queryKey: keys.players(search, onlyActive, offset),
    queryFn: ({ signal }) =>
      api.listPlayers(
        {
          ...(search ? { search } : {}),
          ...(onlyActive ? { active: true } : {}),
          limit: 50,
          offset,
        },
        signal,
      ),
    placeholderData: (previous) => previous,
  });
}

export function usePlayer(playerId: string) {
  return useQuery({
    queryKey: keys.player(playerId),
    queryFn: ({ signal }) => api.getPlayer(playerId, signal),
  });
}

export function usePlayerPredictions(playerId: string) {
  return useQuery({
    queryKey: keys.predictions(playerId),
    queryFn: ({ signal }) => api.playerPredictions(playerId, signal),
  });
}

export function useRecentForm(playerId: string, limit = 5) {
  return useQuery({
    queryKey: keys.recentForm(playerId, limit),
    queryFn: ({ signal }) => api.playerRecentForm(playerId, limit, signal),
    staleTime: 5 * 60_000,
  });
}

export function useOutlook(
  leagueId: string,
  playerId: string,
  horizon: number,
) {
  return useQuery({
    queryKey: keys.outlook(leagueId, playerId, horizon),
    queryFn: ({ signal }) =>
      api.playerOutlook(leagueId, playerId, { horizon }, signal),
    staleTime: Infinity,
    retry: false,
    refetchOnWindowFocus: false,
  });
}

export function useSystemStatus() {
  return useQuery({
    queryKey: keys.system,
    queryFn: ({ signal }) => api.systemStatus(signal),
    staleTime: 60_000,
    refetchOnWindowFocus: true,
  });
}

export function useJob(jobId: string | null) {
  return useQuery({
    queryKey: keys.job(jobId ?? "nessuno"),
    queryFn: ({ signal }) => api.getJob(jobId as string, signal),
    enabled: jobId !== null,
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      return status === "queued" || status === "running" ? 2500 : false;
    },
  });
}
