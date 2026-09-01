import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import { useLeague, useLeagues } from "../api/queries";
import type { FantasyTeamView, LeagueSummary, LeagueView } from "../api/types";
import { getSelectedLeagueId, setSelectedLeagueId } from "../lib/prefs";

interface LeagueContextValue {
  leaguesLoading: boolean;
  leaguesError: boolean;
  leagues: LeagueSummary[];
  refetchLeagues: () => void;
  leagueId: string | null;
  selectLeague: (id: string | null) => void;
  league: LeagueView | null;
  leagueLoading: boolean;
  leagueError: boolean;
  refetchLeague: () => void;
  userTeam: FantasyTeamView | null;
}

const LeagueContext = createContext<LeagueContextValue | null>(null);

export function LeagueProvider({ children }: { children: ReactNode }) {
  const leaguesQuery = useLeagues();
  const [leagueId, setLeagueId] = useState<string | null>(() =>
    getSelectedLeagueId(),
  );

  const leagues = useMemo(
    () => leaguesQuery.data?.items ?? [],
    [leaguesQuery.data],
  );


  const validatedId = useMemo(() => {
    if (leagueId === null) return null;
    if (leaguesQuery.data === undefined) return leagueId;
    return leagues.some((league) => league.id === leagueId) ? leagueId : null;
  }, [leagueId, leagues, leaguesQuery.data]);

  const leagueQuery = useLeague(validatedId);

  const selectLeague = useCallback((id: string | null) => {
    setLeagueId(id);
    setSelectedLeagueId(id);
  }, []);

  const userTeam = useMemo(() => {
    const teams = leagueQuery.data?.fantasy_teams ?? [];
    return teams.find((team) => team.is_user_team) ?? null;
  }, [leagueQuery.data]);

  const value = useMemo<LeagueContextValue>(
    () => ({
      leaguesLoading: leaguesQuery.isPending,
      leaguesError: leaguesQuery.isError,
      leagues,
      refetchLeagues: () => {
        void leaguesQuery.refetch();
      },
      leagueId: validatedId,
      selectLeague,
      league: leagueQuery.data ?? null,
      leagueLoading: leagueQuery.isPending && validatedId !== null,
      leagueError: leagueQuery.isError,
      refetchLeague: () => { void leagueQuery.refetch(); },
      userTeam,
    }),
    [leaguesQuery, leagues, validatedId, selectLeague, leagueQuery, userTeam],
  );

  return <LeagueContext.Provider value={value}>{children}</LeagueContext.Provider>;
}

export function useLeagueContext(): LeagueContextValue {
  const value = useContext(LeagueContext);
  if (value === null) {
    throw new Error();
  }
  return value;
}


export function useActiveLeague() {
  const { league, leagueId, userTeam } = useLeagueContext();
  if (leagueId === null) {
    throw new Error();
  }
  return { leagueId, league, userTeam };
}
