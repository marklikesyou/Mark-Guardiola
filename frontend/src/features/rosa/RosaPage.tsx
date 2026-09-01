import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { Link } from "react-router-dom";
import { useRosters, useUpdateBudget } from "../../api/queries";
import type {
  RosterPlayerView,
  RosterValidation,
  RosterView,
} from "../../api/types";
import { useActiveLeague } from "../../app/LeagueContext";
import { OwnedPlayerPortrait } from "../../app/PlayerPhotoPolicy";
import { errorMessage } from "../../lib/apiErrors";
import { fmtCredits, parseDecimalInput } from "../../lib/format";
import {
  pitchGroupOf,
  roleLetter,
} from "../../lib/roles";
import { it } from "../../lib/strings";
import { IconChevron, IconPlus } from "../../ui/icons";
import {
  Board,
  EmptyState,
  InlineEdit,
  Mark,
  Skeleton,
} from "../../ui/primitives";

export function RosterValidationNotice({
  validation,
}: {
  validation: RosterValidation;
}) {
  if (validation.valid) return null;
  const onlyDraft = validation.issues.every(
    (issue) => issue.code === "minimum_players" || issue.code === "missing_roles",
  );
  return (
    <Board title={it.lega.rosterInvalidTitle}>
      <div style={{ display: "grid", gap: "var(--s-3)" }}>
        <p className="field__hint">
          {it.rosa.validationIntro}{" "}
          {onlyDraft ? it.rosa.validationDraftNote : it.lega.rosterInvalidRulesNote}
        </p>
        <ul style={{ display: "grid", gap: "var(--s-2)" }}>
          {validation.issues.map((issue) => (
            <li key={issue.code + issue.message} className="notice notice--warn">
              <Mark kind="warn" />
              <span>{issue.message}</span>
            </li>
          ))}
        </ul>
        <p className="field__hint">
          {it.rosa.playerCount(validation.player_count)} ·{" "}
          <Link to="/lega">{it.lega.rulesBoard}</Link>
        </p>
      </div>
    </Board>
  );
}

function groupByRole(
  players: RosterPlayerView[],
): Array<{ role: string; players: RosterPlayerView[] }> {
  const buckets = new Map<string, RosterPlayerView[]>();
  for (const player of players) {
    const group = pitchGroupOf(player.roles, player.primary_position);
    const bucket = buckets.get(group) ?? [];
    bucket.push(player);
    buckets.set(group, bucket);
  }
  const ordered: Array<{ role: string; players: RosterPlayerView[] }> = [];
  for (const role of ["FWD", "MID", "DEF", "GK", "other"]) {
    const bucket = buckets.get(role);
    if (bucket && bucket.length > 0) {
      bucket.sort((a, b) => a.display_name.localeCompare(b.display_name, "it"));
      ordered.push({ role, players: bucket });
    }
  }
  return ordered;
}

function RosterRoleLane({
  role,
  players,
  limit,
}: {
  role: string;
  players: RosterPlayerView[];
  limit: number | null;
}) {
  const trackRef = useRef<HTMLUListElement>(null);
  const [canGoBack, setCanGoBack] = useState(false);
  const [canGoForward, setCanGoForward] = useState(false);
  const roleName = it.rosa.roleNames[role] ?? role;
  const headingId = `reparto-${role.toLocaleLowerCase("it-IT")}`;

  const updateScrollState = useCallback(() => {
    const track = trackRef.current;
    if (!track) return;
    const end = track.scrollWidth - track.clientWidth;
    setCanGoBack(track.scrollLeft > 2);
    setCanGoForward(end - track.scrollLeft > 2);
  }, []);

  useEffect(() => {
    const track = trackRef.current;
    if (!track) return;
    const frame = window.requestAnimationFrame(updateScrollState);
    const observer = new ResizeObserver(updateScrollState);
    observer.observe(track);
    return () => {
      window.cancelAnimationFrame(frame);
      observer.disconnect();
    };
  }, [players.length, updateScrollState]);

  function scroll(direction: -1 | 1) {
    const track = trackRef.current;
    if (!track) return;
    const card = track.firstElementChild?.getBoundingClientRect();
    const distance = card ? card.width + 12 : track.clientWidth * 0.75;
    track.scrollBy({
      left: direction * distance,
      behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches
        ? "auto"
        : "smooth",
    });
  }

  return (
    <section
      className={`roster-lane roster-lane--${role.toLowerCase()}`}
      aria-labelledby={headingId}
    >
      <div className="roster-lane__head">
        <h3 className="roster-lane__title" id={headingId}>
          {it.rosa.countOf(players.length, limit, roleName)}
        </h3>
        <div className="roster-lane__controls">
          <button
            type="button"
            className="roster-lane__nav roster-lane__nav--previous"
            aria-label={it.rosa.previousRole(roleName)}
            disabled={!canGoBack}
            onClick={() => scroll(-1)}
          >
            <IconChevron />
          </button>
          <button
            type="button"
            className="roster-lane__nav"
            aria-label={it.rosa.nextRole(roleName)}
            disabled={!canGoForward}
            onClick={() => scroll(1)}
          >
            <IconChevron />
          </button>
        </div>
      </div>
      <ul
        className="roster-lane__track"
        ref={trackRef}
        onScroll={updateScrollState}
      >
        {players.map((player) => {
          const price = fmtCredits(player.purchase_price);
          const roles =
            player.roles.length > 0
              ? player.roles
              : player.primary_position
                ? [player.primary_position]
                : [];
          return (
            <li
              key={player.player_id}
              className={`roster-card${player.active ? "" : " roster-card--inactive"}`}
            >
              <Link to={`/giocatori/${player.player_id}`} className="roster-card__link">
                <OwnedPlayerPortrait
                  playerId={player.player_id}
                  name={player.display_name}
                  photoUrl={player.photo_url}
                  size="medium"
                />
                <span className="roster-card__copy">
                  <span className="roster-card__name">{player.display_name}</span>
                  {roles.length > 0 ? (
                    <span className="roster-card__roles" aria-label={roles.join(", ")}>
                      {roles.map((playerRole) => (
                        <span className="chip" key={playerRole}>
                          {roleLetter(playerRole)}
                        </span>
                      ))}
                    </span>
                  ) : null}
                </span>
                <span className="roster-card__foot">
                  <span>
                    {it.imports.price} <strong className="num">{price ?? it.app.notAvailable}</strong>
                  </span>
                  {!player.active ? (
                    <span className="roster-card__state">
                      <Mark kind="out" /> {it.rosa.inactive}
                    </span>
                  ) : null}
                </span>
              </Link>
            </li>
          );
        })}
      </ul>
    </section>
  );
}

