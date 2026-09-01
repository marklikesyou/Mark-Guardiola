import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router-dom";
import { keys, useMarket } from "../../api/queries";
import type { MarketRecommendationItem } from "../../api/types";
import { useActiveLeague } from "../../app/LeagueContext";
import { OwnedPlayerPortrait } from "../../app/PlayerPhotoPolicy";
import { ApiError, conflictGuidance, errorMessage } from "../../lib/apiErrors";
import { fmtCredits, fmtDateTimeFull, fmtDelta, fmtNumber } from "../../lib/format";
import { it } from "../../lib/strings";
import {
  Board,
  Disclosure,
  EmptyState,
  LongWait,
  Mark,
  Meter,
  Segmented,
} from "../../ui/primitives";

type Horizon = 1 | 3 | 5 | 10;

const HORIZONS: Array<{ value: Horizon; label: string }> = [
  { value: 1, label: "1" },
  { value: 3, label: "3" },
  { value: 5, label: "5" },
  { value: 10, label: "10" },
];

export function MercatoPage() {
  const { leagueId, league } = useActiveLeague();
  const [horizon, setHorizon] = useState<Horizon>(3);
  const [recoverPrice, setRecoverPrice] = useState(false);
  const [requested, setRequested] = useState(false);
  const [cancelled, setCancelled] = useState(false);
  const client = useQueryClient();
  const market = useMarket(leagueId, horizon, recoverPrice, requested);
  const timezone = league?.timezone ?? "Europe/Rome";

  async function cancelComputation() {
    await client.cancelQueries({
      queryKey: keys.market(leagueId, horizon, recoverPrice),
    });
    setCancelled(true);
    setRequested(false);
  }

  function compute() {
    setCancelled(false);
    setRequested(true);
    if (market.isError || market.data !== undefined) void market.refetch();
  }

  return (
    <div className="page">
      <div className="page__head">
        <h1 className="page__title">{it.mercato.title}</h1>
        <div className="page__actions">
          <Link to="/mercato/aggiungi" className="btn btn--secondary btn--small">
            {it.aggiungi.entryMarket}
          </Link>
          <Link to="/mercato/importa" className="btn btn--secondary btn--small">
            {it.mercato.importCta}
          </Link>
        </div>
      </div>
      <p style={{ maxWidth: "44rem" }}>{it.mercato.intro}</p>

      <div
        style={{
          display: "flex",
          gap: "var(--s-4)",
          flexWrap: "wrap",
          alignItems: "center",
        }}
      >
        <div style={{ display: "flex", gap: "var(--s-2)", alignItems: "center" }}>
          <span className="field__label" id="orizzonte-label">
            {it.mercato.horizon}
          </span>
          <Segmented
            legend={it.mercato.horizon}
            options={HORIZONS.map((option) => ({
              value: option.value,
              label: option.label,
              title: it.mercato.horizonHint(option.value),
            }))}
            value={horizon}
            onChange={(next) => {
              setHorizon(next);
              setCancelled(false);
            }}
            disabled={market.isFetching}
          />
          <span className="field__hint">{it.mercato.horizonHint(horizon)}</span>
        </div>
        <label className="toggle">
          <input
            type="checkbox"
            checked={recoverPrice}
            onChange={(event) => setRecoverPrice(event.target.checked)}
          />
          <span className="toggle__track" aria-hidden="true" />
          <span className="field__hint">{it.mercato.recoverPrice}</span>
        </label>
        {market.data !== undefined || market.isError ? (
          <button
            type="button"
            className="btn btn--primary"
            onClick={compute}
            disabled={market.isFetching}
          >
            {it.mercato.recompute}
          </button>
        ) : null}
      </div>

      {!requested && market.data === undefined ? (
        <Board title={it.mercato.resultsBoard}>
          <EmptyState title={it.mercato.emptyTitle} body={it.mercato.emptyBody}>
            <Link to="/mercato/importa" className="btn btn--primary">
              {it.mercato.importCta}
            </Link>
            <button type="button" className="btn btn--secondary" onClick={compute}>
              {it.mercato.compute}
            </button>
          </EmptyState>
        </Board>
      ) : cancelled ? (
        <Board title={it.mercato.resultsBoard}>
          <EmptyState title={it.app.requestCancelled}>
            <button type="button" className="btn btn--primary" onClick={compute}>
              {it.app.retry}
            </button>
          </EmptyState>
        </Board>
      ) : market.isFetching || (requested && market.isPending) ? (
        <Board title={it.mercato.resultsBoard} busy>
          <LongWait
            title={it.mercato.computing}
            body={it.mercato.computingBody}
            onCancel={() => {
              void cancelComputation();
            }}
          />
        </Board>
      ) : market.isError ? (
        <MarketError error={market.error} onRetry={compute} />
      ) : market.data !== undefined ? (
        <>
          <Board
            title={it.mercato.resultsBoard}
            meta={
              market.data.remaining_budget !== null
                ? `${it.mercato.budget}: ${fmtCredits(market.data.remaining_budget)}`
                : it.mercato.budgetUnknown
            }
            flush
            foot={
              <>
                <span>
                  {it.giornata.freshnessData}{" "}
                  {fmtDateTimeFull(market.data.data_cutoff, timezone)}
                </span>
                <span>
                  {it.giornata.freshnessDecision}{" "}
                  {fmtDateTimeFull(market.data.decision_cutoff, timezone)}
                </span>
              </>
            }
          >
            {market.data.items.length === 0 ? (
              <EmptyState title={it.mercato.noItems} />
            ) : (
              <ol className="compose">
                {market.data.items.map((item, index) => (
                  <MarketDeal
                    key={item.recommendation_id}
                    item={item}
                    rank={index + 1}
                    horizon={horizon}
                  />
                ))}
              </ol>
            )}
          </Board>
          {(market.data.warnings ?? []).length > 0 ? (
            <Board title={it.giornata.warningsBoard}>
              <ul style={{ display: "grid", gap: "var(--s-2)" }}>
                {(market.data.warnings ?? []).map((warning) => (
                  <li key={warning} className="notice notice--warn">
                    <Mark kind="warn" />
                    <span>{warning}</span>
                  </li>
                ))}
              </ul>
            </Board>
          ) : null}
          <p className="field__hint" style={{ maxWidth: "44rem" }}>
            {it.mercato.evidenceNote} {it.mercato.horizonNote}
          </p>
        </>
      ) : null}
    </div>
  );
}

