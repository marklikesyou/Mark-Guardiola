import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import {
  keys,
  useOutlook,
  usePlayer,
  usePlayerPredictions,
  useRecentForm,
  useSystemStatus,
} from "../../api/queries";
import type {
  PlayerFixtureOutlook,
  PlayerFixturePrediction,
  PlayerFormMatch,
  PlayerOutlookView,
  PlayerRecentFormView,
  PredictionValue,
} from "../../api/types";
import { useActiveLeague } from "../../app/LeagueContext";
import { OwnedPlayerPortrait } from "../../app/PlayerPhotoPolicy";
import { ApiError, conflictGuidance, errorMessage } from "../../lib/apiErrors";
import {
  clamp01,
  fmtDate,
  fmtDateTimeFull,
  fmtKickoff,
  fmtNumber,
  fmtPct,
  fmtPoints,
  fmtRange,
  itDecimals,
  kickoffTimeZone,
} from "../../lib/format";
import { positionGroup, positionLabel } from "../../lib/roles";
import { it } from "../../lib/strings";
import {
  Board,
  Disclosure,
  EmptyState,
  Mark,
  Meter,
  Segmented,
  Skeleton,
} from "../../ui/primitives";

const keyboardScrollable = { tabIndex: 0 } as const;

const TARGET_LABELS: Record<string, string> = {
  appearance_probability: it.giocatori.presence,
  start_probability: it.giocatori.starter,
  expected_minutes: it.giocatori.minutes,
  goal_probability: it.giocatori.goal,
  expected_goals: it.giocatori.goals,
  assist_probability: it.giocatori.assist,
  expected_assists: it.giocatori.assists,
  clean_sheet_probability: it.giocatori.cleanSheet,
  goalkeeper_saves: it.giocatori.saves,
  goalkeeper_goals_conceded: it.giocatori.conceded,
  penalty_involvement: it.giocatori.penaltyInvolvement,
  yellow_card_probability: `${it.giocatori.cards}: ${it.giocatori.yellow.toLowerCase()}`,
  red_card_probability: `${it.giocatori.cards}: ${it.giocatori.red.toLowerCase()}`,
  team_goals: it.giocatori.teamGoals,
  team_goals_conceded: it.giocatori.teamConceded,
};

type Horizon = 1 | 3 | 5 | 10;
const HORIZONS: Array<{ value: Horizon; label: string }> = [
  { value: 1, label: "1" },
  { value: 3, label: "3" },
  { value: 5, label: "5" },
  { value: 10, label: "10" },
];


function FixtureRange({
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
    <div className="rangerule" style={{ width: "min(100%, 11rem)" }} aria-hidden="true">
      <i className="rangerule__end" />
      <i className="rangerule__mark" style={{ left: `${position * 100}%` }} />
      <i className="rangerule__end rangerule__end--right" />
    </div>
  );
}

