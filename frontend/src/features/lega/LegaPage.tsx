import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { Link, useLocation } from "react-router-dom";
import { api } from "../../api/client";
import {
  invalidateDecisions,
  keys,
  useJob,
  useRosters,
  useSystemStatus,
  useUpdateBudget,
  useUpdateLeagueSettings,
} from "../../api/queries";
import type { JobView, LeagueView } from "../../api/types";
import { useActiveLeague } from "../../app/LeagueContext";
import { errorMessage } from "../../lib/apiErrors";
import {
  fmtCredits,
  fmtDateTimeFull,
  fmtPct,
  parseDecimalInput,
} from "../../lib/format";
import { it } from "../../lib/strings";
import { translateSystemWarning } from "../../lib/warnings";
import {
  Board,
  ConfirmDialog,
  Disclosure,
  InlineEdit,
  Mark,
  Notice,
  Skeleton,
} from "../../ui/primitives";
import { RulesEditor } from "./RulesEditor";
import { RulesSummary } from "./RulesSummary";

export function LegaPage() {
  const { league } = useActiveLeague();
  const location = useLocation();


  useEffect(() => {
    if (location.hash === "#sistema") {
      document.getElementById("sistema")?.scrollIntoView();
    }
  }, [location.hash]);

  if (league === null) {
    return (
      <div className="page">
        <Skeleton lines={8} />
      </div>
    );
  }

  return (
    <div className="page">
      <div className="page__head">
        <h1 className="page__title">{it.lega.title}</h1>
        <p className="page__meta">{league.name}</p>
      </div>
      <div className="cols cols--lead">
        <div className="stack">
          <InfoBoard league={league} />
          <TeamsBoard league={league} />
          <RulesBoard league={league} />
        </div>
        <div className="stack">
          <SystemBoard />
          <JobsBoard />
        </div>
      </div>
    </div>
  );
}

function InfoBoard({ league }: { league: LeagueView }) {
  const updateSettings = useUpdateLeagueSettings(league.id);
  const [h2hError, setH2hError] = useState<string | null>(null);

  return (
    <Board title={it.lega.infoBoard}>
      <dl className="deflist">
        <div>
          <dt>{it.lega.nameLabel}</dt>
          <dd>
            <InlineEdit
              label={it.app.edit}
              display={league.name}
              initial={league.name}
              savedText={it.lega.renameSaved}
              validate={(text) => (text.trim() === "" ? null : text.trim())}
              onSave={async (name) => {
                await updateSettings.mutateAsync({ name });
              }}
            />
          </dd>
        </div>
        <div>
          <dt>{it.lega.modeLabel}</dt>
          <dd>
            {it.leghe.mode[league.mode]}
            <span className="field__hint" style={{ display: "block" }}>
              {it.lega.modeLocked}
            </span>
          </dd>
        </div>
        <div>
          <dt>{it.lega.timezoneLabel}</dt>
          <dd>{league.timezone}</dd>
        </div>
        <div>
          <dt>{it.lega.h2hLabel}</dt>
          <dd>
            <label className="toggle" style={{ minHeight: "2rem" }}>
              <input
                type="checkbox"
                checked={league.head_to_head_enabled}
                disabled={updateSettings.isPending}
                onChange={(event) => {
                  setH2hError(null);
                  updateSettings
                    .mutateAsync({ head_to_head_enabled: event.target.checked })
                    .catch(() => setH2hError(it.app.errorBody));
                }}
              />
              <span className="toggle__track" aria-hidden="true" />
              <span>
                {league.head_to_head_enabled ? it.lega.h2hOn : it.lega.h2hOff}
              </span>
            </label>
            {h2hError ? (
              <span className="field__error" role="alert">
                {h2hError}
              </span>
            ) : null}
          </dd>
        </div>
      </dl>
    </Board>
  );
}

