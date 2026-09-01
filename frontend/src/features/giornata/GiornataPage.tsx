import { useQueryClient } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { keys, useLineup, useMatchup } from "../../api/queries";
import type {
  LineupRecommendationView,
  RiskMode,
  SelectedPlayerView,
} from "../../api/types";
import { useActiveLeague } from "../../app/LeagueContext";
import { OwnedPlayerPortrait } from "../../app/PlayerPhotoPolicy";
import { ApiError, conflictGuidance, errorMessage } from "../../lib/apiErrors";
import {
  clamp01,
  fmtDateTimeFull,
  fmtNumber,
  fmtPct,
  fmtPoints,
  fmtRange,
  itDecimals,
} from "../../lib/format";
import { roleGroupName, roleLetter } from "../../lib/roles";
import { it } from "../../lib/strings";
import {
  Board,
  Disclosure,
  EmptyState,
  LongWait,
  Mark,
  Meter,
  Notice,
  Segmented,
} from "../../ui/primitives";

const RISK_OPTIONS: Array<{ value: RiskMode; label: string; title: string }> = [
  {
    value: "balanced",
    label: it.giornata.riskBalanced,
    title: it.giornata.riskBalancedLong,
  },
  {
    value: "floor",
    label: it.giornata.riskFloor,
    title: it.giornata.riskFloorLong,
  },
  {
    value: "upside",
    label: it.giornata.riskUpside,
    title: it.giornata.riskUpsideLong,
  },
];


const MANTRA_LINES: Array<{ label: string; slots: string[] }> = [
  { label: "Portiere", slots: ["Por"] },
  { label: "Difesa", slots: ["Dd", "Dc", "Ds", "B"] },
  { label: "Centrocampo", slots: ["E", "M", "C"] },
  { label: "Trequarti", slots: ["W", "T"] },
  { label: "Attacco", slots: ["A", "Pc"] },
];

function groupStarters(
  starters: SelectedPlayerView[],
  mode: "classic" | "mantra",
): Array<{ label: string; players: SelectedPlayerView[] }> {
  if (mode === "classic") {
    const order = ["GK", "DEF", "MID", "FWD"];
    return order
      .map((slot) => ({
        label: roleGroupName(slot),
        players: starters.filter((player) => player.slot === slot),
      }))
      .filter((group) => group.players.length > 0);
  }
  const groups = MANTRA_LINES.map((line) => ({
    label: line.label,
    players: starters.filter((player) => line.slots.includes(player.slot)),
  })).filter((group) => group.players.length > 0);
  const covered = new Set(MANTRA_LINES.flatMap((line) => line.slots));
  const rest = starters.filter((player) => !covered.has(player.slot));
  if (rest.length > 0) groups.push({ label: "Altri", players: rest });
  return groups;
}

export function GiornataPage() {
  const { leagueId, league } = useActiveLeague();
  const [risk, setRisk] = useState<RiskMode>("balanced");
  const [cancelled, setCancelled] = useState(false);
  const client = useQueryClient();
  const lineup = useLineup(leagueId, risk);
  const timezone = league?.timezone ?? "Europe/Rome";

  const riskLabel =
    RISK_OPTIONS.find((option) => option.value === risk)?.label ?? "";

  async function cancelComputation() {
    await client.cancelQueries({ queryKey: keys.lineup(leagueId, risk) });
    setCancelled(true);
  }

  function retry() {
    setCancelled(false);
    void lineup.refetch();
  }

  return (
    <div className="page">
      <div className="page__head">
        <h1 className="page__title">{it.giornata.title}</h1>
        <Segmented
          legend={it.giornata.riskLabel}
          options={RISK_OPTIONS}
          value={risk}
          onChange={(next) => {
            setCancelled(false);
            setRisk(next);
          }}
          disabled={lineup.isFetching}
        />
      </div>

      {cancelled ? (
        <Board title={it.giornata.formationBoard}>
          <EmptyState title={it.app.requestCancelled}>
            <button type="button" className="btn btn--primary" onClick={retry}>
              {it.app.retry}
            </button>
          </EmptyState>
        </Board>
      ) : lineup.isPending || lineup.isFetching ? (
        <Board title={it.giornata.formationBoard} busy>
          <LongWait
            title={it.giornata.computing}
            body={it.giornata.computingBody}
            onCancel={() => {
              void cancelComputation();
            }}
          />
        </Board>
      ) : lineup.isError ? (
        <LineupError error={lineup.error} onRetry={retry} />
      ) : (
        <LineupResult
          view={lineup.data}
          mode={league?.mode ?? "classic"}
          riskLabel={riskLabel}
          timezone={timezone}
          onRecalc={retry}
        />
      )}

      {league?.head_to_head_enabled ? <MatchupSection /> : null}
    </div>
  );
}

