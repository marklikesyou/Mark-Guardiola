import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { usePlayers, useSystemStatus } from "../../api/queries";
import { OwnedPlayerPortrait } from "../../app/PlayerPhotoPolicy";
import { errorMessage } from "../../lib/apiErrors";
import { positionLabel } from "../../lib/roles";
import { it } from "../../lib/strings";
import { IconSearch } from "../../ui/icons";
import { Board, EmptyState, Mark, Skeleton } from "../../ui/primitives";

const PAGE_SIZE = 50;

export function GiocatoriPage() {
  const [input, setInput] = useState("");
  const [search, setSearch] = useState("");
  const [onlyActive, setOnlyActive] = useState(true);
  const [offset, setOffset] = useState(0);
  const players = usePlayers(search, onlyActive, offset);
  const system = useSystemStatus();


  useEffect(() => {
    const timer = window.setTimeout(() => {
      setSearch(input.trim());
      setOffset(0);
    }, 300);
    return () => window.clearTimeout(timer);
  }, [input]);

  const total = players.data?.meta.total ?? 0;
  const from = total === 0 ? 0 : offset + 1;
  const to = Math.min(offset + PAGE_SIZE, total);
  const dataNeverRefreshed =
    system.data?.freshness.latest_successful_ingestion == null;

  return (
    <div className="page">
      <div className="page__head">
        <h1 className="page__title">{it.giocatori.title}</h1>
        {players.data ? (
          <p className="page__meta num">{it.giocatori.results(total)}</p>
        ) : null}
      </div>

      <div className="searchbar">
        <div className="field" style={{ flex: "1 1 16rem", maxWidth: "24rem" }}>
          <label className="field__label" htmlFor="cerca">
            {it.giocatori.searchLabel}
          </label>
          <div style={{ position: "relative" }}>
            <input
              id="cerca"
              type="search"
              className="input"
              value={input}
              onChange={(event) => setInput(event.target.value)}
              placeholder={it.giocatori.searchPlaceholder}
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
        <label className="toggle">
          <input
            type="checkbox"
            checked={onlyActive}
            onChange={(event) => {
              setOnlyActive(event.target.checked);
              setOffset(0);
            }}
          />
          <span className="toggle__track" aria-hidden="true" />
          <span className="field__hint">{it.giocatori.onlyActive}</span>
        </label>
      </div>

      <Board title={it.giocatori.listBoard} flush busy={players.isFetching}>
        {players.isPending ? (
          <div style={{ padding: "var(--s-4)" }}>
            <Skeleton lines={8} />
          </div>
        ) : players.isError ? (
          <EmptyState title={it.app.error} body={errorMessage(players.error)}>
            <button
              type="button"
              className="btn btn--primary"
              onClick={() => {
                void players.refetch();
              }}
            >
              {it.app.retry}
            </button>
          </EmptyState>
        ) : players.data.items.length === 0 ? (
          <EmptyState
            title={it.giocatori.noResultsTitle}
            body={
              dataNeverRefreshed
                ? it.giocatori.noPredictionsBodyStale
                : it.giocatori.noResultsBody
            }
          />
        ) : (
          <>
            <ul>
              {players.data.items.map((player) => {
                const position = positionLabel(player.primary_position);
                return (
                  <li key={player.id} className="row row--zebra">
                    <OwnedPlayerPortrait
                      playerId={player.id}
                      name={player.display_name}
                      photoUrl={player.photo_url}
                      size="medium"
                    />
                    <span className="row__main">
                      <span className="row__name">
                        <Link
                          to={`/giocatori/${player.id}`}
                          style={{ color: "inherit", textDecoration: "none" }}
                        >
                          {player.display_name}
                        </Link>
                      </span>
                      {!player.active ? (
                        <span className="row__meta">
                          <Mark kind="out" label={it.giocatori.notActive} />{" "}
                          {it.giocatori.notActive}
                        </span>
                      ) : null}
                    </span>
                    {position ? (
                      <span className="row__aside">
                        <span className="row__meta">{position}</span>
                      </span>
                    ) : null}
                  </li>
                );
              })}
            </ul>
            <div className="pager">
              <button
                type="button"
                className="btn btn--secondary btn--small"
                disabled={offset === 0 || players.isFetching}
                onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}
              >
                {it.giocatori.prev}
              </button>
              <span className="num">{it.giocatori.pageOf(from, to, total)}</span>
              <button
                type="button"
                className="btn btn--secondary btn--small"
                disabled={to >= total || players.isFetching}
                onClick={() => setOffset(offset + PAGE_SIZE)}
              >
                {it.giocatori.next}
              </button>
            </div>
          </>
        )}
      </Board>
    </div>
  );
}
