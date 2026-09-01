from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import cast

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as postgres_insert
from sqlalchemy.ext.asyncio import AsyncSession

from markguardiola.db.models import (
    Competition,
    DataQualityIssue,
    DataSource,
    IngestionRun,
    Match,
    OddsSnapshot,
    Player,
    PlayerMatchStat,
    ProviderEntityMap,
    Referee,
    SchemaVersion,
    Season,
    Team,
    TeamMatchStat,
    Venue,
)
from markguardiola.domain.enums import EntityType, QualitySeverity, ResolutionMethod
from markguardiola.domain.roles import football_role
from markguardiola.domain.timing import historical_result_available_at
from markguardiola.entity_resolution.normalization import corroborated_name_match, normalize_name
from markguardiola.ingestion.contracts import (
    CanonicalMatchRecord,
    CanonicalPlayerMatchRecord,
)
from markguardiola.ingestion.contracts.base import CanonicalPlayerIdentity
from markguardiola.ingestion.identity import fact_id
from markguardiola.ingestion.quality import QualityFinding, run_match_quality
from markguardiola.ingestion.quality.result_precedence import accept_result, result_provenance


class BlockingDataQualityError(RuntimeError):
    pass


def _accept_player_photo(player: Player, record: CanonicalPlayerIdentity) -> bool:
    available_at = (player.photo_provenance or {}).get("available_at")
    if not isinstance(available_at, str):
        return True
    try:
        return record.available_at >= datetime.fromisoformat(available_at)
    except ValueError:
        return True


def _kickoff_provenance(
    source: DataSource,
    run: IngestionRun,
    record: CanonicalMatchRecord,
    schema: SchemaVersion | None,
) -> dict[str, object]:
    return {
        "source_id": str(source.id),
        "source": source.key,
        "ingestion_run_id": str(run.id),
        "schema_version_id": str(schema.id) if schema else None,
        "source_record_id": record.source_record_id,
        "source_value": record.kickoff_source_value or record.kickoff_at.isoformat(),
        "kickoff_at": record.kickoff_at.isoformat(),
        "precision": record.kickoff_precision,
        "available_at": record.available_at.isoformat(),
        "policy": record.kickoff_policy,
    }


