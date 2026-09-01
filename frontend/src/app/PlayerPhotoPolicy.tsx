import {
  createContext,
  useContext,
  useMemo,
  type ComponentProps,
  type ReactNode,
} from "react";
import { useRosters } from "../api/queries";
import { PlayerPortrait } from "../ui/primitives";
import { useActiveLeague } from "./LeagueContext";

const OwnPlayerIdsContext = createContext<ReadonlySet<string> | null>(null);

export function ownPlayerPhotoUrl(
  playerId: string,
  photoUrl: string | null | undefined,
  ownPlayerIds: ReadonlySet<string> | null,
): string | null {
  if (ownPlayerIds === null || !ownPlayerIds.has(playerId)) return null;
  return photoUrl ?? null;
}

export function PlayerPhotoPolicyProvider({ children }: { children: ReactNode }) {
  const { leagueId } = useActiveLeague();
  const rosters = useRosters(leagueId);

  const ownPlayerIds = useMemo<ReadonlySet<string> | null>(() => {
    if (rosters.data === undefined) return null;
    const ownRoster = rosters.data.find(
      (roster) => roster.fantasy_team.is_user_team,
    );
    return new Set(ownRoster?.players.map((player) => player.player_id) ?? []);
  }, [rosters.data]);

  return (
    <OwnPlayerIdsContext.Provider value={ownPlayerIds}>
      {children}
    </OwnPlayerIdsContext.Provider>
  );
}

type PlayerPortraitProps = ComponentProps<typeof PlayerPortrait>;

export function OwnedPlayerPortrait({
  playerId,
  photoUrl,
  ...portraitProps
}: PlayerPortraitProps & { playerId: string }) {
  const ownPlayerIds = useContext(OwnPlayerIdsContext);
  return (
    <PlayerPortrait
      {...portraitProps}
      photoUrl={ownPlayerPhotoUrl(playerId, photoUrl, ownPlayerIds)}
    />
  );
}
