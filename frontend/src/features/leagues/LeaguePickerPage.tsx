import { Link, useNavigate } from "react-router-dom";
import { useLeagueContext } from "../../app/LeagueContext";
import { it } from "../../lib/strings";
import { IconPlus } from "../../ui/icons";
import { Board, EmptyState, Skeleton } from "../../ui/primitives";

export function LeaguePickerPage() {
  const { leagues, leaguesLoading, leaguesError, refetchLeagues, selectLeague } = useLeagueContext();
  const navigate = useNavigate();

  return (
    <div className="page" style={{ maxWidth: "44rem", margin: "0 auto" }}>
      <div className="page__head">
        <h1 className="page__title">{it.leghe.title}</h1>
        <Link to="/benvenuto" className="btn btn--secondary btn--small">
          <IconPlus /> {it.leghe.newLeague}
        </Link>
      </div>
      <Board title={it.leghe.title} meta={it.leghe.pickIntro} flush>
        {leaguesLoading ? (
          <div style={{ padding: "var(--s-4)" }}>
            <Skeleton lines={3} />
          </div>
        ) : leaguesError ? (
          <EmptyState title={it.app.error} body={it.app.offline}>
            <button type="button" className="btn btn--primary" onClick={refetchLeagues}>
              {it.app.retry}
            </button>
          </EmptyState>
        ) : leagues.length === 0 ? (
          <EmptyState title={it.leghe.empty}>
            <Link to="/benvenuto" className="btn btn--primary">
              {it.leghe.newLeague}
            </Link>
          </EmptyState>
        ) : (
          <ul className="rows">
            {leagues.map((league) => (
              <li key={league.id} className="row">
                <span className="row__main">
                  <span className="row__name">{league.name}</span>
                  <span className="row__meta">
                    {it.leghe.mode[league.mode]}
                    {league.head_to_head_enabled ? ` · ${it.leghe.h2hOn}` : ""}
                  </span>
                </span>
                <span className="row__aside">
                  <button
                    type="button"
                    className="btn btn--primary btn--small"
                    onClick={() => {
                      selectLeague(league.id);
                      void navigate("/giornata");
                    }}
                  >
                    {it.leghe.open}
                  </button>
                </span>
              </li>
            ))}
          </ul>
        )}
      </Board>
    </div>
  );
}
