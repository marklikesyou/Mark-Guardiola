from __future__ import annotations

from markguardiola.db.models import DataSource, Event, IngestionRun, Lineup, SchemaVersion, Shot
from markguardiola.ingestion.adapters.football_data_co_uk import FootballDataCoUkAdapter
from markguardiola.ingestion.adapters.pannadata_facts import (
    parse_events,
    parse_lineups,
    parse_shots,
)
from markguardiola.ingestion.adapters.pannadata_parser import PannadataParser
from markguardiola.ingestion.adapters.understat_parser import parse_team_matches
from markguardiola.ingestion.contracts import IngestionScope, RawPayload
from markguardiola.ingestion.pipelines.canonical_writer import CanonicalWriter
from markguardiola.ingestion.pipelines.fact_writer import CanonicalFactWriter


class FootballDataCoUkProcessor:
    def __init__(self, adapter: FootballDataCoUkAdapter, writer: CanonicalWriter) -> None:
        self._adapter = adapter
        self._writer = writer

    async def __call__(
        self,
        source: DataSource,
        run: IngestionRun,
        _schema_version: SchemaVersion,
        payload: RawPayload,
    ) -> int:
        records = self._adapter.parse_matches(payload)
        return await self._writer.write_matches(
            source=source,
            run=run,
            records=records,
            schema_version=_schema_version,
        )


class UnderstatProcessor:
    def __init__(self, writer: CanonicalWriter) -> None:
        self._writer = writer

    async def __call__(
        self,
        source: DataSource,
        run: IngestionRun,
        schema_version: SchemaVersion,
        payload: RawPayload,
    ) -> int:
        records = parse_team_matches(payload)
        if not records:
            return 0
        return await self._writer.write_matches(
            source=source, run=run, schema_version=schema_version, records=records
        )


class PannadataProcessor:
    def __init__(
        self,
        scope: IngestionScope,
        writer: CanonicalWriter,
        fact_writer: CanonicalFactWriter | None = None,
    ) -> None:
        self._scope = scope
        self._parser = PannadataParser()
        self._writer = writer
        self._fact_writer = fact_writer

    async def __call__(
        self,
        source: DataSource,
        run: IngestionRun,
        schema_version: SchemaVersion,
        payload: RawPayload,
    ) -> int:
        matches = self._parser.parse_matches(payload, self._scope)
        count = 0
        if matches:
            count += await self._writer.write_matches(
                source=source,
                run=run,
                records=matches,
                schema_version=schema_version,
            )
        player_matches = self._parser.parse_player_matches(payload, self._scope)
        if player_matches:
            count += await self._writer.write_player_matches(
                source=source,
                run=run,
                schema_version=schema_version,
                records=player_matches,
            )
        if self._fact_writer is not None:
            for model, parser in (
                (Lineup, parse_lineups),
                (Shot, parse_shots),
                (Event, parse_events),
            ):
                count += await self._fact_writer.write(
                    model=model,
                    records=parser(payload, self._scope),
                    source=source,
                    run=run,
                    schema=schema_version,
                )
        return count
