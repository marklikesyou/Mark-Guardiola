import { useEffect, useId, useMemo, useRef, useState } from "react";
import { useReplaceRules } from "../../api/queries";
import type {
  Formation,
  LeagueView,
  RosterConstraints,
  ScoringRules,
} from "../../api/types";
import { ApiError } from "../../lib/apiErrors";
import { roleLetter, roleName } from "../../lib/roles";
import { it } from "../../lib/strings";
import { IconPlus, IconX } from "../../ui/icons";
import { ConfirmDialog, Disclosure, Mark, Notice } from "../../ui/primitives";

const FOOTBALL_ROLES = ["GK", "DEF", "MID", "FWD"] as const;
const MANTRA_SLOTS = [
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

function parseNumber(text: string): number | null {
  const cleaned = text.trim().replace(",", ".");
  if (cleaned === "" || !/^[+-]?\d+(\.\d+)?$/.test(cleaned)) return null;
  const value = Number(cleaned);
  return Number.isFinite(value) ? value : null;
}

function parseIntIn(text: string, min: number, max: number): number | null {
  const value = parseNumber(text);
  if (value === null || !Number.isInteger(value) || value < min || value > max) {
    return null;
  }
  return value;
}

function show(value: number | undefined, fallback: number): string {
  return String(value ?? fallback).replace(".", ",");
}

interface ScoringField {
  key: string;
  label: string;
  integerMax?: number;
  nullable?: boolean;
  hint?: string;
}

function parseScoringField(field: ScoringField, text: string): number | null {
  return field.integerMax === undefined
    ? parseNumber(text)
    : parseIntIn(text, 0, field.integerMax);
}

interface FormationDraft {
  name: string;

  def: string;
  mid: string;
  fwd: string;
  slots: string[];
}

function draftFromFormation(
  formation: Formation,
  mode: "classic" | "mantra",
): FormationDraft {
  if (mode === "classic") {
    const count = (slot: string) =>
      formation.slots.filter((entry) => entry === slot).length;
    return {
      name: formation.name,
      def: String(count("DEF")),
      mid: String(count("MID")),
      fwd: String(count("FWD")),
      slots: [...formation.slots],
    };
  }
  return {
    name: formation.name,
    def: "",
    mid: "",
    fwd: "",
    slots: [...formation.slots],
  };
}

function formationFromDraft(
  draft: FormationDraft,
  mode: "classic" | "mantra",
): Formation | null {
  const name = draft.name.trim();
  if (name === "") return null;
  if (mode === "classic") {
    const def = parseIntIn(draft.def, 0, 10);
    const mid = parseIntIn(draft.mid, 0, 10);
    const fwd = parseIntIn(draft.fwd, 0, 10);
    if (def === null || mid === null || fwd === null) return null;
    if (def + mid + fwd !== 10) return null;
    return {
      name,
      slots: [
        "GK",
        ...Array.from({ length: def }, () => "DEF"),
        ...Array.from({ length: mid }, () => "MID"),
        ...Array.from({ length: fwd }, () => "FWD"),
      ],
    };
  }
  if (draft.slots.length !== 11) return null;
  return { name, slots: [...draft.slots] };
}

export function RulesEditor({
  league,
  onDone,
  onCancel,
}: {
  league: LeagueView;
  onDone: () => void;
  onCancel: () => void;
}) {
  const replaceRules = useReplaceRules(league.id);
  const mode = league.mode;
  const scoring = league.rules.scoring ?? ({} as ScoringRules);
  const subs = league.rules.substitution_rules ?? {};
  const constraints = (league.rules.roster_constraints ??
    {}) as RosterConstraints;
  const fields = it.lega.scoringFields;
  const formId = useId();
  const roleVocabulary = mode === "classic" ? FOOTBALL_ROLES : MANTRA_SLOTS;

  const [values, setValues] = useState<Record<string, string>>({
    goalFWD: show(scoring.goal_points?.FWD, 3),
    goalMID: show(scoring.goal_points?.MID, 3),
    goalDEF: show(scoring.goal_points?.DEF, 3),
    goalGK: show(scoring.goal_points?.GK, 3),
    assist: show(scoring.assist_points, 1),
    cleanSheetGK: show(scoring.clean_sheet_points?.GK, 1),
    cleanSheetDEF: show(scoring.clean_sheet_points?.DEF, 0),
    concededGK: show(scoring.goal_conceded_points?.GK, -1),
    penaltySaved: show(scoring.penalty_saved_points, 3),
    penaltyMissed: show(scoring.penalty_missed_points, -3),
    ownGoal: show(scoring.own_goal_points, -2),
    yellow: show(scoring.yellow_card_points, -0.5),
    red: show(scoring.red_card_points, -1),
    save: show(scoring.save_points, 0),
    baseRatingFallback: show(scoring.base_rating_fallback, 6),
    appearanceMinutes: show(scoring.appearance_minimum_minutes, 1),
    benchSize: subs.bench_size === null ? "" : show(subs.bench_size, 7),
    maxSubs: show(subs.maximum_substitutions, 5),
  });
  const [baseRatingEnabled, setBaseRatingEnabled] = useState(
    scoring.base_rating_enabled ?? true,
  );
  const [allowFormationChange, setAllowFormationChange] = useState(
    subs.allow_formation_change ?? false,
  );


  const initialFormations = useMemo(
    () =>
      (league.rules.formations ?? []).map((formation) =>
        draftFromFormation(formation, mode),
      ),
    [league.rules.formations, mode],
  );
  const [formations, setFormations] = useState<FormationDraft[]>(initialFormations);
  const [useDefaultFormations, setUseDefaultFormations] = useState(false);


  const [minPlayers, setMinPlayers] = useState(
    String(constraints.minimum_players ?? 0),
  );
  const [maxPlayers, setMaxPlayers] = useState(
    constraints.maximum_players === null || constraints.maximum_players === undefined
      ? ""
      : String(constraints.maximum_players),
  );
  const [roleLimits, setRoleLimits] = useState<Record<string, string>>(() => {
    const initial: Record<string, string> = {};
    for (const role of roleVocabulary) {
      const limit = constraints.role_limits?.[role];
      initial[role] = limit === undefined ? "" : String(limit);
    }
    return initial;
  });


  const [modifierEnabled, setModifierEnabled] = useState(
    scoring.defensive_modifier_enabled ?? false,
  );
  const [modifierRoles, setModifierRoles] = useState<string[]>([
    ...(scoring.defensive_modifier_roles ?? ["GK", "DEF"]),
  ]);
  const [bands, setBands] = useState<Array<{ threshold: string; points: string }>>(
    (scoring.defensive_modifier_bands ?? []).map((band) => ({
      threshold: show(band.minimum_average, 6),
      points: show(band.points, 1),
    })),
  );

  const [error, setError] = useState<string | null>(null);
  const [confirming, setConfirming] = useState(false);
  const errorRef = useRef<HTMLParagraphElement>(null);


  useEffect(() => {
    if (error !== null) errorRef.current?.focus();
  }, [error]);

  const scoringRows: ScoringField[] = [
    { key: "goalFWD", label: fields.goalFWD },
    { key: "goalMID", label: fields.goalMID },
    { key: "goalDEF", label: fields.goalDEF },
    { key: "goalGK", label: fields.goalGK },
    { key: "assist", label: fields.assist },
    { key: "cleanSheetGK", label: fields.cleanSheetGK },
    { key: "cleanSheetDEF", label: fields.cleanSheetDEF },
    { key: "concededGK", label: fields.concededGK },
    { key: "penaltySaved", label: fields.penaltySaved },
    { key: "penaltyMissed", label: fields.penaltyMissed },
    { key: "ownGoal", label: fields.ownGoal },
    { key: "yellow", label: fields.yellow },
    { key: "red", label: fields.red },
    { key: "save", label: fields.save },
    { key: "baseRatingFallback", label: fields.baseRatingFallback },
    { key: "appearanceMinutes", label: fields.appearanceMinutes, integerMax: 130,
      hint: it.lega.appearanceMinutesHint },
    { key: "benchSize", label: it.lega.benchSize, integerMax: 50, nullable: true,
      hint: it.lega.benchSizeHint },
    { key: "maxSubs", label: it.lega.maxSubs, integerMax: 11,
      hint: it.lega.maxSubsHint },
  ];

  function validateAdvanced(): string | null {
    if (!useDefaultFormations) {
      if (formations.length === 0) return it.lega.formationsAtLeastOne;
      const names = new Set<string>();
      for (const draft of formations) {
        const formation = formationFromDraft(draft, mode);
        if (formation === null) return it.lega.formationEleven;
        if (names.has(formation.name)) return it.lega.formationsHint;
        names.add(formation.name);
      }
    }
    const min = parseIntIn(minPlayers, 0, 500);
    if (min === null) return it.errors.validation;
    if (maxPlayers.trim() !== "") {
      const max = parseIntIn(maxPlayers, 11, 500);
      if (max === null) return it.lega.maxPlayersHint;
      if (min > max) return it.lega.minAboveMax;
    }
    for (const role of roleVocabulary) {
      const text = roleLimits[role] ?? "";
      if (text.trim() !== "" && parseIntIn(text, 0, 500) === null) {
        return it.errors.validation;
      }
    }
    if (modifierEnabled && modifierRoles.length === 0) {
      return it.lega.modifierRolesRequired;
    }

    let previous = -Infinity;
    for (const band of bands) {
      const threshold = parseNumber(band.threshold);
      const points = parseNumber(band.points);
      const recovery = modifierEnabled ? "" : ` ${it.lega.modifierReactivateHint}`;
      if (threshold === null || threshold < 0 || threshold > 10 || points === null) {
        return it.lega.modifierBandsHint + recovery;
      }
      if (threshold <= previous) return it.lega.bandsAscending + recovery;
      previous = threshold;
    }
    return null;
  }

  function buildPayload() {
    const parsed: Record<string, number> = {};
    for (const row of scoringRows) {
      const text = values[row.key] ?? "";
      if (row.nullable && text.trim() === "") continue;
      const value = parseScoringField(row, text);
      if (value === null) return null;
      parsed[row.key] = value;
    }

    const nextScoring: ScoringRules = {
      ...scoring,
      base_rating_enabled: baseRatingEnabled,
      base_rating_fallback: parsed.baseRatingFallback ?? 6,
      appearance_minimum_minutes: parsed.appearanceMinutes ?? 1,
      goal_points: {
        GK: parsed.goalGK ?? 3,
        DEF: parsed.goalDEF ?? 3,
        MID: parsed.goalMID ?? 3,
        FWD: parsed.goalFWD ?? 3,
      },
      assist_points: parsed.assist ?? 1,
      clean_sheet_points: {
        MID: 0,
        FWD: 0,
        ...(scoring.clean_sheet_points ?? {}),
        GK: parsed.cleanSheetGK ?? 1,
        DEF: parsed.cleanSheetDEF ?? 0,
      },
      goal_conceded_points: {
        DEF: 0,
        MID: 0,
        FWD: 0,
        ...(scoring.goal_conceded_points ?? {}),
        GK: parsed.concededGK ?? -1,
      },
      penalty_saved_points: parsed.penaltySaved ?? 3,
      penalty_missed_points: parsed.penaltyMissed ?? -3,
      own_goal_points: parsed.ownGoal ?? -2,
      yellow_card_points: parsed.yellow ?? -0.5,
      red_card_points: parsed.red ?? -1,
      save_points: parsed.save ?? 0,
      defensive_modifier_enabled: modifierEnabled,
      defensive_modifier_roles: [
        ...modifierRoles,
      ] as ScoringRules["defensive_modifier_roles"],
      defensive_modifier_bands: bands.map((band) => ({
        minimum_average: parseNumber(band.threshold) ?? 0,
        points: parseNumber(band.points) ?? 0,
      })),
    };

    const nextFormations: Formation[] | null = useDefaultFormations
      ? null
      : formations.map((draft) => formationFromDraft(draft, mode) as Formation);

    const nextConstraints: RosterConstraints = {
      minimum_players: parseIntIn(minPlayers, 0, 500) ?? 0,
      maximum_players:
        maxPlayers.trim() === "" ? null : parseIntIn(maxPlayers, 11, 500),
      role_limits: Object.fromEntries(
        roleVocabulary
          .map((role) => [role, (roleLimits[role] ?? "").trim()] as const)
          .filter(([, text]) => text !== "")
          .map(([role, text]) => [role, parseIntIn(text, 0, 500) ?? 0]),
      ),
    };

    return {
      scoring: nextScoring,
      formations: nextFormations,
      roster_constraints: nextConstraints,
      substitution_rules: {
        bench_size: parsed.benchSize ?? null,
        maximum_substitutions: parsed.maxSubs ?? 5,
        allow_formation_change: allowFormationChange,
      },
    };
  }

  async function save() {
    setConfirming(false);
    const advancedError = validateAdvanced();
    if (advancedError !== null) {
      setError(advancedError);
      return;
    }
    const payload = buildPayload();
    if (payload === null) {
      setError(it.errors.validation);
      return;
    }
    setError(null);
    try {
      await replaceRules.mutateAsync(payload);
      onDone();
    } catch (cause) {
      if (cause instanceof ApiError && cause.status === 422) {
        setError(it.errors.validation);
      } else {
        setError(it.app.errorBody);
      }
    }
  }

  return (
    <form
      onSubmit={(event) => {
        event.preventDefault();
        setConfirming(true);
      }}
      style={{ display: "grid", gap: "var(--s-4)" }}
    >
      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fill, minmax(13rem, 1fr))",
          gap: "var(--s-3)",
        }}
      >
        {scoringRows.map((row) => {
          const id = `${formId}-${row.key}`;
          const text = values[row.key] ?? "";
          const invalid = !(row.nullable && text.trim() === "") &&
            parseScoringField(row, text) === null;
          return (
            <div key={row.key} className="field">
              <label className="field__label" htmlFor={id}>
                {row.label}
              </label>
              <input
                id={id}
                className="input"
                inputMode={row.integerMax === undefined ? "decimal" : "numeric"}
                value={text}
                aria-invalid={invalid}
                aria-describedby={row.hint ? `${id}-hint` : undefined}
                onChange={(event) =>
                  setValues((current) => ({
                    ...current,
                    [row.key]: event.target.value,
                  }))
                }
              />
              {row.hint ? <p className="field__hint" id={`${id}-hint`}>{row.hint}</p> : null}
            </div>
          );
        })}
      </div>

      <label className="toggle">
        <input
          type="checkbox"
          checked={baseRatingEnabled}
          onChange={(event) => setBaseRatingEnabled(event.target.checked)}
        />
        <span className="toggle__track" aria-hidden="true" />
        <span className="field__label">{fields.baseRating}</span>
      </label>

      <label className="toggle">
        <input
          type="checkbox"
          checked={allowFormationChange}
          onChange={(event) => setAllowFormationChange(event.target.checked)}
        />
        <span className="toggle__track" aria-hidden="true" />
        <span className="field__label">{it.lega.formationChangeAllowed}</span>
      </label>

      <Disclosure label={it.lega.advancedRules}>
        <FormationsEditor
          mode={mode}
          formations={formations}
          setFormations={setFormations}
          useDefaults={useDefaultFormations}
          setUseDefaults={setUseDefaultFormations}
          formId={formId}
        />

        <section aria-label={it.lega.constraintsSection}>
          <h3 className="rulehead" style={{ padding: 0, marginBottom: "var(--s-2)" }}>
            {it.lega.constraintsSection}
          </h3>
          <p className="field__hint" style={{ marginBottom: "var(--s-3)" }}>
            {it.lega.constraintsHint}
          </p>
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "repeat(auto-fill, minmax(11rem, 1fr))",
              gap: "var(--s-3)",
            }}
          >
            <div className="field">
              <label className="field__label" htmlFor={`${formId}-min`}>
                {it.lega.minPlayersLabel}
              </label>
              <input
                id={`${formId}-min`}
                className="input"
                inputMode="numeric"
                value={minPlayers}
                onChange={(event) => setMinPlayers(event.target.value)}
              />
              <p className="field__hint">{it.lega.minPlayersHint}</p>
            </div>
            <div className="field">
              <label className="field__label" htmlFor={`${formId}-max`}>
                {it.lega.maxPlayersLabel}
              </label>
              <input
                id={`${formId}-max`}
                className="input"
                inputMode="numeric"
                value={maxPlayers}
                onChange={(event) => setMaxPlayers(event.target.value)}
              />
              <p className="field__hint">{it.lega.maxPlayersHint}</p>
            </div>
          </div>
          <fieldset style={{ border: 0, padding: 0, margin: "var(--s-3) 0 0" }}>
            <legend className="field__label" style={{ marginBottom: "var(--s-1)" }}>
              {it.lega.roleLimitsLabel}
            </legend>
            <p className="field__hint" style={{ marginBottom: "var(--s-2)" }}>
              {it.lega.roleLimitsHint}
            </p>
            <div
              style={{
                display: "grid",
                gridTemplateColumns: "repeat(auto-fill, minmax(5.5rem, 1fr))",
                gap: "var(--s-2)",
              }}
            >
              {roleVocabulary.map((role) => (
                <div key={role} className="field">
                  <label
                    className="field__label num"
                    htmlFor={`${formId}-limit-${role}`}
                    title={roleName(role)}
                  >
                    {roleLetter(role)}
                  </label>
                  <input
                    id={`${formId}-limit-${role}`}
                    className="input"
                    inputMode="numeric"
                    value={roleLimits[role] ?? ""}
                    onChange={(event) =>
                      setRoleLimits((current) => ({
                        ...current,
                        [role]: event.target.value,
                      }))
                    }
                  />
                </div>
              ))}
            </div>
          </fieldset>
        </section>

        <section aria-label={it.lega.modifierSection}>
          <h3 className="rulehead" style={{ padding: 0, marginBottom: "var(--s-2)" }}>
            {it.lega.modifierSection}
          </h3>
          <label className="toggle">
            <input
              type="checkbox"
              checked={modifierEnabled}
              onChange={(event) => setModifierEnabled(event.target.checked)}
            />
            <span className="toggle__track" aria-hidden="true" />
            <span className="field__label">{it.lega.modifierEnabled}</span>
          </label>
          <fieldset
            style={{ border: 0, padding: 0, margin: "var(--s-3) 0 0" }}
            disabled={!modifierEnabled}
          >
            <legend className="field__label" style={{ marginBottom: "var(--s-1)" }}>
              {it.lega.modifierRoles}
            </legend>
            <p className="field__hint" style={{ marginBottom: "var(--s-2)" }}>
              {it.lega.modifierRolesHint}
            </p>
            <div style={{ display: "flex", gap: "var(--s-3)", flexWrap: "wrap" }}>
              {FOOTBALL_ROLES.map((role) => (
                <label key={role} className="candidate" style={{ minHeight: "2.25rem" }}>
                  <input
                    type="checkbox"
                    checked={modifierRoles.includes(role)}
                    onChange={(event) =>
                      setModifierRoles((current) =>
                        event.target.checked
                          ? [...current, role]
                          : current.filter((existing) => existing !== role),
                      )
                    }
                  />
                  <span>{roleName(role)}</span>
                </label>
              ))}
            </div>
            <div style={{ marginTop: "var(--s-3)", display: "grid", gap: "var(--s-2)" }}>
              <p className="field__label">{it.lega.modifierBands}</p>
              <p className="field__hint">{it.lega.modifierBandsHint}</p>
              {bands.map((band, index) => (
                <div
                  key={index}
                  style={{ display: "flex", gap: "var(--s-2)", alignItems: "end", flexWrap: "wrap" }}
                >
                  <div className="field">
                    <label className="field__label" htmlFor={`${formId}-band-t-${index}`}>
                      {it.lega.bandThreshold}
                    </label>
                    <input
                      id={`${formId}-band-t-${index}`}
                      className="input"
                      inputMode="decimal"
                      style={{ width: "7rem" }}
                      value={band.threshold}
                      onChange={(event) =>
                        setBands((current) =>
                          current.map((existing, i) =>
                            i === index
                              ? { ...existing, threshold: event.target.value }
                              : existing,
                          ),
                        )
                      }
                    />
                  </div>
                  <div className="field">
                    <label className="field__label" htmlFor={`${formId}-band-p-${index}`}>
                      {it.lega.bandPoints}
                    </label>
                    <input
                      id={`${formId}-band-p-${index}`}
                      className="input"
                      inputMode="decimal"
                      style={{ width: "7rem" }}
                      value={band.points}
                      onChange={(event) =>
                        setBands((current) =>
                          current.map((existing, i) =>
                            i === index
                              ? { ...existing, points: event.target.value }
                              : existing,
                          ),
                        )
                      }
                    />
                  </div>
                  <button
                    type="button"
                    className="btn btn--secondary btn--small"
                    onClick={() =>
                      setBands((current) => current.filter((_, i) => i !== index))
                    }
                  >
                    <IconX /> {it.lega.bandRemove}
                  </button>
                </div>
              ))}
              <div>
                <button
                  type="button"
                  className="btn btn--secondary btn--small"
                  onClick={() =>
                    setBands((current) => [...current, { threshold: "", points: "" }])
                  }
                >
                  <IconPlus /> {it.lega.bandAdd}
                </button>
              </div>
            </div>
          </fieldset>
        </section>
      </Disclosure>

      {error ? (
        <p className="field__error" role="alert" tabIndex={-1} ref={errorRef}>
          <Mark kind="out" /> {error}
        </p>
      ) : null}

      <div style={{ display: "flex", gap: "var(--s-3)", flexWrap: "wrap" }}>
        <button
          type="submit"
          className="btn btn--primary"
          disabled={replaceRules.isPending}
        >
          {it.app.save}
        </button>
        <button
          type="button"
          className="btn btn--secondary"
          onClick={onCancel}
          disabled={replaceRules.isPending}
        >
          {it.app.cancel}
        </button>
      </div>

      <ConfirmDialog
        open={confirming}
        title={it.lega.rulesSaveTitle}
        body={<p>{it.lega.rulesSaveBody}</p>}
        confirmLabel={it.app.confirm}
        onConfirm={() => {
          void save();
        }}
        onClose={() => setConfirming(false)}
      />
    </form>
  );
}