function LineupError({
  error,
  onRetry,
}: {
  error: unknown;
  onRetry: () => void;
}) {
  if (error instanceof ApiError && (error.status === 409 || error.status === 404)) {
    const guidance = conflictGuidance(error);
    return (
      <Board title={it.giornata.formationBoard}>
        <EmptyState title={guidance.title} body={guidance.body}>
          {guidance.cta && guidance.to ? (
            <Link to={guidance.to} className="btn btn--primary">
              {guidance.cta}
            </Link>
          ) : null}
          <button type="button" className="btn btn--secondary" onClick={onRetry}>
            {it.app.retry}
          </button>
        </EmptyState>
        {guidance.raw ? (
          <Disclosure label={it.giornata.advanced}>
            <p>{guidance.raw}</p>
          </Disclosure>
        ) : null}
      </Board>
    );
  }
  return (
    <Board title={it.giornata.formationBoard}>
      <EmptyState title={it.app.error} body={errorMessage(error)}>
        <button type="button" className="btn btn--primary" onClick={onRetry}>
          {it.app.retry}
        </button>
      </EmptyState>
    </Board>
  );
}


function RangeRule({
  p10,
  p90,
  expected,
}: {
  p10: number;
  p90: number;
  expected: number;
}) {
  const span = p90 - p10;
  const position = span > 0 ? clamp01((expected - p10) / span) : 0.5;
  return (
    <div className="rangerule" aria-hidden="true">
      <i className="rangerule__end" />
      <i className="rangerule__mark" style={{ left: `${position * 100}%` }} />
      <i className="rangerule__end rangerule__end--right" />
    </div>
  );
}

