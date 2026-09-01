import { useEffect, useId, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import {
  useImportMarket,
  useImportRoster,
  usePlayers,
} from "../../api/queries";
import type { ImportPlayer, PlayerSummary } from "../../api/types";
import { useActiveLeague } from "../../app/LeagueContext";
import { ApiError } from "../../lib/apiErrors";
import { parseDecimalInput } from "../../lib/format";
import { positionGroup, positionLabel, roleLetter, roleName } from "../../lib/roles";
import { it } from "../../lib/strings";
import { IconSearch } from "../../ui/icons";
import {
  Board,
  EmptyState,
  Mark,
  Notice,
  Skeleton,
} from "../../ui/primitives";

export type AddTarget = "roster" | "opponent" | "market";

const CLASSIC_ROLES = ["GK", "DEF", "MID", "FWD"] as const;
const MANTRA_ROLES = [
  "Por",
  "Dd",
  "Ds",
  "Dc",
  "B",
  "E",
  "M",
  "C",
  "T",
  "W",
  "A",
  "Pc",
] as const;

function titleFor(target: AddTarget): string {
  if (target === "market") return it.aggiungi.marketTitle;
  if (target === "opponent") return it.aggiungi.opponentTitle;
  return it.aggiungi.rosterTitle;
}


function presetRoles(
  player: PlayerSummary,
  mode: "classic" | "mantra",
): string[] {
  const group = positionGroup(player.primary_position);
  if (group === null) return [];
  if (mode === "classic") return [group];

  return group === "GK" ? ["Por"] : [];
}

export function ManualAddPage({ target }: { target: AddTarget }) {
  const { leagueId, league, userTeam } = useActiveLeague();
  const [params] = useSearchParams();
  const importRoster = useImportRoster(leagueId);
  const importMarket = useImportMarket(leagueId);
  const mode = league?.mode ?? "classic";
  const roleVocabulary = mode === "classic" ? CLASSIC_ROLES : MANTRA_ROLES;

  const [input, setInput] = useState("");
  const [search, setSearch] = useState("");
  const [selected, setSelected] = useState<PlayerSummary | null>(null);
  const [roles, setRoles] = useState<string[]>([]);
  const [keepRoles, setKeepRoles] = useState(false);
  const [price, setPrice] = useState("");
  const [clearPrice, setClearPrice] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);
  const [conflict, setConflict] = useState<string | null>(null);
  const [addedSession, setAddedSession] = useState<
    Array<{ name: string; roles: string[] }>
  >([]);


  const paramTeamId = params.get("squadra");
  const paramTeamName = params.get("nome") ?? "";
  const [newOpponentName, setNewOpponentName] = useState("");
  const [createdOpponentId, setCreatedOpponentId] = useState<string | null>(null);
  const opponentTeamId = paramTeamId ?? createdOpponentId;

  const searchId = useId();
  const priceId = useId();
  const opponentId = useId();

  useEffect(() => {
    const timer = window.setTimeout(() => setSearch(input.trim()), 300);
    return () => window.clearTimeout(timer);
  }, [input]);

  const results = usePlayers(search, true, 0);
  const busy = importRoster.isPending || importMarket.isPending;

  const targetTeamLabel = useMemo(() => {
    if (target === "roster") return userTeam?.name ?? null;
    if (target === "opponent") {
      if (paramTeamName) return paramTeamName;
      if (createdOpponentId) return newOpponentName;
      return null;
    }
    return null;
  }, [target, userTeam, paramTeamName, createdOpponentId, newOpponentName]);

  function choose(player: PlayerSummary) {
    setSelected(player);
    setRoles(presetRoles(player, mode));
    setKeepRoles(false);
    setPrice("");
    setClearPrice(false);
    setFormError(null);
    setConflict(null);
  }

  function toggleRole(role: string) {
    setKeepRoles(false);
    setRoles((current) =>
      current.includes(role)
        ? current.filter((existing) => existing !== role)
        : [...current, role],
    );
  }

  function buildPlayers(): ImportPlayer[] | null {
    if (selected === null) return null;
    let purchase: { purchase_price?: string | null } = {};
    if (clearPrice) {
      purchase = { purchase_price: null };
    } else if (price.trim() !== "") {
      const normalized = parseDecimalInput(price);
      if (normalized === null) {
        setFormError(it.aggiungi.invalidPrice);
        return null;
      }
      purchase = { purchase_price: normalized };
    }
    const explicitRoles = keepRoles ? [] : roles;
    if (explicitRoles.length === 0) {
      return [{ name: selected.display_name, player_id: selected.id, ...purchase }];
    }

    return explicitRoles.map((role) => ({
      name: selected.display_name,
      player_id: selected.id,
      role,
      ...purchase,
    }));
  }

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (busy || selected === null) return;
    setFormError(null);
    setConflict(null);
    const players = buildPlayers();
    if (players === null) return;
    if (
      target === "opponent" &&
      opponentTeamId === null &&
      newOpponentName.trim() === ""
    ) {
      setFormError(it.errors.validation);
      return;
    }
    try {
      if (target === "market") {
        await importMarket.mutateAsync({ players, replace_existing: false });
      } else {
        const result = await importRoster.mutateAsync({
          players,
          replace_existing: false,
          ...(target === "roster"
            ? { fantasy_team_id: userTeam?.id ?? null, is_user_team: true }
            : opponentTeamId !== null
              ? { fantasy_team_id: opponentTeamId, is_user_team: false }
              : {
                  fantasy_team_name: newOpponentName.trim(),
                  is_user_team: false,
                }),
        });
        if (
          target === "opponent" &&
          opponentTeamId === null &&
          result.fantasy_team_id
        ) {
          setCreatedOpponentId(result.fantasy_team_id);
        }
        if (result.unresolved_count > 0) {
          setFormError(it.imports.partialWarning(result.unresolved_count));
          return;
        }
      }
      setAddedSession((current) => [
        { name: selected.display_name, roles: keepRoles ? [] : roles },
        ...current,
      ]);
      setSelected(null);
      setInput("");
      setSearch("");
    } catch (cause) {
      if (cause instanceof ApiError && cause.status === 409) {
        setConflict(it.errors.conflictFallback);
      } else {
        setFormError(it.app.errorBody);
      }
    }
  }

  const showRoleWarning = !keepRoles && roles.length > 0;
  const mantraOutfieldNeedsRoles =
    mode === "mantra" &&
    selected !== null &&
    positionGroup(selected.primary_position) !== "GK" &&
    roles.length === 0 &&
    !keepRoles;

  return (
    <div className="page" style={{ maxWidth: "48rem", margin: "0 auto" }}>
      <div className="page__head">
        <h1 className="page__title">{titleFor(target)}</h1>
        {targetTeamLabel ? (
          <p className="page__meta">
            {it.aggiungi.targetTeam}: {targetTeamLabel}
          </p>
        ) : null}
      </div>
      <p style={{ maxWidth: "40rem" }}>{it.aggiungi.intro}</p>

      {target === "opponent" && opponentTeamId === null ? (
        <div className="field" style={{ maxWidth: "24rem" }}>
          <label className="field__label" htmlFor={opponentId}>
            {it.aggiungi.newOpponentNameLabel}
          </label>
          <input
            id={opponentId}
            className="input"
            value={newOpponentName}
            onChange={(event) => setNewOpponentName(event.target.value)}
            maxLength={160}
            required
          />
        </div>
      ) : null}

      <form onSubmit={submit} noValidate>
        <Board
          title={selected === null ? it.aggiungi.searchBoard : it.aggiungi.selectedLabel}
          busy={results.isFetching && selected === null}
          flush
        >
          {selected === null ? (
            <>
              <div style={{ padding: "var(--s-4)" }}>
                <div className="field" style={{ maxWidth: "24rem" }}>
                  <label className="field__label" htmlFor={searchId}>
                    {it.aggiungi.searchLabel}
                  </label>
                  <div style={{ position: "relative" }}>
                    <input
                      id={searchId}
                      type="search"
                      className="input"
                      value={input}
                      onChange={(event) => setInput(event.target.value)}
                      placeholder={it.aggiungi.searchPlaceholder}
                      style={{ paddingRight: "2.5rem" }}
                    />
                    <span
                      aria-hidden="true"
                      style={{
                        position: "absolute",
                        right: "0.75rem",
                        top: "50%",
                        transform: "translateY(-50%)",
                        color: "var(--ink-3)",
                        display: "inline-flex",
                      }}
                    >
                      <IconSearch />
                    </span>
                  </div>
                </div>
              </div>
              {search === "" ? null : results.isPending ? (
                <div style={{ padding: "0 var(--s-4) var(--s-4)" }}>
                  <Skeleton lines={4} />
                </div>
              ) : results.isError ? (
                <div style={{ padding: "0 var(--s-4) var(--s-4)" }}>
                  <Notice tone="bad">
                    {it.aggiungi.searchErrorBody}{" "}
                    <button
                      type="button"
                      className="btn btn--quiet btn--small"
                      onClick={() => {
                        void results.refetch();
                      }}
                    >
                      {it.app.retry}
                    </button>
                  </Notice>
                </div>
              ) : results.data.items.length === 0 ? (
                <EmptyState
                  title={it.aggiungi.searchEmptyTitle}
                  body={it.aggiungi.searchEmptyBody}
                />
              ) : (
                <>
                  <ul>
                    {results.data.items.map((player) => {
                      const position = positionLabel(player.primary_position);
                      return (
                        <li key={player.id} className="row row--zebra">
                          <span className="row__main">
                            <span className="row__name">{player.display_name}</span>
                            {position ? (
                              <span className="row__meta">{position}</span>
                            ) : null}
                          </span>
                          <span className="row__aside">
                            <button
                              type="button"
                              className="btn btn--secondary btn--small"
                              onClick={() => choose(player)}
                            >
                              {it.aggiungi.pick}
                            </button>
                          </span>
                        </li>
                      );
                    })}
                  </ul>
                  {results.data.meta.total > results.data.items.length ? (
                    <p className="field__hint" style={{ padding: "var(--s-3) var(--s-4)" }}>
                      {it.giocatori.pageOf(
                        1,
                        results.data.items.length,
                        results.data.meta.total,
                      )}{" "}
                      . {it.aggiungi.searchEmptyBody}
                    </p>
                  ) : null}
                </>
              )}
            </>
          ) : (
            <div style={{ padding: "var(--s-4)", display: "grid", gap: "var(--s-4)" }}>
              <div className="row" style={{ padding: 0, borderTop: 0 }}>
                <span className="row__main">
                  <span className="row__name">{selected.display_name}</span>
                  {positionLabel(selected.primary_position) ? (
                    <span className="row__meta">
                      {positionLabel(selected.primary_position)}
                    </span>
                  ) : null}
                </span>
                <span className="row__aside">
                  <button
                    type="button"
                    className="btn btn--quiet btn--small"
                    onClick={() => setSelected(null)}
                  >
                    {it.aggiungi.changeSelection}
                  </button>
                </span>
              </div>

              <fieldset style={{ border: 0, padding: 0, margin: 0 }}>
                <legend className="field__label" style={{ marginBottom: "var(--s-1)" }}>
                  {it.aggiungi.rolesLabel}
                </legend>
                <p className="field__hint" style={{ marginBottom: "var(--s-2)" }}>
                  {it.aggiungi.rolesPrimaryHint}
                </p>
                <div className="rolepick" role="group" aria-label={it.aggiungi.rolesLabel}>
                  {roleVocabulary.map((role) => {
                    const index = roles.indexOf(role);
                    const pressed = index !== -1;
                    return (
                      <button
                        key={role}
                        type="button"
                        className="rolepick__opt"
                        aria-pressed={pressed}
                        title={roleName(role)}
                        onClick={() => toggleRole(role)}
                      >
                        {roleLetter(role)}
                        {index === 0 ? (
                          <>
                            {" "}
                            <span className="rolepick__primary">
                              {it.aggiungi.primaryBadge}
                            </span>
                          </>
                        ) : null}
                      </button>
                    );
                  })}
                </div>
                {showRoleWarning ? (
                  <p className="field__hint" style={{ marginTop: "var(--s-2)" }}>
                    <Mark kind="warn" /> {it.aggiungi.rolesReplaceWarning}
                  </p>
                ) : null}
                {mantraOutfieldNeedsRoles ? (
                  <p className="field__hint" style={{ marginTop: "var(--s-2)" }}>
                    {it.aggiungi.rolesMantraRequired}
                  </p>
                ) : null}
                <label className="toggle" style={{ marginTop: "var(--s-2)" }}>
                  <input
                    type="checkbox"
                    checked={keepRoles}
                    onChange={(event) => {
                      setKeepRoles(event.target.checked);
                      if (event.target.checked) setRoles([]);
                    }}
                  />
                  <span className="toggle__track" aria-hidden="true" />
                  <span>
                    <span className="field__label">{it.aggiungi.rolesKeep}</span>
                    <span className="field__hint" style={{ display: "block" }}>
                      {it.aggiungi.rolesKeepHint}
                    </span>
                  </span>
                </label>
              </fieldset>

              <div className="field" style={{ maxWidth: "16rem" }}>
                <label className="field__label" htmlFor={priceId}>
                  {it.aggiungi.priceLabel}
                </label>
                <input
                  id={priceId}
                  className="input"
                  inputMode="decimal"
                  value={price}
                  onChange={(event) => setPrice(event.target.value)}
                  disabled={clearPrice}
                  aria-describedby={`${priceId}-hint`}
                />
                <p className="field__hint" id={`${priceId}-hint`}>
                  {it.aggiungi.priceHint}
                </p>
                <label className="toggle" style={{ minHeight: "2.25rem" }}>
                  <input
                    type="checkbox"
                    checked={clearPrice}
                    onChange={(event) => {
                      setClearPrice(event.target.checked);
                      if (event.target.checked) setPrice("");
                    }}
                  />
                  <span className="toggle__track" aria-hidden="true" />
                  <span className="field__hint">{it.aggiungi.priceClear}</span>
                </label>
              </div>

              {conflict ? (
                <Notice tone="warn">
                  <strong>{it.aggiungi.capacityTitle}.</strong> {conflict}
                </Notice>
              ) : null}
              {formError ? (
                <p className="field__error" role="alert">
                  {formError}
                </p>
              ) : null}

              <div style={{ display: "flex", gap: "var(--s-3)", flexWrap: "wrap" }}>
                <button
                  type="submit"
                  className="btn btn--primary"
                  disabled={busy || mantraOutfieldNeedsRoles}
                >
                  {busy
                    ? it.aggiungi.submitting
                    : target === "market"
                      ? it.aggiungi.submitMarket
                      : it.aggiungi.submitRoster}
                </button>
              </div>
              <p className="field__hint">{it.aggiungi.duplicateNote}</p>
            </div>
          )}
        </Board>
      </form>

      {addedSession.length > 0 ? (
        <Board title={it.aggiungi.addedSession} flush>
          <ul>
            {addedSession.map((entry, index) => (
              <li key={`${entry.name}-${index}`} className="row">
                <Mark kind="ok" label={it.imports.resolvedBadge} />
                <span className="row__main">
                  <span className="row__name">{entry.name}</span>
                  {entry.roles.length > 0 ? (
                    <span className="row__meta">
                      {entry.roles.map((role) => roleLetter(role)).join(" ")}
                    </span>
                  ) : null}
                </span>
              </li>
            ))}
          </ul>
          <div className="board__foot">
            {target === "market" ? (
              <Link to="/mercato">{it.imports.goMercato}</Link>
            ) : target === "roster" ? (
              <Link to="/rosa">{it.imports.goRosa}</Link>
            ) : (
              <Link to="/lega">{it.nav.lega}</Link>
            )}
          </div>
        </Board>
      ) : null}
    </div>
  );
}