class CanonicalWriter:
    def __init__(
        self,
        session: AsyncSession,
        *,
        as_of: datetime | None = None,
        deterministic_fact_ids: bool = False,
    ) -> None:
        self._session = session
        self._as_of = as_of
        self._deterministic_fact_ids = deterministic_fact_ids
        self._mapping_cache: dict[tuple[uuid.UUID, EntityType, str], ProviderEntityMap] = {}
        self._team_cache: dict[uuid.UUID, Team] = {}
        self._player_cache: dict[uuid.UUID, Player] = {}
        self._match_cache: dict[uuid.UUID, Match] = {}
        self._player_mapping_owners: dict[tuple[uuid.UUID, uuid.UUID], str] = {}
        self._loaded_player_sources: set[uuid.UUID] = set()

    async def write_player_identities(
        self,
        source: DataSource,
        run: IngestionRun,
        records: list[CanonicalPlayerIdentity],
        schema_version: SchemaVersion | None = None,
    ) -> int:
        for record in records:
            player = await self._player(source, record)
            if record.date_of_birth is not None:
                if player.date_of_birth not in {None, record.date_of_birth}:
                    raise BlockingDataQualityError()
                player.date_of_birth = record.date_of_birth
            if record.given_name is not None:
                player.given_name = record.given_name
            if record.family_name is not None:
                player.family_name = record.family_name
            if record.photo_url is not None and _accept_player_photo(player, record):
                player.photo_url = record.photo_url
                player.photo_provenance = {
                    "source_id": str(source.id),
                    "source": source.key,
                    "provider_player_id": record.player_provider_id,
                    "ingestion_run_id": str(run.id),
                    "schema_version_id": str(schema_version.id) if schema_version else None,
                    "available_at": record.available_at.isoformat(),
                }
            if record.team_provider_id and record.team_name:
                await self._team(
                    source, record.team_provider_id, record.team_name, record.available_at
                )
        return len(records)

    async def resolve_team(
        self, source: DataSource, provider_id: str, name: str, observed_at: datetime
    ) -> Team:
        return await self._team(source, provider_id, name, observed_at)

    async def resolve_mapping(
        self, source: DataSource, entity_type: EntityType, provider_id: str
    ) -> uuid.UUID:
        mapping = await self._mapping(source.id, entity_type, provider_id)
        if mapping is None:
            raise BlockingDataQualityError()
        return mapping.canonical_entity_id

    async def write_matches(
        self,
        *,
        source: DataSource,
        run: IngestionRun,
        records: list[CanonicalMatchRecord],
        schema_version: SchemaVersion | None = None,
    ) -> int:
        findings = run_match_quality(records)
        await self._record_findings(source, run, findings)
        if any(finding.severity == QualitySeverity.BLOCKING for finding in findings):
            raise BlockingDataQualityError()

        count = 0
        competition = await self._competition()
        for record in records:
            season = await self._season(competition, record.season_label)
            home = await self._team(
                source, record.home_team_provider_id, record.home_team_name, record.available_at
            )
            away = await self._team(
                source, record.away_team_provider_id, record.away_team_name, record.available_at
            )
            existing_mapping = await self._mapping(
                source.id, EntityType.MATCH, record.source_record_id
            )
            match = (
                await self._session.get(Match, existing_mapping.canonical_entity_id)
                if existing_mapping is not None
                else None
            )
            if match is None and existing_mapping is None:
                day_start = record.kickoff_at.replace(hour=0, minute=0, second=0, microsecond=0)
                candidates = list(
                    (
                        await self._session.scalars(
                            select(Match).where(
                                Match.season_id == season.id,
                                Match.home_team_id == home.id,
                                Match.away_team_id == away.id,
                                Match.kickoff_at >= day_start,
                                Match.kickoff_at < day_start + timedelta(days=1),
                            )
                        )
                    ).all()
                )
                if len(candidates) > 1:
                    raise BlockingDataQualityError()
                if (
                    not candidates
                    and record.home_score is not None
                    and record.away_score is not None
                ):
                    owned = select(ProviderEntityMap.canonical_entity_id).where(
                        ProviderEntityMap.source_id == source.id,
                        ProviderEntityMap.entity_type == EntityType.MATCH,
                    )
                    candidates = list(
                        (
                            await self._session.scalars(
                                select(Match).where(
                                    Match.season_id == season.id,
                                    Match.home_team_id == home.id,
                                    Match.away_team_id == away.id,
                                    Match.home_score == record.home_score,
                                    Match.away_score == record.away_score,
                                    Match.kickoff_at >= record.kickoff_at - timedelta(days=21),
                                    Match.kickoff_at <= record.kickoff_at + timedelta(days=21),
                                    Match.id.not_in(owned),
                                )
                            )
                        ).all()
                    )
                    if len(candidates) > 1:
                        raise BlockingDataQualityError()
                if candidates:
                    match = candidates[0]
                    await self._add_mapping(
                        source,
                        EntityType.MATCH,
                        record.source_record_id,
                        match.id,
                        f"{record.home_team_name} {record.away_team_name}",
                        record.available_at,
                        confidence=0.98,
                        method=ResolutionMethod.TEMPORAL_CONTEXT,
                    )
            if match is None:
                match = Match(
                    id=existing_mapping.canonical_entity_id if existing_mapping else uuid.uuid4(),
                    season_id=season.id,
                    home_team_id=home.id,
                    away_team_id=away.id,
                    kickoff_at=record.kickoff_at,
                    kickoff_precision=record.kickoff_precision,
                    kickoff_provenance=_kickoff_provenance(source, run, record, schema_version),
                    matchweek=record.matchweek,
                    status=record.status,
                    home_score=record.home_score,
                    away_score=record.away_score,
                    available_at=record.available_at,
                    result_provenance=result_provenance(source, run, record),
                )
                self._session.add(match)
                await self._session.flush()

                if existing_mapping is None:
                    await self._add_mapping(
                        source,
                        EntityType.MATCH,
                        record.source_record_id,
                        match.id,
                        f"{record.home_team_name} {record.away_team_name}",
                        record.available_at,
                    )
                count += 1
            else:
                if match.season_id != season.id:
                    raise BlockingDataQualityError()
                if (
                    record.kickoff_precision == "minute"
                    and record.kickoff_at > (self._as_of or datetime.now(UTC))
                    and record.available_at >= match.available_at
                    and match.status not in {"finished", "awarded", "forfeited"}
                ):
                    match.kickoff_at = record.kickoff_at
                    match.kickoff_precision = record.kickoff_precision
                    match.kickoff_provenance = _kickoff_provenance(
                        source, run, record, schema_version
                    )
                elif match.kickoff_precision == "unknown" and match.kickoff_at == record.kickoff_at:
                    match.kickoff_precision = record.kickoff_precision
                    match.kickoff_provenance = _kickoff_provenance(
                        source, run, record, schema_version
                    )
                if accept_result(self._session, match, source, run, record) and (
                    match.status != "finished" or record.status == "finished"
                ):
                    match.status = record.status
                    match.home_score = record.home_score
                    match.away_score = record.away_score
                match.available_at = max(match.available_at, record.available_at)
            self._match_cache[match.id] = match
            await self._write_match_context(source, record, match)
            await self._write_match_enrichments(
                source=source,
                run=run,
                schema_version=schema_version,
                record=record,
                match=match,
                home=home,
                away=away,
            )
        return count

    async def _write_match_context(
        self, source: DataSource, record: CanonicalMatchRecord, match: Match
    ) -> None:
        if record.matchweek is not None:
            match.matchweek = record.matchweek
        if record.referee_name:
            previous_referee = match.referee_id
            provider_id = (
                record.referee_provider_id or f"name:{normalize_name(record.referee_name)}"
            )
            mapping = await self._mapping(source.id, EntityType.REFEREE, provider_id)
            if mapping is None:
                referee = Referee(
                    display_name=record.referee_name,
                    normalized_name=normalize_name(record.referee_name),
                )
                self._session.add(referee)
                await self._session.flush()
                await self._add_mapping(
                    source,
                    EntityType.REFEREE,
                    provider_id,
                    referee.id,
                    record.referee_name,
                    record.available_at,
                )
                match.referee_id = referee.id
            else:
                match.referee_id = mapping.canonical_entity_id
            if match.referee_id != previous_referee or match.referee_available_at is None:
                match.referee_available_at = record.available_at
        if record.venue_name:
            provider_id = record.venue_provider_id or f"name:{normalize_name(record.venue_name)}"
            mapping = await self._mapping(source.id, EntityType.VENUE, provider_id)
            if mapping is None:
                venue = Venue(name=record.venue_name, city=record.venue_city)
                self._session.add(venue)
                await self._session.flush()
                await self._add_mapping(
                    source,
                    EntityType.VENUE,
                    provider_id,
                    venue.id,
                    record.venue_name,
                    record.available_at,
                )
                match.venue_id = venue.id
            else:
                match.venue_id = mapping.canonical_entity_id

    async def _write_match_enrichments(
        self,
        *,
        source: DataSource,
        run: IngestionRun,
        schema_version: SchemaVersion | None,
        record: CanonicalMatchRecord,
        match: Match,
        home: Team,
        away: Team,
    ) -> None:
        ingested_at = datetime.now(UTC)
        result_available_at = max(
            record.available_at,
            historical_result_available_at(match.kickoff_at, match.kickoff_precision),
        )
        for side, team, opponent, goals_for, goals_against in (
            ("home", home, away, record.home_score, record.away_score),
            ("away", away, home, record.away_score, record.home_score),
        ):
            source_record_id = f"{record.source_record_id}:team:{side}"
            if record.snapshot_key is not None:
                source_record_id += f":{record.snapshot_key}"
            stats = {
                key.removeprefix(f"{side}_"): value
                for key, value in record.stats.items()
                if key.startswith(f"{side}_") and value is not None
            }
            if goals_for is not None:
                stats["goals_for"] = goals_for
            if goals_against is not None:
                stats["goals_against"] = goals_against
            if stats:
                existing_stat = await self._session.scalar(
                    select(TeamMatchStat).where(
                        TeamMatchStat.source_id == source.id,
                        TeamMatchStat.source_record_id == source_record_id,
                    )
                )
                if existing_stat is None:
                    self._session.add(
                        TeamMatchStat(
                            id=fact_id(
                                source.key,
                                "team_match_stats",
                                source_record_id,
                                deterministic=self._deterministic_fact_ids,
                            ),
                            source_id=source.id,
                            ingestion_run_id=run.id,
                            schema_version_id=(schema_version.id if schema_version else None),
                            source_record_id=source_record_id,
                            event_time=match.kickoff_at,
                            available_at=result_available_at,
                            ingested_at=ingested_at,
                            field_provenance={
                                **{key: source.key for key in stats},
                                "kickoff_precision": match.kickoff_precision,
                                "availability_policy": "provider_and_canonical_completion_bound",
                                "canonical_result_agrees": (
                                    record.home_score == match.home_score
                                    and record.away_score == match.away_score
                                ),
                            },
                            match_id=match.id,
                            team_id=team.id,
                            opponent_team_id=opponent.id,
                            is_home=side == "home",
                            stats=stats,
                        )
                    )
                else:
                    if result_available_at < existing_stat.available_at:
                        continue
                    existing_stat.ingestion_run_id = run.id
                    existing_stat.schema_version_id = schema_version.id if schema_version else None
                    existing_stat.event_time = match.kickoff_at
                    existing_stat.available_at = result_available_at
                    existing_stat.ingested_at = ingested_at
                    existing_stat.stats = cast(dict[str, object], stats)
                    existing_stat.field_provenance = {
                        **{key: source.key for key in stats},
                        "kickoff_precision": match.kickoff_precision,
                        "availability_policy": "provider_and_canonical_completion_bound",
                        "canonical_result_agrees": record.home_score == match.home_score
                        and record.away_score == match.away_score,
                    }

        for key, value in record.odds.items():
            source_record_id = f"{record.source_record_id}:odds:{key}"
            existing_odds = await self._session.scalar(
                select(OddsSnapshot).where(
                    OddsSnapshot.source_id == source.id,
                    OddsSnapshot.source_record_id == source_record_id,
                )
            )
            bookmaker, selection = _odds_identity(key)
            if existing_odds is None:
                self._session.add(
                    OddsSnapshot(
                        id=fact_id(
                            source.key,
                            "odds_snapshots",
                            source_record_id,
                            deterministic=self._deterministic_fact_ids,
                        ),
                        source_id=source.id,
                        ingestion_run_id=run.id,
                        schema_version_id=(schema_version.id if schema_version else None),
                        source_record_id=source_record_id,
                        event_time=record.kickoff_at,
                        available_at=record.available_at,
                        ingested_at=ingested_at,
                        field_provenance={"decimal_odds": source.key},
                        match_id=match.id,
                        bookmaker=bookmaker,
                        market="match_result_1x2",
                        selection=selection,
                        decimal_odds=Decimal(str(value)),
                    )
                )
            else:
                existing_odds.ingestion_run_id = run.id
                existing_odds.schema_version_id = schema_version.id if schema_version else None
                existing_odds.available_at = record.available_at
                existing_odds.ingested_at = ingested_at
                existing_odds.decimal_odds = Decimal(str(value))

    async def write_player_matches(
        self,
        *,
        source: DataSource,
        run: IngestionRun,
        schema_version: SchemaVersion,
        records: list[CanonicalPlayerMatchRecord],
    ) -> int:
        count = 0
        pending: list[dict[str, object]] = []
        for record in records:
            match_mapping = await self._mapping(
                source.id, EntityType.MATCH, record.match_provider_id
            )
            if match_mapping is None:
                await self._record_findings(
                    source,
                    run,
                    [
                        QualityFinding(
                            rule_key="player_match.unresolved_match",
                            severity=QualitySeverity.ERROR,
                            message="Player-match statistics reference an unresolved match.",
                            source_record_id=record.source_record_id,
                            evidence={"match_provider_id": record.match_provider_id},
                        )
                    ],
                )
                run.records_rejected += 1
                continue
            team = await self._team(
                source, record.team_provider_id, record.team_name, record.available_at
            )
            player = await self._player(source, record)
            match = self._match_cache.get(match_mapping.canonical_entity_id)
            if match is None:
                match = await self._session.get_one(Match, match_mapping.canonical_entity_id)
                self._match_cache[match.id] = match

            event_time = match.kickoff_at
            available_at = max(
                record.available_at,
                historical_result_available_at(match.kickoff_at, match.kickoff_precision),
            )
            pending.append(
                {
                    "id": fact_id(
                        source.key,
                        "player_match_stats",
                        record.source_record_id,
                        deterministic=self._deterministic_fact_ids,
                    ),
                    "source_id": source.id,
                    "ingestion_run_id": run.id,
                    "schema_version_id": schema_version.id,
                    "source_record_id": record.source_record_id,
                    "event_time": event_time,
                    "available_at": available_at,
                    "ingested_at": datetime.now(UTC),
                    "field_provenance": {
                        **{key: source.key for key in record.stats},
                        "kickoff_precision": match.kickoff_precision,
                        "availability_policy": "provider_and_canonical_completion_bound",
                    },
                    "match_id": match.id,
                    "team_id": team.id,
                    "player_id": player.id,
                    "minutes": record.minutes,
                    "started": record.started,
                    "football_position": record.position,
                    "stats": record.stats,
                }
            )
            if len(pending) >= 1000:
                await self._upsert_player_stats(pending)
                count += len(pending)
                pending.clear()
        if pending:
            await self._upsert_player_stats(pending)
            count += len(pending)
        return count

    async def _upsert_player_stats(self, records: list[dict[str, object]]) -> None:
        statement = postgres_insert(PlayerMatchStat)
        mutable_columns = {
            key: getattr(statement.excluded, key)
            for key in records[0]
            if key not in {"id", "source_id", "source_record_id"}
        }
        await self._session.execute(
            statement.on_conflict_do_update(
                index_elements=["source_id", "source_record_id"],
                set_=mutable_columns,
            ),
            records,
        )

    async def _competition(self) -> Competition:
        competition = await self._session.scalar(
            select(Competition).where(
                Competition.name == "Serie A", Competition.country_code == "ITA"
            )
        )
        if competition is None:
            competition = Competition(
                name="Serie A", country_code="ITA", competition_type="league", active=True
            )
            self._session.add(competition)
            await self._session.flush()
        return competition

    async def _season(self, competition: Competition, label: str) -> Season:
        normalized_label = label.replace("/", "-")
        season = await self._session.scalar(
            select(Season).where(
                Season.competition_id == competition.id, Season.label == normalized_label
            )
        )
        if season is None:
            parts = normalized_label.split("-")
            if len(parts) != 2:
                raise ValueError()
            start_year, end_year = map(int, parts)
            season = Season(
                competition_id=competition.id,
                label=f"{start_year:04d}-{end_year:04d}",
                start_date=date(start_year, 7, 1),
                end_date=date(end_year, 6, 30),
                current=False,
            )
            self._session.add(season)
            await self._session.flush()
        return season

    async def _team(
        self,
        source: DataSource,
        provider_id: str,
        name: str,
        seen_at: datetime,
    ) -> Team:
        mapping = await self._mapping(source.id, EntityType.TEAM, provider_id)
        if mapping is not None:
            mapping.last_seen_at = max(mapping.last_seen_at, seen_at)
            if mapping.canonical_entity_id not in self._team_cache:
                self._team_cache[mapping.canonical_entity_id] = await self._session.get_one(
                    Team, mapping.canonical_entity_id
                )
            return self._team_cache[mapping.canonical_entity_id]

        normalized = normalize_name(name, entity_type="team")
        teams = list(
            await self._session.scalars(select(Team).where(Team.normalized_name == normalized))
        )
        if len(teams) > 1:
            raise BlockingDataQualityError()
        if teams:
            team = teams[0]
            confidence = 0.98
            method = ResolutionMethod.EXACT
        else:
            team = Team(
                name=name,
                normalized_name=normalized,
                short_name=None,
                country_code="ITA",
                active=True,
            )
            self._session.add(team)
            await self._session.flush()
            confidence = 1.0
            method = ResolutionMethod.MANUAL
        await self._add_mapping(
            source,
            EntityType.TEAM,
            provider_id,
            team.id,
            name,
            seen_at,
            confidence=confidence,
            method=method,
        )
        self._team_cache[team.id] = team
        return team

    async def _player(
        self,
        source: DataSource,
        record: CanonicalPlayerMatchRecord | CanonicalPlayerIdentity,
    ) -> Player:
        await self._load_player_mappings(source.id)
        mapping = await self._mapping(source.id, EntityType.PLAYER, record.player_provider_id)
        if mapping is not None:
            owner = self._player_mapping_owners.get((source.id, mapping.canonical_entity_id))
            if owner is not None and owner != record.player_provider_id:
                separate = Player(
                    display_name=record.player_name,
                    normalized_name=normalize_name(record.player_name),
                    primary_position=football_role(record.position),
                    active=True,
                )
                self._session.add(separate)
                await self._session.flush()
                mapping.canonical_entity_id = separate.id
                mapping.mapping_method = ResolutionMethod.EXISTING_MAPPING
                mapping.manually_confirmed = False
                mapping.confidence = 1.0
                self._player_mapping_owners[(source.id, separate.id)] = record.player_provider_id
                self._player_cache[separate.id] = separate
            latest_observation = record.available_at >= mapping.last_seen_at
            mapping.last_seen_at = max(mapping.last_seen_at, record.available_at)
            if mapping.canonical_entity_id not in self._player_cache:
                self._player_cache[mapping.canonical_entity_id] = await self._session.get_one(
                    Player, mapping.canonical_entity_id
                )
            player = self._player_cache[mapping.canonical_entity_id]
            if latest_observation:
                player.display_name = record.player_name
                player.normalized_name = normalize_name(record.player_name)
            known_position = football_role(record.position)
            if known_position is not None and (
                latest_observation or football_role(player.primary_position) is None
            ):
                player.primary_position = known_position
            return player

        normalized = normalize_name(record.player_name)
        players = list(
            await self._session.scalars(select(Player).where(Player.normalized_name == normalized))
        )

        match_mapping = (
            await self._mapping(source.id, EntityType.MATCH, record.match_provider_id)
            if record.match_provider_id is not None
            else None
        )
        team_mapping = (
            await self._mapping(source.id, EntityType.TEAM, record.team_provider_id)
            if record.team_provider_id
            else None
        )
        corroborated: list[Player] = []
        if match_mapping is not None and team_mapping is not None:
            fixture_players = list(
                await self._session.scalars(
                    select(Player)
                    .join(PlayerMatchStat, PlayerMatchStat.player_id == Player.id)
                    .where(
                        PlayerMatchStat.match_id == match_mapping.canonical_entity_id,
                        PlayerMatchStat.team_id == team_mapping.canonical_entity_id,
                    )
                    .distinct()
                )
            )
            corroborated = [
                person
                for person in fixture_players
                if (source.id, person.id) not in self._player_mapping_owners
                and corroborated_name_match(record.player_name, person.display_name)
                and not (
                    isinstance(record, CanonicalPlayerIdentity)
                    and record.date_of_birth is not None
                    and person.date_of_birth is not None
                    and record.date_of_birth != person.date_of_birth
                )
            ]
        candidate = corroborated[0] if len(corroborated) == 1 else None
        if candidate is not None:
            player = candidate
            confidence = 0.98
            method = ResolutionMethod.TEMPORAL_CONTEXT
        else:
            player = Player(
                display_name=record.player_name,
                normalized_name=normalized,
                primary_position=football_role(record.position),
                active=True,
            )
            self._session.add(player)
            await self._session.flush()
            review_candidates = {person.id for person in [*players, *corroborated]}
            if not review_candidates and len(normalized.split()) >= 2:
                same_surname = await self._session.scalars(
                    select(Player).where(
                        Player.normalized_name.endswith(" " + normalized.split()[-1]),
                        Player.id != player.id,
                    )
                )
                review_candidates = {person.id for person in same_surname}
            if review_candidates:
                self._session.add(
                    DataQualityIssue(
                        source_id=source.id,
                        entity_type="player",
                        entity_id=player.id,
                        provider_record_id=record.player_provider_id,
                        rule_key="identity.cross_source_player_review",
                        severity="warning",
                        message=(
                            "Same-name identities need corroboration; kept separate for review."
                        ),
                        evidence={"candidate_ids": sorted(str(item) for item in review_candidates)},
                    )
                )
            confidence = 1.0
            method = ResolutionMethod.EXACT
        await self._add_mapping(
            source,
            EntityType.PLAYER,
            record.player_provider_id,
            player.id,
            record.player_name,
            record.available_at,
            confidence=confidence,
            method=method,
        )
        self._player_cache[player.id] = player
        self._player_mapping_owners[(source.id, player.id)] = record.player_provider_id
        return player

    async def _load_player_mappings(self, source_id: uuid.UUID) -> None:
        if source_id in self._loaded_player_sources:
            return
        mappings = (
            await self._session.scalars(
                select(ProviderEntityMap)
                .where(
                    ProviderEntityMap.source_id == source_id,
                    ProviderEntityMap.entity_type == EntityType.PLAYER,
                )
                .order_by(ProviderEntityMap.first_seen_at, ProviderEntityMap.provider_entity_id)
            )
        ).all()
        for mapping in mappings:
            self._mapping_cache[(source_id, EntityType.PLAYER, mapping.provider_entity_id)] = (
                mapping
            )
            self._player_mapping_owners.setdefault(
                (source_id, mapping.canonical_entity_id), mapping.provider_entity_id
            )
        self._loaded_player_sources.add(source_id)

    async def _mapping(
        self, source_id: uuid.UUID, entity_type: EntityType, provider_id: str
    ) -> ProviderEntityMap | None:
        key = (source_id, entity_type, provider_id)
        if key in self._mapping_cache:
            return self._mapping_cache[key]
        result = await self._session.scalar(
            select(ProviderEntityMap).where(
                ProviderEntityMap.source_id == source_id,
                ProviderEntityMap.entity_type == entity_type,
                ProviderEntityMap.provider_entity_id == provider_id,
            )
        )
        if result is not None:
            self._mapping_cache[key] = result
        return result

    async def _add_mapping(
        self,
        source: DataSource,
        entity_type: EntityType,
        provider_id: str,
        canonical_id: uuid.UUID,
        name: str,
        seen_at: datetime,
        *,
        confidence: float = 1.0,
        method: ResolutionMethod = ResolutionMethod.MANUAL,
    ) -> None:
        mapping = ProviderEntityMap(
            source_id=source.id,
            entity_type=entity_type,
            provider_entity_id=provider_id,
            canonical_entity_id=canonical_id,
            normalized_name=normalize_name(
                name, entity_type="team" if entity_type == EntityType.TEAM else "player"
            ),
            confidence=confidence,
            mapping_method=method,
            manually_confirmed=method == ResolutionMethod.MANUAL,
            first_seen_at=seen_at,
            last_seen_at=seen_at,
        )
        self._session.add(mapping)
        self._mapping_cache[(source.id, entity_type, provider_id)] = mapping

    async def _record_findings(
        self,
        source: DataSource,
        run: IngestionRun,
        findings: list[QualityFinding],
    ) -> None:
        for finding in findings:
            self._session.add(
                DataQualityIssue(
                    ingestion_run_id=run.id,
                    source_id=source.id,
                    rule_key=finding.rule_key,
                    severity=finding.severity,
                    provider_record_id=finding.source_record_id,
                    message=finding.message,
                    evidence=finding.evidence,
                )
            )


def _odds_identity(key: str) -> tuple[str, str]:
    for bookmaker in ("bet365", "pinnacle", "market_average"):
        prefix = f"{bookmaker}_"
        if key.startswith(prefix):
            return bookmaker, key.removeprefix(prefix)
    return "unknown", key
