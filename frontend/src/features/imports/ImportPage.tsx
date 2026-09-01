import { useId, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { useImportMarket, useImportRoster } from "../../api/queries";
import type {
  ImportPlayer,
  ImportResolutionView,
  ImportResult,
} from "../../api/types";
import { useActiveLeague } from "../../app/LeagueContext";
import { fmtPct, parseDecimalInput } from "../../lib/format";
import { IMPORT_SIZE_ERROR, MAX_IMPORT_BYTES, parseRosterText, type ParsedRow } from "../../lib/parse";
import { it } from "../../lib/strings";
import { IconChevron } from "../../ui/icons";
import {
  Board,
  Mark,
  Notice,
  Steps,
} from "../../ui/primitives";

export type ImportKind = "roster" | "opponent" | "market";

interface RowChoice {
  excluded: boolean;
  pickedId: string | null;
}

const STEP_LABELS = [
  it.imports.stepPaste,
  it.imports.stepReview,
  it.imports.stepResolve,
  it.imports.stepDone,
];

function titleFor(kind: ImportKind): string {
  if (kind === "market") return it.imports.marketTitle;
  if (kind === "opponent") return it.imports.opponentTitle;
  return it.imports.rosterTitle;
}


function firstPassPlayers(rows: ParsedRow[]): ImportPlayer[] {
  return rows.map((row) => ({
    name: row.name,
    role: row.roles[0] ?? null,
    team: row.team,
    purchase_price: row.price,
    player_id: null,
  }));
}





function finalPlayers(
  rows: ParsedRow[],
  resolutions: ImportResolutionView[],
  choices: Record<number, RowChoice>,
): ImportPlayer[] {
  const players: ImportPlayer[] = [];
  rows.forEach((row, index) => {
    const choice = choices[index];
    if (choice?.excluded) return;
    const resolution = resolutions[index];
    const playerId =
      choice?.pickedId ?? resolution?.selected_player_id ?? null;
    if (playerId === null) return;
    const roles = row.roles.length > 0 ? row.roles : [null];
    for (const role of roles) {
      players.push({
        name: row.name,
        role,
        team: row.team,
        purchase_price: row.price,
        player_id: playerId,
      });
    }
  });
  return players;
}

export function ImportPage({ kind }: { kind: ImportKind }) {
  const { leagueId, league, userTeam } = useActiveLeague();
  const [params] = useSearchParams();
  const importRoster = useImportRoster(leagueId);
  const importMarket = useImportMarket(leagueId);

  const [step, setStep] = useState(0);
  const [text, setText] = useState("");
  const [opponentName, setOpponentName] = useState(params.get("nome") ?? "");
  const opponentTeamId = params.get("squadra");
  const [credits, setCredits] = useState("");
  const [rows, setRows] = useState<ParsedRow[]>([]);
  const [resolutions, setResolutions] = useState<ImportResolutionView[]>([]);
  const [choices, setChoices] = useState<Record<number, RowChoice>>({});
  const [finalResult, setFinalResult] = useState<ImportResult | null>(null);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [fileError, setFileError] = useState<string | null>(null);
  const [readingFile, setReadingFile] = useState(false);

  const parsed = useMemo(
    () => parseRosterText(text, league?.mode ?? "classic", kind === "market" ? 1000 : 500),
    [text, league?.mode, kind],
  );
  const inputError = fileError ?? parsed.error;
  const busy = importRoster.isPending || importMarket.isPending;


  const resolvedPlayerCount = new Set(
    finalResult?.resolutions
      .filter((resolution) => resolution.status === "resolved" && resolution.selected_player_id)
      .map((resolution) => resolution.selected_player_id),
  ).size;

  const pendingCount = useMemo(() => {
    return resolutions.reduce((count, resolution, index) => {
      if (resolution.status === "resolved") return count;
      const choice = choices[index];
      if (choice?.excluded || choice?.pickedId) return count;
      return count + 1;
    }, 0);
  }, [resolutions, choices]);

  function readFile(file: File) {
    if (file.size > MAX_IMPORT_BYTES) {
      setFileError(IMPORT_SIZE_ERROR);
      return;
    }
    setFileError(null);
    setReadingFile(true);
    const reader = new FileReader();
    reader.onload = () => {
      if (typeof reader.result === "string") setText(reader.result);
      setReadingFile(false);
    };
    reader.onerror = () => {
      setFileError(it.imports.fileReadError);
      setReadingFile(false);
    };
    reader.readAsText(file);
  }

  async function sendFirstPass() {
    setSubmitError(null);
    const players = firstPassPlayers(rows);
    try {
      let result: ImportResult;
      if (kind === "market") {
        result = await importMarket.mutateAsync({
          players,
          replace_existing: true,
        });
      } else {
        result = await importRoster.mutateAsync({
          players,
          replace_existing: true,
          ...(kind === "roster"
            ? { fantasy_team_id: userTeam?.id ?? null, is_user_team: true }
            : opponentTeamId
              ? { fantasy_team_id: opponentTeamId, is_user_team: false }
              : {
                  fantasy_team_name: opponentName.trim(),
                  is_user_team: false,
                }),
        });
      }
      setResolutions(result.resolutions);
      setChoices({});
      setStep(2);
    } catch {
      setSubmitError(it.app.errorBody);
    }
  }

  async function sendFinal() {
    setSubmitError(null);
    const players = finalPlayers(rows, resolutions, choices);
    const normalizedCredits =
      kind === "roster" && credits.trim() !== ""
        ? parseDecimalInput(credits)
        : null;
    if (kind === "roster" && credits.trim() !== "" && normalizedCredits === null) {
      setSubmitError(it.rosa.budgetInvalid);
      return;
    }
    try {
      let result: ImportResult;
      if (kind === "market") {
        result = await importMarket.mutateAsync({
          players,
          replace_existing: true,
        });
      } else {
        result = await importRoster.mutateAsync({
          players,
          replace_existing: true,
          ...(normalizedCredits !== null
            ? { remaining_credits: normalizedCredits }
            : {}),
          ...(kind === "roster"
            ? { fantasy_team_id: userTeam?.id ?? null, is_user_team: true }
            : opponentTeamId
              ? { fantasy_team_id: opponentTeamId, is_user_team: false }
              : {
                  fantasy_team_name: opponentName.trim(),
                  is_user_team: false,
                }),
        });
      }
      setFinalResult(result);
      setStep(3);
    } catch {
      setSubmitError(it.app.errorBody);
    }
  }

  const replaceWarning =
    kind === "market"
      ? it.imports.replaceWarningMarket
      : it.imports.replaceWarningRoster;

  return (
    <div className="page" style={{ maxWidth: "48rem", margin: "0 auto" }}>
      <div className="page__head">
        <h1 className="page__title">{titleFor(kind)}</h1>
      </div>
      <Steps labels={STEP_LABELS} current={step} />

      {step === 0 ? (
        <Board title={it.imports.stepPaste}>
          <div style={{ display: "grid", gap: "var(--s-4)" }}>
            {kind === "opponent" && !opponentTeamId ? (
              <div className="field">
                <label className="field__label" htmlFor="nome-avversaria">
                  {it.imports.opponentNameLabel}
                </label>
                <input
                  id="nome-avversaria"
                  name="opponent_name"
                  autoComplete="off"
                  className="input"
                  value={opponentName}
                  onChange={(event) => setOpponentName(event.target.value)}
                  maxLength={160}
                  required
                />
              </div>
            ) : null}
            {kind === "opponent" && opponentTeamId ? (
              <p className="field__hint">
                {it.imports.opponentNameLabel}: <strong>{opponentName || it.app.notAvailable}</strong>
              </p>
            ) : null}

            <div className="field">
              <label className="field__label" htmlFor="elenco">
                {it.imports.pasteLabel}
              </label>
              <textarea
                id="elenco"
                name="roster_text"
                autoComplete="off"
                className="textarea"
                value={text}
                disabled={readingFile}
                aria-invalid={inputError !== null}
                aria-describedby={inputError ? "import-input-error" : undefined}
                onChange={(event) => { setText(event.target.value); setFileError(null); }}
                placeholder={it.imports.pastePlaceholder}
                spellCheck={false}
              />
              <details className="disclosure" style={{ borderTop: 0 }}>
                <summary>
                  <IconChevron />
                  {it.imports.pasteHelp}
                </summary>
                <div className="disclosure__body">
                  <p>{it.imports.pasteHelpBody}</p>
                </div>
              </details>
            </div>

            <div>
              <input
                type="file"
                accept=".csv,.txt,text/csv,text/plain"
                className="visually-hidden"
                id="file-import"
                name="roster_file"
                disabled={readingFile}
                onChange={(event) => {
                  const file = event.target.files?.[0];
                  if (file) readFile(file);
                  event.target.value = "";
                }}
              />
              <label htmlFor="file-import" className="btn btn--secondary btn--small">
                {it.imports.fileButton}
              </label>
              {readingFile ? <p role="status">{it.imports.fileReading}</p> : null}
            </div>

            {inputError ? <p id="import-input-error" className="field__error" role="alert">{inputError}</p> : null}

            {kind === "roster" ? (
              <div className="field" style={{ maxWidth: "14rem" }}>
                <label className="field__label" htmlFor="crediti-residui">
                  {it.imports.creditsOptionalLabel}
                </label>
                <input
                  id="crediti-residui"
                  name="remaining_credits"
                  autoComplete="off"
                  className="input"
                  inputMode="decimal"
                  value={credits}
                  onChange={(event) => setCredits(event.target.value)}
                />
              </div>
            ) : null}

            <p className="field__hint" role="status">
              {parsed.rows.length > 0
                ? it.imports.parsedRows(parsed.rows.length)
                : text.trim() !== ""
                  ? it.imports.emptyParse
                  : ""}
            </p>

            <div>
              <button
                type="button"
                className="btn btn--primary"
                disabled={
                  parsed.rows.length === 0 ||
                  inputError !== null || readingFile ||
                  (kind === "opponent" &&
                    !opponentTeamId &&
                    opponentName.trim() === "")
                }
                onClick={() => {
                  setRows(parsed.rows);
                  setStep(1);
                }}
              >
                {it.app.next}
              </button>
            </div>
          </div>
        </Board>
      ) : null}

      {step === 1 ? (
        <Board
          title={it.imports.reviewTitle}
          meta={it.imports.parsedRows(rows.length)}
          flush
          busy={busy}
        >
          <div className="tablewrap">
            <table className="table">
              <thead>
                <tr>
                  <th scope="col">{it.imports.name}</th>
                  <th scope="col">{it.imports.role}</th>
                  <th scope="col">{it.imports.team}</th>
                  <th scope="col" className="num">
                    {it.imports.price}
                  </th>
                </tr>
              </thead>
              <tbody>
                {rows.map((row) => (
                  <tr key={`${row.line}-${row.name}`}>
                    <td>{row.name}</td>
                    <td>{row.roles.join(" ") || it.app.notAvailable}</td>
                    <td>{row.team ?? it.app.notAvailable}</td>
                    <td className="num">{row.price ?? it.app.notAvailable}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div style={{ padding: "var(--s-4)", display: "grid", gap: "var(--s-3)" }}>
            {rows.some((row) => row.issue !== null) ? (
              <Notice tone="warn">
                {it.imports.parseIssues}:{" "}
                {rows
                  .filter((row) => row.issue !== null)
                  .map((row) => `riga ${row.line} (${row.issue})`)
                  .join(", ")}
              </Notice>
            ) : null}
            <Notice tone="warn">{replaceWarning}</Notice>
            {submitError ? (
              <p className="field__error" role="alert">
                {submitError}
              </p>
            ) : null}
            <div style={{ display: "flex", gap: "var(--s-3)", flexWrap: "wrap" }}>
              <button
                type="button"
                className="btn btn--secondary"
                onClick={() => setStep(0)}
                disabled={busy}
              >
                {it.app.back}
              </button>
              <button
                type="button"
                className="btn btn--primary"
                disabled={busy}
                onClick={() => {
                  void sendFirstPass();
                }}
              >
                {busy ? it.imports.sending : it.imports.send}
              </button>
            </div>
          </div>
        </Board>
      ) : null}

      {step === 2 ? (
        <Board
          title={it.imports.stepResolve}
          meta={`${resolutions.filter((r) => r.status === "resolved").length}/${resolutions.length} ${it.imports.resolvedBadge}`}
          flush
          busy={busy}
        >
          <p className="field__hint" style={{ padding: "var(--s-3) var(--s-4) 0" }}>
            {it.imports.resolveIntro}
          </p>
          <ul>
            {resolutions.map((resolution, index) => (
              <ResolutionRow
                key={`${index}-${resolution.imported_name}`}
                resolution={resolution}
                choice={choices[index] ?? { excluded: false, pickedId: null }}
                onChange={(next) =>
                  setChoices((current) => ({ ...current, [index]: next }))
                }
              />
            ))}
          </ul>
          <div style={{ padding: "var(--s-4)", display: "grid", gap: "var(--s-3)" }}>
            {pendingCount > 0 ? (
              <Notice tone="warn">{it.imports.pendingChoices(pendingCount)}</Notice>
            ) : (
              <p className="field__hint">
                {it.imports.confirmFinalHint(
                  finalPlayersCount(rows, resolutions, choices),
                  Object.values(choices).filter((choice) => choice.excluded).length,
                )}
              </p>
            )}
            {submitError ? (
              <p className="field__error" role="alert">
                {submitError}
              </p>
            ) : null}
            <div style={{ display: "flex", gap: "var(--s-3)", flexWrap: "wrap" }}>
              <button
                type="button"
                className="btn btn--primary"
                disabled={pendingCount > 0 || busy}
                onClick={() => {
                  void sendFinal();
                }}
              >
                {busy
                  ? it.imports.sending
                  : kind === "market"
                    ? it.imports.confirmFinalMarket
                    : it.imports.confirmFinal}
              </button>
            </div>
          </div>
        </Board>
      ) : null}

      {step === 3 && finalResult !== null ? (
        <Board title={it.imports.doneTitle}>
          <div style={{ display: "grid", gap: "var(--s-3)" }}>
            <p>
              <Mark kind="ok" />{" "}
              {kind === "market"
                ? it.imports.doneMarket(resolvedPlayerCount)
                : it.imports.doneRoster(resolvedPlayerCount)}
            </p>
            {finalResult.unresolved_count > 0 ? (
              <Notice tone="warn">
                {it.imports.partialWarning(finalResult.unresolved_count)}
              </Notice>
            ) : null}
            <div style={{ display: "flex", gap: "var(--s-3)", flexWrap: "wrap" }}>
              {kind === "market" ? (
                <Link to="/mercato" className="btn btn--primary">
                  {it.imports.goMercato}
                </Link>
              ) : kind === "roster" ? (
                <>
                  <Link to="/giornata" className="btn btn--primary">
                    {it.imports.goGiornata}
                  </Link>
                  <Link to="/rosa" className="btn btn--secondary">
                    {it.imports.goRosa}
                  </Link>
                </>
              ) : (
                <Link to="/lega" className="btn btn--primary">
                  {it.nav.lega}
                </Link>
              )}
            </div>
          </div>
        </Board>
      ) : null}

    </div>
  );
}

function finalPlayersCount(
  rows: ParsedRow[],
  resolutions: ImportResolutionView[],
  choices: Record<number, RowChoice>,
): number {
  let count = 0;
  rows.forEach((_row, index) => {
    const choice = choices[index];
    if (choice?.excluded) return;
    const resolution = resolutions[index];
    if ((choice?.pickedId ?? resolution?.selected_player_id) !== null) count += 1;
  });
  return count;
}

function ResolutionRow({
  resolution,
  choice,
  onChange,
}: {
  resolution: ImportResolutionView;
  choice: RowChoice;
  onChange: (next: RowChoice) => void;
}) {
  const choiceGroup = useId();
  const status = resolution.status;
  const resolvedCandidate = resolution.candidates.find(
    (candidate) => candidate.player_id === resolution.selected_player_id,
  );

  return (
    <li className="res-row">
      <div className="res-row__line">
        {status === "resolved" ? (
          <Mark kind="ok" label={it.imports.resolvedBadge} />
        ) : status === "ambiguous" ? (
          <Mark kind="half" label={it.imports.ambiguousBadge} />
        ) : (
          <Mark kind="out" label={it.imports.unresolvedBadge} />
        )}
        <span className="res-row__name">{resolution.imported_name}</span>
        <span className="chip">
          {status === "resolved"
            ? it.imports.resolvedBadge
            : status === "ambiguous"
              ? it.imports.ambiguousBadge
              : it.imports.unresolvedBadge}
        </span>
        {status === "resolved" ? (
          <span className="res-row__resolved num">
            {resolvedCandidate ? `${resolvedCandidate.display_name} · ` : ""}
            {it.imports.confidence} {fmtPct(resolution.confidence)}
          </span>
        ) : null}
        {choice.excluded ? (
          <span className="chip">{it.imports.excludedNote}</span>
        ) : null}
      </div>

      {status === "ambiguous" && !choice.excluded ? (
        <fieldset style={{ border: 0, padding: 0, margin: 0 }}>
          <legend className="field__hint">{it.imports.ambiguousPick}</legend>
          <div className="candidates">
            {resolution.candidates.map((candidate) => (
              <label key={candidate.player_id} className="candidate">
                <input
                  type="radio"
                  name={`scelta-${choiceGroup}`}
                  checked={choice.pickedId === candidate.player_id}
                  onChange={() =>
                    onChange({ excluded: false, pickedId: candidate.player_id })
                  }
                />
                <span>
                  <strong>{candidate.display_name}</strong>{" "}
                  <span className="num">({fmtPct(candidate.confidence)})</span>
                  {candidate.evidence.length > 0 ? (
                    <span className="candidate__evidence">
                      {" "}
                      , {candidate.evidence.join(", ")}
                    </span>
                  ) : null}
                </span>
              </label>
            ))}
          </div>
        </fieldset>
      ) : null}

      {status === "unresolved" && !choice.excluded ? (
        <p className="field__hint">{it.imports.unresolvedKeep}</p>
      ) : null}

      {status !== "resolved" ? (
        <div>
          <label className="candidate" style={{ minHeight: "2.25rem" }}>
            <input
              type="checkbox"
              checked={choice.excluded}
              onChange={(event) =>
                onChange({
                  excluded: event.target.checked,
                  pickedId: event.target.checked ? null : choice.pickedId,
                })
              }
            />
            <span>{it.imports.excludeRow}</span>
          </label>
        </div>
      ) : null}
    </li>
  );
}