function LineupResult({
  view,
  mode,
  riskLabel,
  timezone,
  onRecalc,
}: {
  view: LineupRecommendationView;
  mode: "classic" | "mantra";
  riskLabel: string;
  timezone: string;
  onRecalc: () => void;
}) {
  const groups = useMemo(
    () => groupStarters(view.starters, mode),
    [view.starters, mode],
  );

  return (
    <div className="cols cols--lead">
      {                                                                      }
      <p className="scorecap" aria-hidden="true">
        <strong className="num">{fmtRange(view.p10_points, view.p90_points)}</strong>{" "}
        {it.giornata.points} · {it.giornata.confidence.toLowerCase()}{" "}
        <span className="num">{fmtPct(view.confidence)}</span>
      </p>
      <div className="stack">
        <Board
          title={it.giornata.formationBoard}
          meta={`${view.formation} · ${riskLabel.toLowerCase()}`}
          flush
          lead
        >
          <div className="compose">
            {groups.map((group) => (
              <section key={group.label} aria-label={group.label}>
                <h3 className="rulehead">{group.label}</h3>
                <ul>
                  {group.players.map((player) => (
                    <li key={player.player_id} className="xi-row">
                      <span className="xi-row__slot" aria-hidden="true">
                        {roleLetter(player.slot)}
                      </span>
                      <OwnedPlayerPortrait
                        playerId={player.player_id}
                        name={player.display_name}
                        photoUrl={player.photo_url}
                        size="small"
                      />
                      <span className="xi-row__name">{player.display_name}</span>
                      <span className="xi-row__presence">
                        <Meter
                          value={player.appearance_probability}
                          label={`${it.giornata.presence} ${player.display_name}`}
                          ink
                        />
                      </span>
                      <span
                        className="xi-row__pts"
                        aria-label={`${it.giornata.points}: ${fmtPoints(player.expected_points)}`}
                      >
                        {fmtPoints(player.expected_points)}
                      </span>
                    </li>
                  ))}
                </ul>
              </section>
            ))}
          </div>
          <div className="board__foot">
            <button
              type="button"
              className="btn btn--quiet btn--small"
              onClick={onRecalc}
            >
              {it.giornata.recalc}
            </button>
          </div>
        </Board>
      </div>

      <div className="stack">
        <Board title={it.giornata.scoreBoard}>
          <div className="scoreline">
            <p
              className="scoreline__range"
              aria-label={`${it.giornata.scoreBoard}: ${fmtRange(view.p10_points, view.p90_points)} ${it.giornata.points}`}
            >
              {fmtRange(view.p10_points, view.p90_points)}
            </p>
            <RangeRule
              p10={view.p10_points}
              p90={view.p90_points}
              expected={view.expected_points}
            />
            <p className="scoreline__center">
              {it.giornata.scoreCenter}{" "}
              <strong className="num">{fmtPoints(view.expected_points)}</strong> ·{" "}
              {it.giornata.scoreRangeHint}
            </p>
            <dl className="deflist" style={{ width: "100%" }}>
              <div>
                <dt>{it.giornata.confidence}</dt>
                <dd>
                  <Meter value={view.confidence} label={it.giornata.confidence} />
                </dd>
              </div>
              <div>
                <dt>{it.giornata.substitutions}</dt>
                <dd className="num">{fmtNumber(view.expected_substitutions ?? 0, 1)}</dd>
              </div>
              {(view.expected_modifier ?? 0) !== 0 ? (
                <div>
                  <dt>{it.giornata.modifier}</dt>
                  <dd className="num">{fmtPoints(view.expected_modifier ?? 0)}</dd>
                </div>
              ) : null}
            </dl>
            <div className="freshness">
              <span>
                {it.giornata.freshnessData}{" "}
                {fmtDateTimeFull(view.data_cutoff, timezone)}
              </span>
              <span>
                {it.giornata.freshnessDecision}{" "}
                {fmtDateTimeFull(view.decision_cutoff, timezone)}
              </span>
            </div>
          </div>
          <Disclosure label={it.giornata.advanced}>
            <dl className="deflist">
              <div>
                <dt>Metodo di ricerca</dt>
                <dd>{view.optimization_method ?? it.app.notAvailable}</dd>
              </div>
              <div>
                <dt>Formazioni valutate</dt>
                <dd className="num">{view.evaluated_candidates ?? 1}</dd>
              </div>
              <div>
                <dt>Scenari esplorati</dt>
                <dd className="num">{view.search_scenarios ?? 0}</dd>
              </div>
            </dl>
            <p>{it.giornata.optimality}</p>
            <p className="num" style={{ overflowWrap: "anywhere" }}>
              ID {view.recommendation_id}
            </p>
          </Disclosure>
        </Board>

        {view.explanations.length > 0 ? (
          <Board title={it.giornata.whyBoard}>
            <ul style={{ display: "grid", gap: "var(--s-3)" }}>
              {view.explanations.slice(0, 3).map((explanation, index) => (
                <li
                  key={`${explanation.evidence_key}-${index}`}
                  style={{ display: "flex", gap: "var(--s-2)", alignItems: "baseline" }}
                >
                  <Mark kind="on" />
                  <span>{itDecimals(explanation.text)}</span>
                </li>
              ))}
            </ul>
          </Board>
        ) : null}

        <Board title={it.giornata.benchBoard} meta={it.giornata.benchOrderHint} flush>
          <ol className="rows">
            {view.bench.map((player, index) => (
              <li key={player.player_id} className="row row--zebra">
                <span className="row__rank num" aria-hidden="true">
                  {index + 1}
                </span>
                <OwnedPlayerPortrait
                  playerId={player.player_id}
                  name={player.display_name}
                  photoUrl={player.photo_url}
                  size="small"
                />
                <span className="row__main">
                  <span className="row__name">{player.display_name}</span>
                  <span className="row__meta">
                    {player.roles.map((role) => roleLetter(role)).join(" ")}
                  </span>
                </span>
                <span
                  className="row__num"
                  aria-label={`${it.giornata.utility}: ${fmtPoints(player.utility)}`}
                >
                  {fmtPoints(player.utility)}
                </span>
              </li>
            ))}
          </ol>
        </Board>

        {view.warnings && view.warnings.length > 0 ? (
          <Board title={it.giornata.warningsBoard}>
            <ul style={{ display: "grid", gap: "var(--s-2)" }}>
              {view.warnings.map((warning) => (
                <li key={warning} className="notice notice--warn">
                  <Mark kind="warn" />
                  <span>{warning}</span>
                </li>
              ))}
            </ul>
          </Board>
        ) : null}
      </div>
    </div>
  );
}