function OutlookFixture({
  fixture,
  keeper,
  timezone,
}: {
  fixture: PlayerFixtureOutlook;
  keeper: boolean;
  timezone: string;
}) {
  const match = fixture.match;
  const heading = `${match.home_team.name} contro ${match.away_team.name}`;
  const football = fixture.football;
  return (
    <section aria-label={heading}>
      <h3 className="rulehead">
        {heading} · {fmtKickoff(match.kickoff_at, match.kickoff_precision, timezone)}
        {match.matchweek !== null ? ` · ${it.giocatori.matchweek(match.matchweek)}` : ""}
      </h3>
      <div style={{ padding: "var(--s-2) var(--s-4) var(--s-3)", display: "grid", gap: "var(--s-3)" }}>
        <div style={{ display: "flex", alignItems: "baseline", gap: "var(--s-3)", flexWrap: "wrap" }}>
          <span
            className="num"
            style={{
              fontStretch: "var(--stretch-display)",
              fontWeight: 800,
              fontSize: "1.5rem",
            }}
            aria-label={`${it.giornata.points}: ${fmtPoints(fixture.expected_points)}`}
          >
            {fmtPoints(fixture.expected_points)}
          </span>
          <span className="field__hint num">
            {it.outlook.fixtureRange} {fmtRange(fixture.p10_points, fixture.p90_points)} ·{" "}
            {it.outlook.median} {fmtPoints(fixture.median_points)}
          </span>
          <Meter value={fixture.confidence} label={it.giornata.confidence} ink />
        </div>
        <FixtureRange
          p10={fixture.p10_points}
          p90={fixture.p90_points}
          expected={fixture.expected_points}
        />
        <dl className="statgrid">
          <div className="stat">
            <dt title={it.outlook.scoringAppearanceHint}>{it.outlook.scoringAppearance}</dt>
            <dd>{fmtPct(fixture.scoring_appearance_probability)}</dd>
          </div>
          <div className="stat">
            <dt>{it.outlook.starter}</dt>
            <dd>{fmtPct(football.start_probability)}</dd>
          </div>
          <div className="stat">
            <dt>{it.outlook.presence}</dt>
            <dd>{fmtPct(football.appearance_probability)}</dd>
          </div>
          <div className="stat">
            <dt>{it.outlook.minutes}</dt>
            <dd>
              {fmtNumber(football.mean_minutes, 0)}′
              <small>
                {it.giocatori.range}{" "}
                {fmtRange(football.p10_minutes, football.p90_minutes)}
              </small>
            </dd>
          </div>
          {!keeper ? (
            <>
              <div className="stat">
                <dt>{it.giocatori.goal}</dt>
                <dd>{fmtPct(football.goal_probability)}</dd>
              </div>
              <div className="stat">
                <dt>{it.giocatori.assist}</dt>
                <dd>{fmtPct(football.assist_probability)}</dd>
              </div>
            </>
          ) : (
            <>
              <div className="stat">
                <dt>{it.giocatori.saves}</dt>
                <dd>{fmtNumber(football.mean_saves, 1)}</dd>
              </div>
              <div className="stat">
                <dt>{it.giocatori.conceded}</dt>
                <dd>{fmtNumber(football.mean_goals_conceded, 1)}</dd>
              </div>
            </>
          )}
          <div className="stat">
            <dt title={it.outlook.cleanSheetHint}>{it.giocatori.cleanSheet}</dt>
            <dd>{fmtPct(football.clean_sheet_probability)}</dd>
          </div>
        </dl>
        {fixture.explanations.length > 0 ? (
          <ul style={{ display: "grid", gap: "var(--s-1)" }}>
            {fixture.explanations.slice(0, 3).map((explanation, index) => (
              <li
                key={`${explanation.evidence_key}-${index}`}
                style={{ display: "flex", gap: "var(--s-2)", alignItems: "baseline" }}
                className="field__hint"
              >
                <Mark kind="on" />
                <span>{itDecimals(explanation.text)}</span>
              </li>
            ))}
          </ul>
        ) : null}
      </div>
    </section>
  );
}