function TeamsBoard({ league }: { league: LeagueView }) {
  const { userTeam } = useActiveLeague();
  const updateBudget = useUpdateBudget(league.id);

  return (
    <Board
      title={it.lega.teamsBoard}
      meta={
        <span style={{ display: "inline-flex", gap: "var(--s-3)", flexWrap: "wrap" }}>
          <Link to="/rosa/importa/avversaria">{it.lega.addOpponent}</Link>
          <Link to="/rosa/aggiungi/avversaria">{it.lega.addOpponentManual}</Link>
        </span>
      }
      flush
    >
      <ul>
        {league.fantasy_teams.map((team) => {
          const credits = fmtCredits(team.remaining_credits);
          return (
            <li key={team.id} className="row row--zebra">
              <span className="row__main">
                <span className="row__name">{team.name}</span>
                <span className="row__meta">
                  {team.is_user_team ? it.lega.yourTeam : it.lega.opponent}
                </span>
              </span>
              <span className="row__aside">
                {team.is_user_team && userTeam !== null ? (
                  <InlineEdit
                    label={it.rosa.budgetEdit}
                    display={
                      credits !== null
                        ? `${credits} ${it.lega.credits}`
                        : it.lega.creditsUnknown
                    }
                    initial={credits ?? ""}
                    savedText={it.rosa.budgetSaved}
                    validate={parseDecimalInput}
                    onSave={async (normalized) => {
                      await updateBudget.mutateAsync({
                        fantasyTeamId: team.id,
                        body: { remaining_credits: normalized },
                      });
                    }}
                  />
                ) : (
                  <>
                    <span className="row__meta num">
                      {credits !== null
                        ? `${credits} ${it.lega.credits}`
                        : it.lega.creditsUnknown}
                    </span>
                    <Link
                      className="btn btn--secondary btn--small"
                      to={`/rosa/aggiungi/avversaria?squadra=${team.id}&nome=${encodeURIComponent(team.name)}`}
                    >
                      {it.aggiungi.entryRoster}
                    </Link>
                    <Link
                      className="btn btn--secondary btn--small"
                      to={`/rosa/importa/avversaria?squadra=${team.id}&nome=${encodeURIComponent(team.name)}`}
                    >
                      {it.lega.importOpponent}
                    </Link>
                  </>
                )}
              </span>
            </li>
          );
        })}
      </ul>
      <div className="board__foot">
        <span>{it.lega.budgetHint}</span>
      </div>
    </Board>
  );
}

function RulesBoard({ league }: { league: LeagueView }) {
  const [editing, setEditing] = useState(false);
  const rosters = useRosters(league.id);
  const userValidation = (rosters.data ?? []).find(
    (roster) => roster.fantasy_team.is_user_team,
  )?.validation;

  return (
    <Board
      title={it.lega.rulesBoard}
      meta={`${it.lega.rulesVersion(league.rules.version)} · ${it.lega.rulesEffective} ${fmtDateTimeFull(league.rules.effective_from, league.timezone)}`}
    >
      {userValidation && !userValidation.valid ? (
        <div style={{ marginBottom: "var(--s-4)" }}>
          <Notice tone="warn">
            <strong>{it.lega.rosterInvalidTitle}.</strong>{" "}
            {it.lega.rosterInvalidRulesNote}{" "}
            <Link to="/rosa">{it.lega.seeRoster}</Link>
          </Notice>
        </div>
      ) : null}
      {editing ? (
        <RulesEditor
          league={league}
          onDone={() => setEditing(false)}
          onCancel={() => setEditing(false)}
        />
      ) : (
        <>
          <RulesSummary rules={league.rules} mode={league.mode} />
          <div style={{ marginTop: "var(--s-4)" }}>
            <button
              type="button"
              className="btn btn--secondary"
              onClick={() => setEditing(true)}
            >
              {it.lega.editRules}
            </button>
          </div>
        </>
      )}
    </Board>
  );
}

