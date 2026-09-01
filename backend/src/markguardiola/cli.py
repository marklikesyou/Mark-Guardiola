import asyncio
import json
from datetime import datetime
from pathlib import Path

import typer

app = typer.Typer(
    no_args_is_help=True,
    pretty_exceptions_show_locals=False,
    help="MarkGuardiola operational commands",
)


@app.command()
def version() -> None:

    from markguardiola import __version__

    typer.echo(__version__)


@app.command()
def build_bundle(
    destination: Path = typer.Argument(...),
    bundle_version: str = typer.Option(..., "--bundle-version"),
    reconstruction_cutoff: str | None = typer.Option(
        None, help="Preserve the original reconstruction clock when repackaging a raw rebuild."
    ),
) -> None:

    from markguardiola.core.config import get_settings
    from markguardiola.release.bundle import build_bundle as build

    cutoff = None
    if reconstruction_cutoff is not None:
        try:
            cutoff = datetime.fromisoformat(reconstruction_cutoff)
        except ValueError:
            raise typer.BadParameter("") from None
        if cutoff.tzinfo is None:
            raise typer.BadParameter("")
    manifest = build(
        get_settings(),
        destination,
        version=bundle_version,
        reconstruction_cutoff=cutoff,
    )
    typer.echo(
        json.dumps({"version": manifest.version, "row_counts": manifest.row_counts}, indent=2)
    )


@app.command()
def verify_bundle(
    bundle: Path = typer.Argument(..., exists=True, dir_okay=False),
    sha256: str = typer.Option(..., help="Checksum obtained from a trusted bundle producer."),
) -> None:

    from markguardiola.release.bundle import verify_bundle as verify

    manifest = verify(bundle, sha256)
    typer.echo(
        json.dumps({"version": manifest.version, "row_counts": manifest.row_counts}, indent=2)
    )


@app.command()
def restore_bundle(
    bundle: Path = typer.Argument(..., exists=True, dir_okay=False),
    sha256: str = typer.Option(..., help="Checksum obtained from a trusted bundle producer."),
) -> None:

    from markguardiola.core.config import get_settings
    from markguardiola.release.bundle import restore_bundle as restore

    manifest = restore(get_settings(), bundle, expected_sha256=sha256)
    typer.echo(f"Restored full bootstrap {manifest.version}")


@app.command()
def worker() -> None:

    from redis import Redis
    from rq import Queue, Worker

    from markguardiola.core.config import get_settings

    connection = Redis.from_url(get_settings().redis_url)
    queue = Queue("markguardiola", connection=connection)
    Worker([queue], connection=connection).work()


@app.command()
def rebuild_raw(
    bundle: Path = typer.Argument(..., exists=True, dir_okay=False),
    sha256: str = typer.Option(..., help="SHA-256 from a trusted producer of the archived inputs."),
    data_only: bool = typer.Option(
        False, "--data-only", help="Rebuild canonical facts only; not a complete installation."
    ),
) -> None:

    from markguardiola.core.config import get_settings
    from markguardiola.db.session import get_engine, get_session_factory
    from markguardiola.ml.pipeline import rebuild_models
    from markguardiola.release.bundle import restore_raw_inputs
    from markguardiola.release.replay import replay_raw_inputs

    settings = get_settings()
    manifest = restore_raw_inputs(settings, bundle, expected_sha256=sha256)

    async def reconstruct() -> dict[str, object]:
        try:
            result = await replay_raw_inputs(settings, manifest, bundle_sha256=sha256)
            if not data_only:
                result["models"] = await rebuild_models(
                    {
                        "include_external": True,
                        "random_seed": 2026,
                        "as_of": manifest.replay_cutoff.isoformat(),
                    }
                )
            else:
                result["models"] = "not built: --data-only is a diagnostic operation"
            return result
        finally:
            await get_engine().dispose()
            get_session_factory.cache_clear()
            get_engine.cache_clear()

    typer.echo(json.dumps(asyncio.run(reconstruct()), indent=2))


@app.command()
def install_data() -> None:

    from markguardiola.release.install import main

    main()


@app.command()
def install_status() -> None:

    from markguardiola.core.config import get_settings
    from markguardiola.release.install import assert_installation_ready

    typer.echo(json.dumps(assert_installation_ready(get_settings()), indent=2))


@app.command()
def seed_tutorial() -> None:

    from markguardiola.db.session import get_session_factory
    from markguardiola.release.tutorial import provision_tutorial_league

    async def run() -> dict[str, object]:
        async with get_session_factory()() as session:
            result = await provision_tutorial_league(session)
            await session.commit()
            return result

    typer.echo(json.dumps(asyncio.run(run()), indent=2))