function OutlookBoard({
  leagueId,
  playerId,
  keeper,
  timezone,
}: {
  leagueId: string;
  playerId: string;
  keeper: boolean;
  timezone: string;
}) {
  const [horizon, setHorizon] = useState<Horizon>(1);
  const [cancelled, setCancelled] = useState(false);
  const client = useQueryClient();
  const outlook = useOutlook(leagueId, playerId, horizon);

  async function cancelComputation() {
    await client.cancelQueries({ queryKey: keys.outlook(leagueId, playerId, horizon) });
    setCancelled(true);
  }

  function retry() {
    setCancelled(false);
    void outlook.refetch();
  }

  const horizonControl = (
    <div style={{ display: "inline-flex", gap: "var(--s-2)", alignItems: "center" }}>
      <span className="field__hint">{it.outlook.horizon}</span>
      <Segmented
        legend={it.outlook.horizon}
        options={HORIZONS.map((option) => ({
          value: option.value,
          label: option.label,
          title: it.mercato.horizonHint(option.value),
        }))}
        value={horizon}
        onChange={(next) => {
          setCancelled(false);
          setHorizon(next);
        }}
        disabled={outlook.isFetching}
      />
    </div>
  );

  return (
    <Board
      title={it.outlook.board}
      meta={horizonControl}
      flush
      lead
      busy={outlook.isFetching}
    >
      {cancelled ? (
        <EmptyState title={it.app.requestCancelled}>
          <button type="button" className="btn btn--primary" onClick={retry}>
            {it.app.retry}
          </button>
        </EmptyState>
      ) : outlook.isPending || outlook.isFetching ? (
        <div style={{ padding: "var(--s-4)", display: "grid", gap: "var(--s-3)" }}>
          <p className="field__hint" role="status">
            {it.outlook.computing}… {it.outlook.computingBody}
          </p>
          <Skeleton lines={5} />
          <div>
            <button
              type="button"
              className="btn btn--secondary btn--small"
              onClick={() => {
                void cancelComputation();
              }}
            >
              {it.app.cancel}
            </button>
          </div>
        </div>
      ) : outlook.isError ? (
        <OutlookError error={outlook.error} onRetry={retry} />
      ) : (
        <OutlookResult view={outlook.data} keeper={keeper} timezone={timezone} />
      )}
    </Board>
  );
}

function OutlookError({ error, onRetry }: { error: unknown; onRetry: () => void }) {
  if (error instanceof ApiError && (error.status === 409 || error.status === 404)) {
    const guidance = conflictGuidance(error);
    return (
      <EmptyState title={it.outlook.unavailableTitle} body={guidance.body}>
        {guidance.cta && guidance.to ? (
          <Link to={guidance.to} className="btn btn--primary">
            {guidance.cta}
          </Link>
        ) : null}
        <button type="button" className="btn btn--secondary" onClick={onRetry}>
          {it.app.retry}
        </button>
      </EmptyState>
    );
  }
  return (
    <EmptyState title={it.app.error} body={errorMessage(error)}>
      <button type="button" className="btn btn--primary" onClick={onRetry}>
        {it.app.retry}
      </button>
    </EmptyState>
  );
}


function ProvenanceTime({ value, timezone }: { value: string; timezone: string }) {
  return (
    <time dateTime={value} className="prov__id">
      <span>{fmtDateTimeFull(value, timezone)}</span>{" "}
      (<span>{value}</span>)
    </time>
  );
}