function SystemBoard() {
  const system = useSystemStatus();

  return (
    <Board
      title={it.lega.systemBoard}
      id="sistema"
      meta={
        system.data ? (
          <span>
            <Mark
              kind={
                system.data.status === "healthy"
                  ? "ok"
                  : system.data.status === "updating"
                    ? "half"
                    : "warn"
              }
              label={
                system.data.status === "healthy"
                  ? it.lega.systemHealthy
                  : system.data.status === "updating"
                    ? it.lega.systemUpdating
                    : it.lega.systemDegraded
              }
            />{" "}
            {system.data.status === "healthy"
              ? it.lega.systemHealthy
              : system.data.status === "updating"
                ? it.lega.systemUpdating
                : it.lega.systemDegraded}
          </span>
        ) : null
      }
    >
      {system.isPending ? (
        <Skeleton lines={5} />
      ) : system.isError ? (
        <Notice tone="bad">{errorMessage(system.error)}</Notice>
      ) : (
        <div style={{ display: "grid", gap: "var(--s-4)" }}>
          <dl className="deflist">
            <div>
              <dt>{it.lega.freshnessIngestion}</dt>
              <dd className="num">
                {system.data.freshness.latest_successful_ingestion
                  ? fmtDateTimeFull(system.data.freshness.latest_successful_ingestion)
                  : it.lega.never}
              </dd>
            </div>
            <div>
              <dt>{it.lega.freshnessPrediction}</dt>
              <dd className="num">
                {system.data.freshness.latest_prediction_cutoff
                  ? fmtDateTimeFull(system.data.freshness.latest_prediction_cutoff)
                  : it.lega.never}
              </dd>
            </div>
            <div>
              <dt>{it.lega.freshnessTraining}</dt>
              <dd className="num">
                {system.data.freshness.latest_model_training
                  ? fmtDateTimeFull(system.data.freshness.latest_model_training)
                  : it.lega.never}
              </dd>
            </div>
            <div>
              <dt>{it.lega.championModels}</dt>
              <dd className="num">{system.data.champion_models}</dd>
            </div>
            <div>
              <dt>{it.lega.upcomingFixtures}</dt>
              <dd className="num">{system.data.upcoming_fixture_count ?? 0}</dd>
            </div>
            <div>
              <dt>{it.lega.qualityIssues}</dt>
              <dd className="num">{system.data.unresolved_quality_issues}</dd>
            </div>
          </dl>

          {system.data.warnings.length > 0 ? (
            <ul style={{ display: "grid", gap: "var(--s-2)" }}>
              {system.data.warnings.map((warning) => (
                <li key={warning} className="notice notice--warn">
                  <Mark kind="warn" />
                  <span>{translateSystemWarning(warning)}</span>
                </li>
              ))}
            </ul>
          ) : null}

          {(system.data.notices ?? []).map((notice) => (
            <Notice key={notice}>{notice}</Notice>
          ))}

          <Disclosure label={it.lega.sources}>
            <div className="tablewrap">
              <table className="table">
                <thead>
                  <tr>
                    <th scope="col">{it.lega.sources}</th>
                    <th scope="col">Stato</th>
                    <th scope="col">{it.lega.lastIngestion}</th>
                  </tr>
                </thead>
                <tbody>
                  {(system.data.sources ?? []).map((source) => (
                    <tr key={source.key}>
                      <td>{source.name}</td>
                      <td>
                        <Mark
                          kind={
                            source.status === "available"
                              ? "ok"
                              : source.status === "unconfigured"
                                ? "ask"
                                : source.status === "stale"
                                  ? "half"
                                  : "out"
                          }
                          label={it.lega.sourceStates[source.status] ?? source.status}
                        />{" "}
                        {it.lega.sourceStates[source.status] ?? source.status}
                      </td>
                      <td className="num">
                        {source.latest_successful_ingestion
                          ? fmtDateTimeFull(source.latest_successful_ingestion)
                          : it.lega.never}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Disclosure>
        </div>
      )}
    </Board>
  );
}

type JobKind = "refresh" | "train";

function JobsBoard() {
  const client = useQueryClient();
  const system = useSystemStatus();
  const [confirming, setConfirming] = useState<JobKind | null>(null);
  const [jobId, setJobId] = useState<string | null>(null);
  const [startError, setStartError] = useState<string | null>(null);
  const job = useJob(jobId);


  const jobStatus = job.data?.status;
  useEffect(() => {
    if (jobStatus === "succeeded") {
      void client.invalidateQueries({ queryKey: keys.system });
      void client.invalidateQueries({ queryKey: ["predictions"] });
      void client.invalidateQueries({ queryKey: ["players"] });
      invalidateDecisions(client);
    }
  }, [jobStatus, client]);

  async function start(kind: JobKind) {
    setConfirming(null);
    setStartError(null);
    try {
      const started: JobView =
        kind === "refresh" ? await api.refreshData() : await api.trainModels();
      setJobId(started.id);
    } catch {
      setStartError(it.app.errorBody);
    }
  }

  const running =
    jobStatus === "queued" || jobStatus === "running" || job.isFetching;

  return (
    <Board
      title={it.lega.jobsBoard}
      meta={
        system.data
          ? it.lega.activeJobs(system.data.queued_jobs, system.data.running_jobs)
          : null
      }
    >
      <div style={{ display: "grid", gap: "var(--s-3)" }}>
        <div style={{ display: "flex", gap: "var(--s-3)", flexWrap: "wrap" }}>
          <button
            type="button"
            className="btn btn--secondary"
            disabled={running}
            onClick={() => setConfirming("refresh")}
          >
            {it.lega.refreshData}
          </button>
          <button
            type="button"
            className="btn btn--secondary"
            disabled={running}
            onClick={() => setConfirming("train")}
          >
            {it.lega.trainModels}
          </button>
        </div>

        {startError ? <Notice tone="bad">{startError}</Notice> : null}

        {job.data ? (
          <div className="notice" role="status">
            <Mark
              kind={
                job.data.status === "succeeded"
                  ? "ok"
                  : job.data.status === "failed"
                    ? "out"
                    : job.data.status === "cancelled"
                      ? "off"
                      : "half"
              }
            />
            <span>
              {job.data.job_type},{" "}
              {job.data.status === "queued"
                ? it.lega.jobQueued
                : job.data.status === "running"
                  ? it.lega.jobRunning
                  : job.data.status === "succeeded"
                    ? it.lega.jobSucceeded
                    : job.data.status === "failed"
                      ? it.lega.jobFailed
                      : it.lega.jobCancelled}
              {job.data.status === "running" && job.data.progress > 0 ? (
                <>
                  {" "}
                  · {it.lega.jobProgress}{" "}
                  <strong className="num">{fmtPct(job.data.progress)}</strong>
                </>
              ) : null}
              {job.data.error ? (
                <>
                  {" "}
                  · {it.lega.jobError}: {job.data.error}
                </>
              ) : null}
            </span>
            {job.data.status === "failed" ? (
              <button
                type="button"
                className="btn btn--quiet btn--small"
                onClick={() => {
                  const kind: JobKind = job.data.job_type.includes("train")
                    ? "train"
                    : "refresh";
                  void start(kind);
                }}
              >
                {it.app.retry}
              </button>
            ) : null}
          </div>
        ) : null}
      </div>

      <ConfirmDialog
        open={confirming !== null}
        title={confirming === "train" ? it.lega.trainModels : it.lega.refreshData}
        body={
          <p>
            {confirming === "train"
              ? it.lega.trainModelsBody
              : it.lega.refreshDataBody}
          </p>
        }
        confirmLabel={it.app.confirm}
        onConfirm={() => {
          if (confirming !== null) void start(confirming);
        }}
        onClose={() => setConfirming(null)}
      />
    </Board>
  );
}