export function RosaPage() {
  const { leagueId, league, userTeam } = useActiveLeague();
  const rosters = useRosters(leagueId);
  const updateBudget = useUpdateBudget(leagueId);

  const userRoster: RosterView | null = useMemo(() => {
    const all = rosters.data ?? [];
    return all.find((roster) => roster.fantasy_team.is_user_team) ?? null;
  }, [rosters.data]);

  const roleLimits = useMemo(() => {
    const constraints = league?.rules.roster_constraints;
    if (
      constraints &&
      typeof constraints === "object" &&
      "role_limits" in constraints
    ) {
      return (constraints as { role_limits: Record<string, number> }).role_limits;
    }
    return null;
  }, [league]);

  const groups = useMemo(
    () => (userRoster ? groupByRole(userRoster.players) : []),
    [userRoster],
  );

  const remaining = userRoster?.fantasy_team.remaining_credits ?? null;

  return (
    <div className="page">
      <div className="page__head">
        <h1 className="page__title">{it.rosa.title}</h1>
        <div className="page__actions">
          <Link to="/rosa/aggiungi" className="btn btn--primary btn--small">
            <IconPlus /> {it.aggiungi.entryRoster}
          </Link>
          <Link to="/rosa/importa" className="btn btn--secondary btn--small">
            {it.rosa.reimport}
          </Link>
        </div>
      </div>

      {rosters.isPending ? (
        <Board title={it.rosa.title}>
          <Skeleton lines={8} />
        </Board>
      ) : rosters.isError ? (
        <Board title={it.rosa.title}>
          <EmptyState title={it.app.error} body={errorMessage(rosters.error)}>
            <button
              type="button"
              className="btn btn--primary"
              onClick={() => {
                void rosters.refetch();
              }}
            >
              {it.app.retry}
            </button>
          </EmptyState>
        </Board>
      ) : userRoster === null || userRoster.players.length === 0 ? (
        <Board title={it.rosa.title}>
          <EmptyState title={it.rosa.emptyTitle} body={it.rosa.emptyBody}>
            <Link to="/rosa/importa" className="btn btn--primary">
              {it.rosa.emptyCta}
            </Link>
          </EmptyState>
        </Board>
      ) : (
        <>
          {userRoster.validation ? (
            <RosterValidationNotice validation={userRoster.validation} />
          ) : null}
          <section className="roster-board" aria-labelledby="organico-title">
            <div className="roster-board__head">
              <h2 className="roster-board__title" id="organico-title">
                {it.rosa.boardTitle}
              </h2>
              <div className="roster-board__meta">
                <InlineEdit
                  label={it.rosa.budgetEdit}
                  display={
                    remaining !== null
                      ? `${it.rosa.budget}: ${fmtCredits(remaining) ?? it.app.notAvailable}`
                      : it.mercato.budgetUnknown
                  }
                  initial={fmtCredits(remaining) ?? ""}
                  savedText={it.rosa.budgetSaved}
                  validate={parseDecimalInput}
                  onSave={async (normalized) => {
                    if (userTeam === null) return;
                    await updateBudget.mutateAsync({
                      fantasyTeamId: userTeam.id,
                      body: { remaining_credits: normalized },
                    });
                  }}
                />
              </div>
            </div>
            <div className="roster-pitch">
              {groups.map((group) => (
                <RosterRoleLane
                  key={group.role}
                  role={group.role}
                  players={group.players}
                  limit={
                    league?.mode === "classic"
                      ? (roleLimits?.[group.role] ?? null)
                      : null
                  }
                />
              ))}
            </div>
            <div className="roster-board__foot">
              <span>
                {userRoster.players.length} giocatori ·{" "}
                {it.rosa.budget.toLowerCase()}:{" "}
                {remaining !== null
                  ? (fmtCredits(remaining) ?? it.app.notAvailable)
                  : it.app.notAvailable}
              </span>
            </div>
          </section>
        </>
      )}
    </div>
  );
}
