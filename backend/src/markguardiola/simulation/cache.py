from __future__ import annotations

import hashlib
import json
import tempfile
from dataclasses import asdict, fields
from functools import lru_cache
from pathlib import Path

import numpy as np
import structlog

from markguardiola.simulation.engine import FixtureSimulator, _summarize_player
from markguardiola.simulation.models import FixtureForecast, FixtureSimulationResult, PlayerSamples

logger = structlog.get_logger(__name__)
ARRAY_FIELDS = tuple(
    field.name for field in fields(PlayerSamples) if field.name not in {"player_id", "team_id"}
)


@lru_cache(maxsize=1)
def _implementation_digest() -> str:
    root = Path(__file__).parent
    content = b"".join(
        (root / name).read_bytes() for name in ("engine.py", "models.py", "cache.py")
    )
    return hashlib.sha256(content + np.__version__.encode()).hexdigest()


class FixtureScenarioCache:
    def __init__(self, root: Path) -> None:
        self._root = root

    def get_or_simulate(
        self, forecast: FixtureForecast, *, count: int, seed: int
    ) -> FixtureSimulationResult:
        descriptor = {
            "format": 1,
            "implementation": _implementation_digest(),
            "forecast": asdict(forecast),
            "count": count,
            "seed": seed,
        }
        encoded = json.dumps(descriptor, sort_keys=True, separators=(",", ":"))
        key = hashlib.sha256(encoded.encode()).hexdigest()
        path = self._root / key[:2] / f"{key}.npz"
        if path.is_file():
            try:
                return self._load(path, forecast, count, seed, encoded)
            except (ValueError, OSError, KeyError):
                logger.warning("simulation_cache_invalid", key=key)
        result = FixtureSimulator().simulate(forecast, simulation_count=count, seed=seed)
        arrays: dict[str, np.ndarray] = {
            "descriptor": np.array(encoded),
            "home_goals": result.home_goals,
            "away_goals": result.away_goals,
        }
        for index, player in enumerate(forecast.players):
            sample = result.player_samples[player.player_id]
            for name in ARRAY_FIELDS:
                arrays[f"player_{index}_{name}"] = getattr(sample, name)
        path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            dir=path.parent, prefix=".scenario-", suffix=".npz", delete=False
        ) as temporary:
            temporary_path = Path(temporary.name)
            try:
                np.savez_compressed(temporary, allow_pickle=False, **arrays)
            except BaseException:
                temporary_path.unlink(missing_ok=True)
                raise
        temporary_path.replace(path)
        return result

    @staticmethod
    def _load(
        path: Path, forecast: FixtureForecast, count: int, seed: int, descriptor: str
    ) -> FixtureSimulationResult:
        samples: dict[str, PlayerSamples] = {}
        with np.load(path, allow_pickle=False) as archive:
            if archive["descriptor"].item() != descriptor:
                raise ValueError()
            home = _array(archive["home_goals"], count, np.dtype(np.int16))
            away = _array(archive["away_goals"], count, np.dtype(np.int16))
            for index, player in enumerate(forecast.players):
                values = {
                    name: _array(
                        archive[f"player_{index}_{name}"],
                        count,
                        np.dtype(bool if name in {"started", "clean_sheet"} else np.int16),
                    )
                    for name in ARRAY_FIELDS
                }
                samples[player.player_id] = PlayerSamples(
                    player_id=player.player_id, team_id=player.team_id, **values
                )
        return FixtureSimulationResult(
            match_id=forecast.match_id,
            simulation_count=count,
            seed=seed,
            home_goals=home,
            away_goals=away,
            player_samples=samples,
            summaries={
                player_id: _summarize_player(sample) for player_id, sample in samples.items()
            },
        )


def _array(value: np.ndarray, count: int, dtype: np.dtype) -> np.ndarray:
    if value.shape != (count,) or value.dtype != dtype:
        raise ValueError()
    return value