@app.command()
def tutorial_photos() -> None:

    from markguardiola.core.config import get_settings
    from markguardiola.release.tutorial_photos import enrich_tutorial_photos

    typer.echo(json.dumps(asyncio.run(enrich_tutorial_photos(get_settings())), indent=2))


@app.command()
def bootstrap_data(
    first_start_year: int = typer.Option(2013, min=1993, max=2100),
    include_pannadata: bool = typer.Option(True, "--pannadata/--no-pannadata"),
    include_understat: bool = typer.Option(True, "--understat/--no-understat"),
    pannadata_types: list[str] | None = typer.Option(None, "--pannadata-type"),
) -> None:

    from markguardiola.core.config import get_settings
    from markguardiola.ingestion.pipelines.bootstrap import bootstrap

    summary = asyncio.run(
        bootstrap(
            get_settings(),
            first_start_year=first_start_year,
            include_pannadata=include_pannadata,
            include_understat=include_understat,
            pannadata_types=tuple(pannadata_types)
            if pannadata_types
            else ("fixtures", "player_stats", "lineups", "shots", "events"),
        )
    )
    typer.echo(
        json.dumps(
            {
                "ingestion_runs": summary.runs,
                "unavailable_enrichments": summary.unavailable_enrichments,
            },
            indent=2,
        )
    )


@app.command()
def reconcile_data(apply: bool = typer.Option(False, "--apply")) -> None:

    from markguardiola.db.session import get_session_factory
    from markguardiola.entity_resolution.reconcile import reconcile_identities

    async def run() -> dict[str, object]:
        async with get_session_factory()() as session, session.begin():
            result = await reconcile_identities(session, apply=apply)
            return {
                "applied": apply,
                "team_redirects": {str(k): str(v) for k, v in result.team_redirects.items()},
                "match_redirect_count": len(result.match_redirects),
            }

    typer.echo(json.dumps(asyncio.run(run()), indent=2))


@app.command()
def train_models(
    include_external: bool = typer.Option(True, "--external/--no-external"),
    targets: list[str] | None = typer.Option(None, "--target"),
) -> None:

    from markguardiola.ml.pipeline import rebuild_models

    result = asyncio.run(rebuild_models({"include_external": include_external, "targets": targets}))
    typer.echo(json.dumps(result, indent=2))


@app.command()
def predict() -> None:

    from markguardiola.ml.pipeline import predict_upcoming

    typer.echo(json.dumps(asyncio.run(predict_upcoming()), indent=2))


@app.command()
def materialize_memberships() -> None:

    from markguardiola.db.session import get_session_factory
    from markguardiola.entity_resolution.periods import materialize_membership_periods

    async def run() -> None:
        async with get_session_factory()() as session:
            count = await materialize_membership_periods(session)
            await session.commit()
            typer.echo(f"Materialized {count} observed membership spans.")

    asyncio.run(run())


@app.command()
def enrich_optional(
    season: str = typer.Option(...),
    source: list[str] | None = typer.Option(None),
    allow_browser: bool = typer.Option(False, "--allow-browser"),
) -> None:

    from markguardiola.core.config import get_settings
    from markguardiola.ingestion.adapters.soccerdata_optional import PROVIDERS
    from markguardiola.ingestion.pipelines.optional import ingest_optional

    typer.echo(
        json.dumps(
            asyncio.run(
                ingest_optional(
                    get_settings(),
                    season,
                    tuple(source or PROVIDERS),
                    allow_browser=allow_browser,
                )
            ),
            indent=2,
        )
    )


@app.command()
def backtest_train(
    season: str = typer.Option(..., help="Completed evaluation season, excluded from all fitting."),
    include_external: bool = typer.Option(True, "--external/--no-external"),
) -> None:

    from markguardiola.backtesting.training import train_historical_models

    typer.echo(
        json.dumps(
            asyncio.run(train_historical_models(season, include_external=include_external)),
            indent=2,
        )
    )


@app.command()
def backtest_decisions(
    season: str = typer.Option(...),
    weeks: int = typer.Option(8, min=1, max=40),
    drafts_per_week: int = typer.Option(2, min=1, max=20),
    simulations: int = typer.Option(1000, min=100, max=100_000),
    seed: int = 2026,
    include_external: bool = typer.Option(True, "--external/--no-external"),
    training_snapshot: str | None = typer.Option(
        None, help="Reuse a verified immutable training SHA-256."
    ),
) -> None:

    from markguardiola.backtesting.replay import run_decision_backtest

    typer.echo(
        json.dumps(
            asyncio.run(
                run_decision_backtest(
                    season,
                    maximum_weeks=weeks,
                    drafts_per_week=drafts_per_week,
                    simulations=simulations,
                    seed=seed,
                    include_external=include_external,
                    training_snapshot_hash=training_snapshot,
                )
            ),
            indent=2,
        )
    )
