from typing import Literal

FootballRole = Literal["GK", "DEF", "MID", "FWD"]

_POSITIONS: dict[str, FootballRole] = {
    "gk": "GK",
    "goalkeeper": "GK",
    "portiere": "GK",
    "por": "GK",
    "def": "DEF",
    "defender": "DEF",
    "difensore": "DEF",
    "wing back": "DEF",
    "full back": "DEF",
    "centre back": "DEF",
    "center back": "DEF",
    "mid": "MID",
    "midfielder": "MID",
    "centrocampista": "MID",
    "defensive midfielder": "MID",
    "attacking midfielder": "MID",
    "fwd": "FWD",
    "forward": "FWD",
    "striker": "FWD",
    "attaccante": "FWD",
}


def football_role(position: str | None) -> FootballRole | None:

    if not position:
        return None
    normalized = " ".join(position.casefold().replace("-", " ").split())
    return _POSITIONS.get(normalized)