function OutlookResult({
  view,
  keeper,
  timezone,
}: {
  view: PlayerOutlookView;
  keeper: boolean;
  timezone: string;
}) {
  return (
    <div className="compose">
      <div style={{ padding: "var(--s-4)", display: "grid", gap: "var(--s-2)" }}>
        <p
          className="scoreline__range"
          style={{ fontSize: "2.25rem" }}
          aria-label={`${it.outlook.scoreLabel}: ${fmtPoints(view.recommendation_score.value)}`}
        >
          {fmtPoints(view.recommendation_score.value)}
        </p>
        <p className="field__label">{it.outlook.scoreLabel}</p>
        <p className="field__hint" style={{ maxWidth: "36rem" }}>
          {it.outlook.scoreHint}
        </p>
      </div>

      {(view.warnings ?? []).length > 0 ? (
        <ul style={{ display: "grid", gap: "var(--s-2)", padding: "0 var(--s-4) var(--s-3)" }}>
          {(view.warnings ?? []).map((warning) => (
            <li key={warning} className="notice notice--warn">
              <Mark kind="warn" />
              <span>{warning}</span>
            </li>
          ))}
        </ul>
      ) : null}

      {view.fixtures.map((fixture) => (
        <OutlookFixture
          key={fixture.match.id}
          fixture={fixture}
          keeper={keeper}
          timezone={timezone}
        />
      ))}

      <Disclosure label={it.outlook.advanced}>
        <dl className="deflist">
          <div>
            <dt>{it.outlook.rulesVersion}</dt>
            <dd className="num">{it.lega.rulesVersion(view.rules_version)}</dd>
          </div>
          <div>
            <dt>{it.outlook.roles}</dt>
            <dd>{view.roles.join(" ") || it.app.notAvailable}</dd>
          </div>
          <div>
            <dt>{it.outlook.scoringRole}</dt>
            <dd>{view.scoring_role ?? it.app.notAvailable}</dd>
          </div>
          <div>
            <dt>{it.outlook.simulations}</dt>
            <dd className="num">{view.simulation_count.toLocaleString("it-IT")}</dd>
          </div>
          <div>
            <dt>{it.outlook.seed}</dt>
            <dd className="num">{view.seed}</dd>
          </div>
          <div>
            <dt>{it.outlook.statCutoff}</dt>
            <dd className="num"><ProvenanceTime value={view.data_cutoff} timezone={timezone} /></dd>
          </div>
          <div>
            <dt>{it.outlook.predictionCutoff}</dt>
            <dd className="num">
              <ProvenanceTime value={view.prediction_cutoff} timezone={timezone} />
            </dd>
          </div>
          <div>
            <dt>{it.outlook.decisionCutoff}</dt>
            <dd className="num"><ProvenanceTime value={view.decision_cutoff} timezone={timezone} /></dd>
          </div>
          <div>
            <dt>{it.outlook.timezoneLabel}</dt>
            <dd>{timezone}</dd>
          </div>
          <div>
            <dt>{it.outlook.run}</dt>
            <dd className="num prov__id">{view.prediction_run_id}</dd>
          </div>
        </dl>
        <p>
          {it.outlook.scoringAppearance}: {it.outlook.scoringAppearanceHint}
        </p>
        <p>
          {it.giocatori.cleanSheet}: {it.outlook.cleanSheetHint}
        </p>
        <p className="field__hint">{it.outlook.models}</p>
        <dl className="deflist">
          {Object.entries(view.model_versions).map(([target, version]) => (
            <div key={target}>
              <dt>{TARGET_LABELS[target] ?? target}</dt>
              <dd className="num prov__id">{version}</dd>
            </div>
          ))}
        </dl>
      </Disclosure>
    </div>
  );
}







function MinutesChart({
  items,
  timezone,
}: {
  items: PlayerFormMatch[];
  timezone: string;
}) {
  const chronological = [...items].reverse();
  const scaleMax = Math.max(90, ...chronological.map((match) => match.minutes));
  const referenceBottom = (90 / scaleMax) * 100;
  return (
    <figure className="minchart" aria-hidden="true">
      <figcaption className="minchart__title">
        {it.forma.chartTitle} · {it.forma.chartDirection}
      </figcaption>
      <div className="minchart__plot">
        <i
          className="minchart__ref"
          style={{ bottom: `${referenceBottom}%` }}
        />
        <span
          className="minchart__reflabel"
          style={{ bottom: `${referenceBottom}%` }}
        >
          {it.forma.chartRef}
        </span>
        {chronological.map((match) => {
          const percent = (match.minutes / scaleMax) * 100;
          return (
            <div key={match.match_id} className="minchart__col">
              {                                                                   }
              <span
                className="minchart__value num"
                style={{ bottom: `calc(${percent}% + 2px)` }}
              >
                {match.minutes}′
              </span>
              <i className="minchart__bar" style={{ height: `${percent}%` }} />
              <span className="minchart__date num">
                {new Intl.DateTimeFormat("it-IT", {
                  day: "numeric",
                  month: "numeric",
                  timeZone: kickoffTimeZone(match.kickoff_precision, timezone),
                }).format(new Date(match.kickoff_at))}
              </span>
            </div>
          );
        })}
      </div>
    </figure>
  );
}


