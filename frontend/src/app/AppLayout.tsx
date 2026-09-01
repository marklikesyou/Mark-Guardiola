import { useEffect, useRef, useState } from "react";
import { Link, NavLink, Outlet, useLocation } from "react-router-dom";
import { useSystemStatus } from "../api/queries";
import { it } from "../lib/strings";
import {
  IconGiocatori,
  IconGiornata,
  IconLega,
  IconMercato,
  IconRosa,
  IconX,
} from "../ui/icons";
import { Mark } from "../ui/primitives";
import { useLeagueContext } from "./LeagueContext";
import logoUrl from "../assets/markguardiola-logo.jpg";

const SECTIONS = [
  {
    to: "/giornata",
    label: it.nav.giornata,
    short: it.nav.giornata,
    icon: IconGiornata,
  },
  { to: "/rosa", label: it.nav.rosa, short: it.nav.rosaShort, icon: IconRosa },
  {
    to: "/mercato",
    label: it.nav.mercato,
    short: it.nav.mercato,
    icon: IconMercato,
  },
  {
    to: "/giocatori",
    label: it.nav.giocatori,
    short: it.nav.giocatori,
    icon: IconGiocatori,
  },
  { to: "/lega", label: it.nav.lega, short: it.nav.lega, icon: IconLega },
] as const;

export function AppLayout() {
  const { league, leagues } = useLeagueContext();
  const status = useSystemStatus();
  const [statusDismissed, setStatusDismissed] = useState(false);
  const mainRef = useRef<HTMLElement>(null);
  const location = useLocation();
  const previousPath = useRef(location.pathname);


  useEffect(() => {
    if (previousPath.current !== location.pathname) {
      previousPath.current = location.pathname;
      mainRef.current?.focus();
    }
  }, [location.pathname]);

  const degraded = status.data?.status === "degraded";
  const showNav = league !== null;

  return (
    <div className="shell">
      <a href="#contenuto" className="skip-link">
        {it.app.skipToContent}
      </a>
      <header className="masthead">
        <div className="masthead__inner">
          <div className="masthead__top">
            <Link to="/" className="nameplate">
              <img className="nameplate__logo" src={logoUrl} alt="" />
              <span className="nameplate__wordmark">{it.app.name}</span>
            </Link>
            <div className="masthead__meta">
              {league ? (
                <>
                  <span className="masthead__league">{league.name}</span>
                  <span>{it.leghe.mode[league.mode]}</span>
                  {leagues.length > 1 ? (
                    <Link to="/leghe">{it.leghe.switchLeague}</Link>
                  ) : null}
                </>
              ) : (
                <span>{it.app.tagline}</span>
              )}
            </div>
          </div>
          {showNav ? (
            <nav aria-label="Sezioni">
              <ul className="sections">
                {SECTIONS.map((section) => (
                  <li key={section.to}>
                    <NavLink to={section.to} className="sections__link">
                      {section.label}
                    </NavLink>
                  </li>
                ))}
              </ul>
            </nav>
          ) : null}
        </div>
      </header>

      {degraded && !statusDismissed ? (
        <div className="statusline">
          <div className="statusline__inner">
            <Mark kind="warn" />
            <span className="statusline__text">
              {it.status.degraded}{" "}
              <Link to="/lega#sistema">{it.status.degradedLink}</Link>
            </span>
            <button
              type="button"
              className="btn btn--quiet btn--small"
              onClick={() => setStatusDismissed(true)}
              aria-label={it.status.dismiss}
            >
              <IconX />
            </button>
          </div>
        </div>
      ) : null}

      <main id="contenuto" className="main" tabIndex={-1} ref={mainRef}>
        <Outlet />
      </main>

      {showNav ? (
        <nav className="bottomnav" aria-label="Sezioni">
          <ul>
            {SECTIONS.map((section) => {
              const Icon = section.icon;
              return (
                <li key={section.to}>
                  <NavLink to={section.to} className="bottomnav__link">
                    <Icon size={20} />
                    {section.short}
                  </NavLink>
                </li>
              );
            })}
          </ul>
        </nav>
      ) : null}
    </div>
  );
}
