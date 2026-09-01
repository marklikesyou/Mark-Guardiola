import type {
  LeagueMode,
  LeagueRulesView,
  RosterConstraints,
  ScoringRules,
} from "../../api/types";
import { fmtNumber } from "../../lib/format";
import { roleLetter } from "../../lib/roles";
import { it } from "../../lib/strings";

function scoringEntries(scoring: ScoringRules): Array<[string, string]> {
  const fields = it.lega.scoringFields;
  const entries: Array<[string, string]> = [];
  const goal = scoring.goal_points ?? {};
  const cleanSheet = scoring.clean_sheet_points ?? {};
  const conceded = scoring.goal_conceded_points ?? {};

  const pushIf = (label: string, value: number | undefined) => {
    if (value !== undefined) entries.push([label, fmtNumber(value, 2)]);
  };

  pushIf(fields.goalFWD, goal.FWD);
  pushIf(fields.goalMID, goal.MID);
  pushIf(fields.goalDEF, goal.DEF);
  pushIf(fields.goalGK, goal.GK);
  entries.push([fields.assist, fmtNumber(scoring.assist_points ?? 1, 2)]);
  pushIf(fields.cleanSheetGK, cleanSheet.GK);
  pushIf(fields.cleanSheetDEF, cleanSheet.DEF);
  pushIf(fields.concededGK, conceded.GK);
  entries.push([
    fields.penaltySaved,
    fmtNumber(scoring.penalty_saved_points ?? 3, 2),
  ]);
  entries.push([
    fields.penaltyMissed,
    fmtNumber(scoring.penalty_missed_points ?? -3, 2),
  ]);
  entries.push([fields.ownGoal, fmtNumber(scoring.own_goal_points ?? -2, 2)]);
  entries.push([fields.yellow, fmtNumber(scoring.yellow_card_points ?? -0.5, 2)]);
  entries.push([fields.red, fmtNumber(scoring.red_card_points ?? -1, 2)]);
  return entries;
}

export function RulesSummary({
  rules,
  mode: _mode,
}: {
  rules: LeagueRulesView;
  mode: LeagueMode;
}) {
  const scoring = rules.scoring ?? ({} as ScoringRules);
  const subs = rules.substitution_rules;
  const constraints = (rules.roster_constraints ?? {}) as RosterConstraints;
  const roleLimits = constraints.role_limits ?? null;

  return (
    <div style={{ display: "grid", gap: "var(--s-4)" }}>
      <div>
        <h3 className="rulehead" style={{ padding: 0, marginBottom: "var(--s-2)" }}>
          {it.lega.scoring}
        </h3>
        <dl className="deflist">
          {scoringEntries(scoring).map(([label, value]) => (
            <div key={label}>
              <dt>{label}</dt>
              <dd className="num">{value}</dd>
            </div>
          ))}
        </dl>
      </div>

      <div>
        <h3 className="rulehead" style={{ padding: 0, marginBottom: "var(--s-2)" }}>
          {it.lega.formations}
        </h3>
        <ul style={{ display: "flex", flexWrap: "wrap", gap: "var(--s-2)" }}>
          {(rules.formations ?? []).map((formation) => (
            <li key={formation.name}>
              <span
                className="chip"
                title={formation.slots.map((slot) => roleLetter(slot)).join(" · ")}
              >
                {formation.name}
              </span>
            </li>
          ))}
        </ul>
      </div>

      <dl className="deflist">
        {subs ? (
          <>
            <div>
              <dt>{it.lega.benchSize}</dt>
              <dd className="num">{subs.bench_size ?? it.app.notAvailable}</dd>
            </div>
            <div>
              <dt>{it.lega.maxSubs}</dt>
              <dd className="num">{subs.maximum_substitutions ?? 5}</dd>
            </div>
            <div>
              <dt>{it.lega.formationChangeAllowed}</dt>
              <dd>{subs.allow_formation_change ? it.lega.yes : it.lega.no}</dd>
            </div>
          </>
        ) : null}
        {(constraints.minimum_players ?? 0) > 0 || constraints.maximum_players != null ? (
          <div>
            <dt>{it.lega.rosterConstraints}</dt>
            <dd className="num">
              da {constraints.minimum_players ?? 0} a{" "}
              {constraints.maximum_players ?? "nessun limite"}{" "}
              giocatori
            </dd>
          </div>
        ) : null}
        {roleLimits && Object.keys(roleLimits).length > 0 ? (
          <div>
            <dt>{it.lega.roleLimitsLabel}</dt>
            <dd className="num">
              {Object.entries(roleLimits)
                .map(([role, limit]) => `${limit}${roleLetter(role)}`)
                .join(" · ")}
            </dd>
          </div>
        ) : null}
        <div>
          <dt>{it.lega.modifierSection}</dt>
          <dd>
            {scoring.defensive_modifier_enabled
              ? `${it.lega.yes} · ${(scoring.defensive_modifier_roles ?? [])
                  .map((role) => roleLetter(role))
                  .join(" ")} · ${(scoring.defensive_modifier_bands ?? [])
                  .map(
                    (band) =>
                      `≥${fmtNumber(band.minimum_average, 2)}: ${fmtNumber(band.points, 2)}`,
                  )
                  .join(", ") || it.app.notAvailable}`
              : it.lega.no}
          </dd>
        </div>
      </dl>
    </div>
  );
}