function FormRow({ match, timezone }: { match: PlayerFormMatch; timezone: string }) {
  const facts: string[] = [`${match.minutes}${it.forma.minutes}`];
  if (match.goals !== null && match.goals > 0) {
    facts.push(`${match.goals} ${it.forma.goals}`);
  }
  if (match.assists !== null && match.assists > 0) {
    facts.push(`${match.assists} ${it.forma.assists}`);
  }
  if (match.shots !== null && match.shots > 0) {
    facts.push(`${match.shots} ${it.forma.shots}`);
  }
  if (match.xg !== null) facts.push(`xG ${fmtNumber(match.xg, 2)}`);

  return (
    <li className="row row--zebra" style={{ alignItems: "flex-start" }}>
      <span style={{ paddingTop: "3px" }}>
        <Mark
          kind={match.started ? "on" : "off"}
          label={match.started ? it.forma.started : it.forma.benched}
        />
      </span>
      <span className="row__main" style={{ display: "grid", gap: "2px" }}>
        <span className="row__name">
          {match.is_home
            ? `${match.team.name} contro ${match.opponent.name}`
            : `${match.opponent.name} contro ${match.team.name}`}
        </span>
        <span className="row__meta num">
          {fmtKickoff(match.kickoff_at, match.kickoff_precision, timezone)}
          {match.matchweek !== null ? ` · ${it.giocatori.matchweek(match.matchweek)}` : ""}
          {" · "}
          {match.is_home ? it.forma.home : it.forma.away}
          {" · "}
          {facts.join(" · ")}
        </span>
      </span>
      <span
        className="row__num"
        aria-label={
          match.base_rating !== null
            ? `${it.forma.rating}: ${fmtNumber(match.base_rating, 1)}`
            : it.forma.noRating
        }
      >
        {match.base_rating !== null ? fmtNumber(match.base_rating, 1) : it.app.notAvailable}
      </span>
    </li>
  );
}

function FormBoard({ playerId, timezone }: { playerId: string; timezone: string }) {
  const form = useRecentForm(playerId, 5);

  return (
    <Board
      title={it.forma.board}
      meta={it.forma.intro}
      flush
      busy={form.isFetching}
    >
      {form.isPending ? (
        <div style={{ padding: "var(--s-4)" }}>
          <Skeleton lines={5} />
        </div>
      ) : form.isError ? (
        <EmptyState title={it.app.error} body={errorMessage(form.error)}>
          <button
            type="button"
            className="btn btn--primary"
            onClick={() => {
              void form.refetch();
            }}
          >
            {it.app.retry}
          </button>
        </EmptyState>
      ) : (
        <FormContent view={form.data} timezone={timezone} />
      )}
    </Board>
  );
}

function FormContent({
  view,
  timezone,
}: {
  view: PlayerRecentFormView;
  timezone: string;
}) {
  return (
    <>
      {(view.warnings ?? []).length > 0 ? (
        <ul style={{ display: "grid", gap: "var(--s-2)", padding: "var(--s-3) var(--s-4) 0" }}>
          {(view.warnings ?? []).map((warning) => (
            <li key={warning} className="notice notice--warn">
              <Mark kind="warn" />
              <span>{warning}</span>
            </li>
          ))}
        </ul>
      ) : null}
      {view.items.length === 0 ? (
        <EmptyState title={it.forma.empty} />
      ) : (
        <>
          <MinutesChart items={view.items} timezone={timezone} />
          <p className="forma-colhead">
            <span>{it.forma.listDirection}</span>
            <span aria-hidden="true">{it.forma.rating}</span>
          </p>
          <ul>
            {view.items.map((match) => (
              <FormRow key={match.match_id} match={match} timezone={timezone} />
            ))}
          </ul>
          <Disclosure label={it.forma.provenance}>
            <p className="num">
              {it.forma.asOf}: <ProvenanceTime value={view.as_of} timezone={timezone} />
            </p>
            {view.data_cutoff ? (
              <p className="num">
                {it.forma.dataCutoff}: <ProvenanceTime value={view.data_cutoff} timezone={timezone} />{" "}
                ({timezone})
              </p>
            ) : null}
            <div style={{ display: "grid", gap: "var(--s-3)" }}>
              {view.items.map((match) => (
                <MatchProvenance
                  key={match.match_id}
                  match={match}
                  timezone={timezone}
                />
              ))}
            </div>
          </Disclosure>
        </>
      )}
    </>
  );
}







