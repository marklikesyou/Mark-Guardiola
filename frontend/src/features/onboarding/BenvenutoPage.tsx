import { useId, useState } from "react";
import { Link } from "react-router-dom";
import { useCreateLeague } from "../../api/queries";
import type { LeagueMode, LeagueView } from "../../api/types";
import { useLeagueContext } from "../../app/LeagueContext";
import { fmtCredits, parseDecimalInput } from "../../lib/format";
import { it } from "../../lib/strings";
import { Board } from "../../ui/primitives";
import { RulesSummary } from "../lega/RulesSummary";

export function BenvenutoPage() {
  const { selectLeague } = useLeagueContext();
  const createLeague = useCreateLeague();
  const [created, setCreated] = useState<LeagueView | null>(null);

  const [name, setName] = useState("");
  const [mode, setMode] = useState<LeagueMode>("classic");
  const [credits, setCredits] = useState("500");
  const [teamName, setTeamName] = useState("");
  const [coachName, setCoachName] = useState("");
  const [h2h, setH2h] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  const nameId = useId();
  const creditsId = useId();
  const teamId = useId();
  const coachId = useId();

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    const trimmedName = name.trim();
    if (trimmedName === "") {
      setFormError(it.errors.validation);
      return;
    }
    const parsedCredits = parseDecimalInput(credits);
    if (parsedCredits === null) {
      setFormError(it.rosa.budgetInvalid);
      return;
    }
    setFormError(null);
    try {
      const league = await createLeague.mutateAsync({
        name: trimmedName,
        mode,
        total_credits: parsedCredits,
        head_to_head_enabled: h2h,
        ...(teamName.trim() ? { team_name: teamName.trim() } : {}),
        ...(coachName.trim() ? { owner_display_name: coachName.trim() } : {}),
      });
      selectLeague(league.id);
      setCreated(league);
    } catch {
      setFormError(it.app.errorBody);
    }
  }

  if (created !== null) {
    return (
      <div className="page" style={{ maxWidth: "44rem", margin: "0 auto" }}>
        <div className="page__head">
          <h1 className="page__title">{it.benvenuto.createdTitle}</h1>
          <p className="page__meta">
            {created.name} · {it.leghe.mode[created.mode]}
          </p>
        </div>
        <Board title={it.lega.rulesBoard} meta={it.lega.rulesVersion(created.rules.version)}>
          <p style={{ marginBottom: "var(--s-4)" }} className="field__hint">
            {it.benvenuto.rulesReviewIntro}
          </p>
          <RulesSummary rules={created.rules} mode={created.mode} />
        </Board>
        <div className="empty__actions" style={{ justifyContent: "flex-start" }}>
          <Link to="/rosa/importa" className="btn btn--primary">
            {it.benvenuto.goImport}
          </Link>
          <Link to="/giornata" className="btn btn--secondary">
            {it.benvenuto.goGiornata}
          </Link>
        </div>
      </div>
    );
  }

  return (
    <div className="page page--welcome">
      <section className="welcome-hero" aria-labelledby="welcome-title">
        <div className="welcome-hero__copy">
          <p className="welcome-hero__kicker">{it.benvenuto.kicker}</p>
          <h1 className="page__title" id="welcome-title">
            {it.benvenuto.title}
          </h1>
          <p>{it.benvenuto.intro}</p>
        </div>
      </section>
      <form
        className="welcome-form"
        onSubmit={submit}
        noValidate
        aria-describedby={formError ? "errore-creazione" : undefined}
      >
        <Board title={it.benvenuto.createTitle}>
          <div style={{ display: "grid", gap: "var(--s-4)" }}>
            <div className="field">
              <label className="field__label" htmlFor={nameId}>
                {it.benvenuto.nameLabel}
              </label>
              <input
                id={nameId}
                className="input"
                value={name}
                onChange={(event) => setName(event.target.value)}
                placeholder={it.benvenuto.namePlaceholder}
                required
                maxLength={160}
              />
            </div>

            <fieldset style={{ border: 0, padding: 0, margin: 0 }}>
              <legend className="field__label" style={{ marginBottom: "var(--s-2)" }}>
                {it.benvenuto.modeLabel}
              </legend>
              <div style={{ display: "grid", gap: "var(--s-2)" }}>
                <label className="radiocard">
                  <input
                    type="radio"
                    name="mode"
                    value="classic"
                    checked={mode === "classic"}
                    onChange={() => setMode("classic")}
                  />
                  <span>
                    <span className="radiocard__name">{it.benvenuto.modeClassic}</span>
                    <span className="radiocard__desc">. {it.benvenuto.modeClassicDesc}</span>
                  </span>
                </label>
                <label className="radiocard">
                  <input
                    type="radio"
                    name="mode"
                    value="mantra"
                    checked={mode === "mantra"}
                    onChange={() => setMode("mantra")}
                  />
                  <span>
                    <span className="radiocard__name">{it.benvenuto.modeMantra}</span>
                    <span className="radiocard__desc">. {it.benvenuto.modeMantraDesc}</span>
                  </span>
                </label>
              </div>
            </fieldset>

            <div className="field">
              <label className="field__label" htmlFor={creditsId}>
                {it.benvenuto.creditsLabel}
              </label>
              <input
                id={creditsId}
                className="input"
                inputMode="decimal"
                value={credits}
                onChange={(event) => setCredits(event.target.value)}
                style={{ maxWidth: "10rem" }}
              />
              <p className="field__hint">
                {fmtCredits(parseDecimalInput(credits) ?? "") ?? it.app.notAvailable} crediti
              </p>
            </div>

            <div className="field">
              <label className="field__label" htmlFor={teamId}>
                {it.benvenuto.teamNameLabel}
              </label>
              <input
                id={teamId}
                className="input"
                value={teamName}
                onChange={(event) => setTeamName(event.target.value)}
                placeholder="La mia rosa"
                maxLength={160}
              />
            </div>

            <div className="field">
              <label className="field__label" htmlFor={coachId}>
                {it.benvenuto.coachNameLabel}
              </label>
              <input
                id={coachId}
                className="input"
                value={coachName}
                onChange={(event) => setCoachName(event.target.value)}
                placeholder="Allenatore"
                maxLength={160}
              />
            </div>

            <label className="toggle">
              <input
                type="checkbox"
                checked={h2h}
                onChange={(event) => setH2h(event.target.checked)}
              />
              <span className="toggle__track" aria-hidden="true" />
              <span>
                <span className="field__label">{it.benvenuto.h2hLabel}</span>
                <span className="field__hint" style={{ display: "block" }}>
                  {it.benvenuto.h2hHint}
                </span>
              </span>
            </label>

            {formError ? (
              <p className="field__error" role="alert" id="errore-creazione">
                {formError}
              </p>
            ) : null}

            <div>
              <button
                type="submit"
                className="btn btn--primary"
                disabled={createLeague.isPending}
              >
                {createLeague.isPending ? it.benvenuto.creating : it.benvenuto.submit}
              </button>
            </div>
          </div>
        </Board>
      </form>
    </div>
  );
}