function MatchupSection() {
  const { leagueId, league } = useActiveLeague();
  const client = useQueryClient();
  const [opponentId, setOpponentId] = useState("");
  const [requestedOpponent, setRequestedOpponent] = useState<string | null>(null);
  const [cancelled, setCancelled] = useState(false);
  const requested = requestedOpponent === opponentId;
  const matchup = useMatchup(leagueId, opponentId, requested);


  const result = requested && matchup.isSuccess && !matchup.isFetching
    ? matchup.data
    : null;
  const opponents = (league?.fantasy_teams ?? []).filter(
    (team) => !team.is_user_team,
  );
  const timezone = league?.timezone ?? "Europe/Rome";

  function run() {
    if (opponentId === "") return;
    setCancelled(false);
    setRequestedOpponent(opponentId);
    if (requested) void matchup.refetch();
  }

  if (opponents.length === 0) {
    return (
      <Board title={it.giornata.matchupBoard}>
        <EmptyState title={it.giornata.matchupNoOpponents}>
          <Link to="/rosa/importa/avversaria" className="btn btn--secondary">
            {it.lega.addOpponent}
          </Link>
        </EmptyState>
      </Board>
    );
  }

  return (
    <Board title={it.giornata.matchupBoard} busy={matchup.isFetching}>
      <div style={{ display: "grid", gap: "var(--s-4)" }}>
        <div
          style={{
            display: "flex",
            gap: "var(--s-3)",
            flexWrap: "wrap",
            alignItems: "end",
          }}
        >
          <div className="field" style={{ minWidth: "14rem" }}>
            <label className="field__label" htmlFor="avversario">
              {it.giornata.matchupOpponent}
            </label>
            <select
              id="avversario"
              className="select"
              value={opponentId}
              onChange={(event) => {
                setOpponentId(event.target.value);
                setRequestedOpponent(null);
                setCancelled(false);
              }}
            >
              <option value="">{it.app.notAvailable}</option>
              {opponents.map((team) => (
                <option key={team.id} value={team.id}>
                  {team.name}
                </option>
              ))}
            </select>
          </div>
          <button
            type="button"
            className="btn btn--primary"
            disabled={opponentId === "" || matchup.isFetching}
            onClick={() => {
              void run();
            }}
          >
            {matchup.isFetching ? it.giornata.matchupRunning : it.giornata.matchupRun}
          </button>
        </div>

        {matchup.isFetching ? (
          <LongWait
            title={it.giornata.computing}
            body={it.giornata.computingBody}
            onCancel={() => {
              setRequestedOpponent(null);
              setCancelled(true);
              void client.cancelQueries({ queryKey: keys.matchup(leagueId, opponentId) });
            }}
          />
        ) : null}

        {cancelled ? <Notice>{it.app.requestCancelled}</Notice> : null}

        {requested && matchup.isError ? (
          <MatchupError error={matchup.error} />
        ) : null}

        {result !== null ? (
          <div style={{ display: "grid", gap: "var(--s-4)" }}>
            <dl className="matchup-triple">
              <div>
                <dt>{it.giornata.win}</dt>
                <dd>{fmtPct(result.win_probability)}</dd>
              </div>
              <div>
                <dt>{it.giornata.draw}</dt>
                <dd>{fmtPct(result.draw_probability)}</dd>
              </div>
              <div>
                <dt>{it.giornata.loss}</dt>
                <dd>{fmtPct(result.loss_probability)}</dd>
              </div>
            </dl>
            <p className="field__hint">
              {it.giornata.matchupFormation}: {result.lineup.formation} ·{" "}
              {it.giornata.scoreCenter}{" "}
              <strong className="num">
                {fmtPoints(result.lineup.expected_points)}
              </strong>{" "}
              ({fmtRange(result.lineup.p10_points, result.lineup.p90_points)})
            </p>
            <p className="freshness">
              {it.giornata.freshnessData}{" "}
              {fmtDateTimeFull(result.lineup.data_cutoff, timezone)} ·{" "}
              {it.giornata.freshnessDecision}{" "}
              {fmtDateTimeFull(result.lineup.decision_cutoff, timezone)} ·{" "}
              {result.simulation_count.toLocaleString("it-IT")} simulazioni
            </p>
            <Disclosure label={it.giornata.matchupFormation}>
              <div className="compose">
                {groupStarters(result.lineup.starters, league?.mode ?? "classic").map((group) => (
                  <section key={group.label} aria-label={group.label}>
                    <h3 className="rulehead">{group.label}</h3>
                    <ul>
                      {group.players.map((player) => (
                        <li key={player.player_id} className="xi-row">
                          <span className="xi-row__slot">{roleLetter(player.slot)}</span>
                          <OwnedPlayerPortrait
                            playerId={player.player_id}
                            name={player.display_name}
                            photoUrl={player.photo_url}
                            size="small"
                          />
                          <span className="xi-row__name">{player.display_name}</span>
                          <span className="xi-row__presence">
                            <Meter value={player.appearance_probability} label={`${it.giornata.presence} ${player.display_name}`} ink />
                          </span>
                          <span className="xi-row__pts">{fmtPoints(player.expected_points)}</span>
                        </li>
                      ))}
                    </ul>
                  </section>
                ))}
              </div>
              <h3 className="rulehead">{it.giornata.benchBoard}</h3>
              <ol className="rows">
                {result.lineup.bench.map((player, index) => (
                  <li key={player.player_id} className="row row--zebra">
                    <span className="row__rank num" aria-hidden="true">{index + 1}</span>
                    <OwnedPlayerPortrait
                      playerId={player.player_id}
                      name={player.display_name}
                      photoUrl={player.photo_url}
                      size="small"
                    />
                    <span className="row__main">
                      <span className="row__name">{player.display_name}</span>
                      <span className="row__meta">{player.roles.map(roleLetter).join(" ")}</span>
                    </span>
                  </li>
                ))}
              </ol>
              {result.lineup.explanations.map((explanation, index) => (
                <p key={`${explanation.evidence_key}-${index}`}>{explanation.text}</p>
              ))}
              {result.lineup.warnings?.map((warning) => <Notice key={warning} tone="warn">{warning}</Notice>)}
            </Disclosure>
          </div>
        ) : null}
      </div>
    </Board>
  );
}

function MatchupError({ error }: { error: unknown }) {
  if (error instanceof ApiError && (error.status === 409 || error.status === 404)) {
    const guidance = conflictGuidance(error);
    return (
      <Notice tone="warn">
        <strong>{guidance.title}.</strong> {guidance.body}{" "}
        {guidance.cta && guidance.to ? (
          <Link to={guidance.to}>{guidance.cta}</Link>
        ) : null}
      </Notice>
    );
  }
  return <Notice tone="bad">{errorMessage(error)}</Notice>;
}