function MatchProvenance({
  match,
  timezone,
}: {
  match: PlayerFormMatch;
  timezone: string;
}) {
  const fieldsByStat = new Map<string, string[]>();
  for (const [field, statId] of Object.entries(match.field_sources)) {
    const bucket = fieldsByStat.get(statId) ?? [];
    bucket.push(it.forma.fieldNames[field] ?? field);
    fieldsByStat.set(statId, bucket);
  }
  const orphanStatIds = [...fieldsByStat.keys()].filter(
    (statId) => !match.sources.some((source) => source.stat_id === statId),
  );

  return (
    <div>
      <p className="field__label">
        {match.opponent.name} · {fmtDate(match.kickoff_at, kickoffTimeZone(match.kickoff_precision, timezone))}
      </p>
      {match.kickoff_precision !== "minute" ? (
        <p className="field__hint">{it.forma.dateOnlyEvent}</p>
      ) : null}
      {match.sources.length === 0 && fieldsByStat.size === 0 ? (
        <p className="field__hint">{it.app.notAvailable}</p>
      ) : null}
      <div style={{ display: "grid", gap: "var(--s-2)" }}>
        {match.sources.map((source) => {
          const covered = fieldsByStat.get(source.stat_id) ?? [];
          return (
            <div key={source.stat_id} className="prov">
              <p className="field__hint" style={{ overflowWrap: "anywhere" }}>
                <strong>{source.source_name}</strong> ({source.source_key}) ·{" "}
                {it.forma.sourcePriority}{" "}
                <span className="num">{source.source_priority}</span>
                {covered.length > 0 ? (
                  <>
                    {" "}
                    · {it.forma.coveredFields}: {covered.join(", ")}
                  </>
                ) : null}
              </p>
              <p className="field__hint num" style={{ overflowWrap: "anywhere" }}>
                {it.forma.observedAt} <ProvenanceTime value={source.event_time} timezone={timezone} /> ·{" "}
                {it.forma.availableAt} <ProvenanceTime value={source.available_at} timezone={timezone} /> ·{" "}
                {it.forma.ingestedAt} <ProvenanceTime value={source.ingested_at} timezone={timezone} />
              </p>
              <Disclosure label={it.forma.fullIds}>
                <dl className="deflist">
                  <div>
                    <dt>{it.forma.statId}</dt>
                    <dd className="num prov__id">{source.stat_id}</dd>
                  </div>
                  <div>
                    <dt>{it.forma.sourceId}</dt>
                    <dd className="num prov__id">{source.source_id}</dd>
                  </div>
                  <div>
                    <dt>{it.forma.recordId}</dt>
                    <dd className="num prov__id">{source.source_record_id}</dd>
                  </div>
                  <div>
                    <dt>{it.forma.ingestionRun}</dt>
                    <dd className="num prov__id">{source.ingestion_run_id}</dd>
                  </div>
                  <div>
                    <dt>{it.forma.schemaVersion}</dt>
                    <dd className="num prov__id">
                      {source.schema_version_id ?? it.app.notAvailable}
                    </dd>
                  </div>
                  <div>
                    <dt>{it.forma.adapter}</dt>
                    <dd className="num prov__id">{source.adapter_version}</dd>
                  </div>
                </dl>
                {Object.keys(source.field_provenance).length > 0 ? (
                  <>
                    <p className="field__hint">{it.forma.fieldProvenance}</p>
                    {                                                                                     }
                    {                                                                  }
                    <pre {...keyboardScrollable} className="provjson" role="region" aria-label={`${it.forma.fieldProvenance}: ${source.source_name}, ${fmtDate(match.kickoff_at, kickoffTimeZone(match.kickoff_precision, timezone))}`}>
                      {JSON.stringify(source.field_provenance, null, 2)}
                    </pre>
                  </>
                ) : null}
              </Disclosure>
            </div>
          );
        })}
        {orphanStatIds.map((statId) => (
          <p
            key={statId}
            className="field__hint num"
            style={{ overflowWrap: "anywhere" }}
          >
            {(fieldsByStat.get(statId) ?? []).join(", ")}: {it.forma.missingSource}{" "}
            ({statId})
          </p>
        ))}
      </div>
    </div>
  );
}

