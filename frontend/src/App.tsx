import { Component, type ReactNode } from "react";
import {
  createBrowserRouter,
  Navigate,
  Outlet,
  RouterProvider,
} from "react-router-dom";
import { AppLayout } from "./app/AppLayout";
import { LeagueProvider, useLeagueContext } from "./app/LeagueContext";
import { PlayerPhotoPolicyProvider } from "./app/PlayerPhotoPolicy";
import { Providers } from "./app/providers";
import { GiornataPage } from "./features/giornata/GiornataPage";
import { GiocatoreDetailPage } from "./features/giocatori/GiocatoreDetailPage";
import { GiocatoriPage } from "./features/giocatori/GiocatoriPage";
import { ImportPage } from "./features/imports/ImportPage";
import { ManualAddPage } from "./features/imports/ManualAddPage";
import { LegaPage } from "./features/lega/LegaPage";
import { LeaguePickerPage } from "./features/leagues/LeaguePickerPage";
import { BenvenutoPage } from "./features/onboarding/BenvenutoPage";
import { MercatoPage } from "./features/mercato/MercatoPage";
import { RosaPage } from "./features/rosa/RosaPage";
import { it } from "./lib/strings";
import { EmptyState, Skeleton } from "./ui/primitives";

class RouteErrorBoundary extends Component<
  { children: ReactNode },
  { failed: boolean }
> {
  state = { failed: false };

  static getDerivedStateFromError() {
    return { failed: true };
  }

  render() {
    if (this.state.failed) {
      return (
        <EmptyState title={it.app.error} body={it.app.errorBody}>
          <button
            type="button"
            className="btn btn--primary"
            onClick={() => window.location.reload()}
          >
            {it.app.retry}
          </button>
        </EmptyState>
      );
    }
    return this.props.children;
  }
}





function RequireLeague() {
  const { leaguesLoading, leaguesError, leagues, leagueId, refetchLeagues,
    leagueLoading, leagueError, refetchLeague } =
    useLeagueContext();

  if (leaguesLoading) {
    return <Skeleton lines={6} />;
  }
  if (leaguesError) {
    return (
      <EmptyState title={it.app.error} body={it.app.offline}>
        <button type="button" className="btn btn--primary" onClick={refetchLeagues}>
          {it.app.retry}
        </button>
      </EmptyState>
    );
  }
  if (leagues.length === 0) {
    return <Navigate to="/benvenuto" replace />;
  }
  if (leagueId === null) {
    return <Navigate to="/leghe" replace />;
  }


  if (leagueLoading) return <Skeleton lines={6} />;
  if (leagueError) {
    return (
      <EmptyState title={it.app.error} body={it.app.offline}>
        <button type="button" className="btn btn--primary" onClick={refetchLeague}>
          {it.app.retry}
        </button>
      </EmptyState>
    );
  }
  return (
    <PlayerPhotoPolicyProvider>
      <Outlet />
    </PlayerPhotoPolicyProvider>
  );
}

function RouteError() {
  return (
    <EmptyState title={it.app.error} body={it.app.errorBody}>
      <button
        type="button"
        className="btn btn--primary"
        onClick={() => window.location.reload()}
      >
        {it.app.retry}
      </button>
    </EmptyState>
  );
}

const router = createBrowserRouter([
  {
    element: (
      <LeagueProvider>
        <AppLayout />
      </LeagueProvider>
    ),
    errorElement: <RouteError />,
    children: [
      { path: "/benvenuto", element: <BenvenutoPage /> },
      { path: "/leghe", element: <LeaguePickerPage /> },
      {
        element: <RequireLeague />,
        errorElement: <RouteError />,
        children: [
          { path: "/", element: <Navigate to="/giornata" replace /> },
          { path: "/giornata", element: <GiornataPage /> },
          { path: "/rosa", element: <RosaPage /> },
          { path: "/rosa/importa", element: <ImportPage kind="roster" /> },
          {
            path: "/rosa/importa/avversaria",
            element: <ImportPage kind="opponent" />,
          },
          { path: "/rosa/aggiungi", element: <ManualAddPage target="roster" /> },
          {
            path: "/rosa/aggiungi/avversaria",
            element: <ManualAddPage target="opponent" />,
          },
          { path: "/mercato", element: <MercatoPage /> },
          { path: "/mercato/importa", element: <ImportPage kind="market" /> },
          { path: "/mercato/aggiungi", element: <ManualAddPage target="market" /> },
          { path: "/giocatori", element: <GiocatoriPage /> },
          { path: "/giocatori/:playerId", element: <GiocatoreDetailPage /> },
          { path: "/lega", element: <LegaPage /> },
          { path: "*", element: <Navigate to="/giornata" replace /> },
        ],
      },
    ],
  },
]);

export default function App() {
  return (
    <Providers>
      <RouteErrorBoundary>
        <RouterProvider router={router} />
      </RouteErrorBoundary>
    </Providers>
  );
}