function FormationsEditor({
  mode,
  formations,
  setFormations,
  useDefaults,
  setUseDefaults,
  formId,
}: {
  mode: "classic" | "mantra";
  formations: FormationDraft[];
  setFormations: React.Dispatch<React.SetStateAction<FormationDraft[]>>;
  useDefaults: boolean;
  setUseDefaults: (next: boolean) => void;
  formId: string;
}) {
  function update(index: number, patch: Partial<FormationDraft>) {
    setFormations((current) =>
      current.map((existing, i) =>
        i === index ? { ...existing, ...patch } : existing,
      ),
    );
  }

  function addFormation() {
    setUseDefaults(false);
    setFormations((current) => [
      ...current,
      mode === "classic"
        ? { name: "", def: "4", mid: "4", fwd: "2", slots: [] }
        : {
            name: "",
            def: "",
            mid: "",
            fwd: "",
            slots: [
              "Por",
              "Dd",
              "Dc",
              "Dc",
              "Ds",
              "M",
              "C",
              "C",
              "W",
              "A",
              "Pc",
            ],
          },
    ]);
  }

  return (
    <section aria-label={it.lega.formationsSection}>
      <h3 className="rulehead" style={{ padding: 0, marginBottom: "var(--s-2)" }}>
        {it.lega.formationsSection}
      </h3>
      <p className="field__hint" style={{ marginBottom: "var(--s-3)" }}>
        {it.lega.formationsHint}
        {mode === "classic" ? ` ${it.lega.formationClassicHint}` : ""}
      </p>

      <label className="toggle" style={{ marginBottom: "var(--s-3)" }}>
        <input
          type="checkbox"
          checked={useDefaults}
          onChange={(event) => setUseDefaults(event.target.checked)}
        />
        <span className="toggle__track" aria-hidden="true" />
        <span>
          <span className="field__label">{it.lega.formationDefaults}</span>
          <span className="field__hint" style={{ display: "block" }}>
            {it.lega.formationDefaultsHint}
          </span>
        </span>
      </label>

      {useDefaults ? null : (
        <div style={{ display: "grid", gap: "var(--s-3)" }}>
          {formations.map((draft, index) => (
            <div
              key={index}
              style={{
                display: "grid",
                gap: "var(--s-2)",
                border: "1px solid var(--rule)",
                borderRadius: "var(--radius)",
                padding: "var(--s-3)",
              }}
            >
              <div
                style={{
                  display: "flex",
                  gap: "var(--s-2)",
                  alignItems: "end",
                  flexWrap: "wrap",
                }}
              >
                <div className="field" style={{ minWidth: "9rem" }}>
                  <label
                    className="field__label"
                    htmlFor={`${formId}-formation-${index}`}
                  >
                    {it.lega.formationName}
                  </label>
                  <input
                    id={`${formId}-formation-${index}`}
                    className="input"
                    value={draft.name}
                    onChange={(event) => update(index, { name: event.target.value })}
                    maxLength={40}
                  />
                </div>
                {mode === "classic" ? (
                  <>
                    {(
                      [
                        ["def", "D"],
                        ["mid", "C"],
                        ["fwd", "A"],
                      ] as const
                    ).map(([key, label]) => (
                      <div key={key} className="field" style={{ width: "5rem" }}>
                        <label
                          className="field__label num"
                          htmlFor={`${formId}-formation-${index}-${key}`}
                        >
                          {label}
                        </label>
                        <input
                          id={`${formId}-formation-${index}-${key}`}
                          className="input"
                          inputMode="numeric"
                          value={draft[key]}
                          onChange={(event) =>
                            update(index, { [key]: event.target.value })
                          }
                        />
                      </div>
                    ))}
                  </>
                ) : null}
                <button
                  type="button"
                  className="btn btn--secondary btn--small"
                  onClick={() =>
                    setFormations((current) => current.filter((_, i) => i !== index))
                  }
                >
                  <IconX /> {it.lega.formationRemove}
                </button>
              </div>

              {mode === "mantra" ? (
                <div
                  style={{
                    display: "grid",
                    gridTemplateColumns: "repeat(auto-fill, minmax(5rem, 1fr))",
                    gap: "var(--s-2)",
                  }}
                >
                  {Array.from({ length: 11 }, (_, slotIndex) => (
                    <div key={slotIndex} className="field">
                      <label
                        className="field__label"
                        htmlFor={`${formId}-formation-${index}-slot-${slotIndex}`}
                      >
                        {it.lega.formationSlotLabel(slotIndex + 1)}
                      </label>
                      <select
                        id={`${formId}-formation-${index}-slot-${slotIndex}`}
                        className="select"
                        value={draft.slots[slotIndex] ?? "C"}
                        onChange={(event) => {
                          const slots = [...draft.slots];
                          while (slots.length < 11) slots.push("C");
                          slots[slotIndex] = event.target.value;
                          update(index, { slots });
                        }}
                      >
                        {MANTRA_SLOTS.map((slot) => (
                          <option key={slot} value={slot}>
                            {slot}
                          </option>
                        ))}
                      </select>
                    </div>
                  ))}
                </div>
              ) : null}
            </div>
          ))}
          <div>
            <button
              type="button"
              className="btn btn--secondary btn--small"
              onClick={addFormation}
            >
              <IconPlus /> {it.lega.formationAdd}
            </button>
          </div>
          {formations.length === 0 ? (
            <Notice tone="warn">{it.lega.formationsAtLeastOne}</Notice>
          ) : null}
        </div>
      )}
    </section>
  );
}