function RawPredictions({
  predictions,
  timezone,
}: {
  predictions: PlayerFixturePrediction[];
  timezone: string;
}) {
  return (
    <div style={{ display: "grid", gridTemplateColumns: "minmax(0, 1fr)", gap: "var(--s-3)" }}>
      <p className="field__hint">{it.outlook.rawIntro}</p>
      {predictions.map((prediction) => {
        const match = prediction.match;
        return (
          <div key={match.id}>
            <p className="field__label">
              {match.home_team.name} contro {match.away_team.name},{" "}
              {fmtKickoff(match.kickoff_at, match.kickoff_precision, timezone)}
            </p>
            <AdvancedTable values={prediction.values} />
            <p className="field__hint num" style={{ overflowWrap: "anywhere" }}>
              {it.giornata.freshnessData}{" "}
              <ProvenanceTime value={prediction.data_cutoff} timezone={timezone} /> ·{" "}
              {it.outlook.predictionCutoff}{" "}
              <ProvenanceTime value={prediction.prediction_cutoff} timezone={timezone} /> ·{" "}
              {it.giocatori.predictionRun} {prediction.prediction_run_id}
            </p>
          </div>
        );
      })}
    </div>
  );
}

function AdvancedTable({ values }: { values: PredictionValue[] }) {
  return (


    <div {...keyboardScrollable} className="tablewrap" role="region" aria-label={it.giocatori.advancedTable}>
      <table className="table">
        <thead>
          <tr>
            <th scope="col">{it.giocatori.target}</th>
            <th scope="col" className="num">
              {it.giocatori.expected}
            </th>
            <th scope="col" className="num">
              {it.giocatori.median}
            </th>
            <th scope="col" className="num">
              {it.giocatori.range}
            </th>
            <th scope="col" className="num">
              {it.giocatori.probability}
            </th>
            <th scope="col" className="num">
              {it.giocatori.reliability}
            </th>
            <th scope="col">{it.giocatori.model}</th>
          </tr>
        </thead>
        <tbody>
          {values.map((entry) => (
            <tr key={entry.target}>
              <td>{TARGET_LABELS[entry.target] ?? entry.target}</td>
              <td className="num">{fmtNumber(entry.expected_value, 3)}</td>
              <td className="num">{fmtNumber(entry.median, 3)}</td>
              <td className="num">{fmtRange(entry.p10, entry.p90)}</td>
              <td className="num">
                {entry.probability !== null ? fmtPct(entry.probability) : it.app.notAvailable}
              </td>
              <td className="num">{fmtPct(entry.reliability)}</td>
              <td className="num prov__id">{entry.model_version}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function GiocatoreDetailPage() {
  const { playerId } = useParams();
  const { leagueId, league } = useActiveLeague();
  const player = usePlayer(playerId ?? "");
  const predictions = usePlayerPredictions(playerId ?? "");
  const system = useSystemStatus();
  const timezone = league?.timezone ?? "Europe/Rome";

  if (player.isPending) {
    return (
      <div className="page">
        <Skeleton lines={6} />
      </div>
    );
  }

  if (player.isError) {
    return (
      <div className="page">
        <EmptyState title={it.app.error} body={errorMessage(player.error)}>
          <Link to="/giocatori" className="btn btn--secondary">
            {it.giocatori.backToList}
          </Link>
        </EmptyState>
      </div>
    );
  }

  const detail = player.data;
  const keeper = positionGroup(detail.primary_position) === "GK";
  const position = positionLabel(detail.primary_position);
  const dataNeverRefreshed =
    system.data?.freshness.latest_prediction_cutoff == null;

  return (
    <div className="page">
      <p>
        <Link to="/giocatori">{it.giocatori.backToList}</Link>
      </p>
      <div className="player-heading">
        <OwnedPlayerPortrait
          playerId={detail.id}
          name={detail.display_name}
          photoUrl={detail.photo_url}
          size="large"
          decorative={false}
          eager
        />
        <div className="player-heading__copy">
          <h1 className="page__title">{detail.display_name}</h1>
          <p className="page__meta">
            {[position, detail.current_team?.name ?? null, league?.name ?? null]
              .filter(Boolean)
              .join(" · ")}
          </p>
        </div>
      </div>

      <div className="cols cols--lead">
        <div className="stack">
          <OutlookBoard
            leagueId={leagueId}
            playerId={detail.id}
            keeper={keeper}
            timezone={timezone}
          />
          <FormBoard playerId={detail.id} timezone={timezone} />
        </div>

        <div className="stack">
          <Board title={it.giocatori.cardBoard}>
            <dl className="deflist">
              {position ? (
                <div>
                  <dt>{it.giocatori.position}</dt>
                  <dd>{position}</dd>
                </div>
              ) : null}
              {detail.current_team ? (
                <div>
                  <dt>{it.giocatori.team}</dt>
                  <dd>{detail.current_team.name}</dd>
                </div>
              ) : null}
              {detail.date_of_birth ? (
                <div>
                  <dt>{it.giocatori.born}</dt>
                  <dd>{fmtDate(detail.date_of_birth)}</dd>
                </div>
              ) : null}
              {detail.nationality_code ? (
                <div>
                  <dt>{it.giocatori.nationality}</dt>
                  <dd>{detail.nationality_code}</dd>
                </div>
              ) : null}
              {detail.preferred_foot ? (
                <div>
                  <dt>{it.giocatori.foot}</dt>
                  <dd>{detail.preferred_foot}</dd>
                </div>
              ) : null}
              {detail.height_cm !== null ? (
                <div>
                  <dt>{it.giocatori.height}</dt>
                  <dd className="num">{detail.height_cm} cm</dd>
                </div>
              ) : null}
              <div>
                <dt>{it.giocatori.active}</dt>
                <dd>{detail.active ? it.lega.yes : it.lega.no}</dd>
              </div>
            </dl>
          </Board>

          <Board title={it.outlook.rawBoard} flush>
            {predictions.isPending ? (
              <div style={{ padding: "var(--s-4)" }}>
                <Skeleton lines={3} />
              </div>
            ) : predictions.isError ? (
              <div style={{ padding: "var(--s-4)" }}>
                <p className="field__hint">{errorMessage(predictions.error)}</p>
              </div>
            ) : predictions.data.length === 0 ? (
              <EmptyState
                title={it.giocatori.noPredictionsTitle}
                body={
                  dataNeverRefreshed
                    ? it.giocatori.noPredictionsBodyStale
                    : it.giocatori.noPredictionsBodyFresh
                }
              />
            ) : (
              <Disclosure label={it.giocatori.advancedTable}>
                <RawPredictions predictions={predictions.data} timezone={timezone} />
              </Disclosure>
            )}
          </Board>
        </div>
      </div>
    </div>
  );
}