function MarketError({
  error,
  onRetry,
}: {
  error: unknown;
  onRetry: () => void;
}) {
  if (error instanceof ApiError && (error.status === 409 || error.status === 404)) {
    const guidance = conflictGuidance(error);
    return (
      <Board title={it.mercato.resultsBoard}>
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
      </Board>
    );
  }
  return (
    <Board title={it.mercato.resultsBoard}>
      <EmptyState title={it.app.error} body={errorMessage(error)}>
        <button type="button" className="btn btn--primary" onClick={onRetry}>
          {it.app.retry}
        </button>
      </EmptyState>
    </Board>
  );
}

function MarketDeal({
  item,
  rank,
  horizon,
}: {
  item: MarketRecommendationItem;
  rank: number;
  horizon: Horizon;
}) {
  const price = fmtCredits(item.asking_price);
  const reason = item.explanations[0]?.text ?? null;
  const horizonEntries = Object.entries(item.horizon_improvements).sort(
    (a, b) => Number(a[0]) - Number(b[0]),
  );

  return (
    <li className="deal deal--zebra">
      <div className="deal__line">
        <span className="deal__rank num" aria-hidden="true">
          {rank}
        </span>
        <span className="deal__portraits" aria-hidden="true">
          <OwnedPlayerPortrait
            playerId={item.target_player_id}
            name={item.target_name}
            photoUrl={item.target_photo_url}
            size="medium"
          />
          <OwnedPlayerPortrait
            playerId={item.replace_player_id}
            name={item.replace_name}
            photoUrl={item.replace_photo_url}
            size="small"
          />
        </span>
        <span className="deal__swap">
          <span className="deal__in">{item.target_name}</span>
          <span className="deal__out">per {item.replace_name}</span>
        </span>
        <span
          className={`deal__gain ${item.expected_improvement >= 0 ? "deal__gain--pos" : "deal__gain--neg"}`}
          aria-label={`${it.mercato.improvement} ${it.mercato.improvementAt(horizon)}: ${fmtDelta(item.expected_improvement)} ${it.giornata.points}`}
        >
          {fmtDelta(item.expected_improvement)}
        </span>
      </div>
      <div className="deal__facts">
        <span>
          {price !== null ? (
            <>
              {it.mercato.askingPrice} <strong className="num">{price}</strong>
            </>
          ) : (
            <>
              <Mark kind="ask" label={it.mercato.priceUnknown} />{" "}
              {it.mercato.priceUnknown} · {it.mercato.affordabilityUnknown}
            </>
          )}
        </span>
        <span>{it.mercato.formationChange(item.formation_before, item.formation_after)}</span>
        <Meter value={item.confidence} label={it.giornata.confidence} ink />
      </div>
      {reason ? <p className="deal__reason">{reason}</p> : null}
      <Disclosure label={it.giornata.advanced}>
        <dl className="deflist">
          {horizonEntries.length > 0 ? (
            <div>
              <dt>{it.mercato.horizonTable}</dt>
              <dd className="num">
                {horizonEntries
                  .map(([key, value]) => `${key}: ${fmtDelta(value)}`)
                  .join(" · ")}
              </dd>
            </div>
          ) : null}
          <div>
            <dt>{it.mercato.valueOverReplacement}</dt>
            <dd className="num">{fmtDelta(item.value_over_replacement)}</dd>
          </div>
          {item.budget_efficiency !== null ? (
            <div>
              <dt>{it.mercato.budgetEfficiency}</dt>
              <dd className="num">{fmtNumber(item.budget_efficiency, 3)}</dd>
            </div>
          ) : null}
          <div>
            <dt>{it.mercato.roleFlex}</dt>
            <dd className="num">
              {item.role_flexibility_delta > 0
                ? `+${item.role_flexibility_delta}`
                : item.role_flexibility_delta}
            </dd>
          </div>
          {item.formation_schedule_after &&
          item.formation_schedule_after.length > 0 ? (
            <div>
              <dt>{it.mercato.schedule}</dt>
              <dd className="num">
                {it.mercato.scheduleBefore}:{" "}
                {(item.formation_schedule_before ?? []).join(", ") || it.app.notAvailable},{" "}
                {it.mercato.scheduleAfter}:{" "}
                {item.formation_schedule_after.join(", ")}
              </dd>
            </div>
          ) : null}
        </dl>
        {item.explanations.length > 1 ? (
          <ul style={{ display: "grid", gap: "var(--s-1)" }}>
            {item.explanations.slice(1).map((explanation, index) => (
              <li key={`${explanation.evidence_key}-${index}`}>
                {explanation.text}
              </li>
            ))}
          </ul>
        ) : null}
        <p>{it.giornata.optimality}</p>
      </Disclosure>
    </li>
  );
}
