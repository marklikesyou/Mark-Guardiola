from __future__ import annotations

import re
import unicodedata

_TEAM_SUFFIXES = {"fc", "calcio", "club", "ac", "ssc", "ss", "as", "cf"}


_TEAM_ALIASES = {
    "acf fiorentina": "fiorentina",
    "ars et labor ferrara": "spal",
    "atalanta bergamasca": "atalanta",
    "bologna 1909": "bologna",
    "carpi 1909": "carpi",
    "chievoverona": "chievo",
    "como 1907": "como",
    "delfino pescara 1936": "pescara",
    "genoa cfc": "genoa",
    "hellas verona": "verona",
    "internazionale": "inter",
    "internazionale milano": "inter",
    "parma 1913": "parma",
    "pisa sporting": "pisa",
    "spal 2013": "spal",
    "uc sampdoria": "sampdoria",
    "us cremonese": "cremonese",
    "us lecce": "lecce",
    "us salernitana 1919": "salernitana",
    "us sassuolo": "sassuolo",
}


def normalize_name(value: str, *, entity_type: str = "player") -> str:
    normalized = unicodedata.normalize("NFKD", value)
    without_marks = "".join(char for char in normalized if not unicodedata.combining(char))
    casefolded = without_marks.casefold()
    if entity_type == "team":
        casefolded = re.sub(
            r"(?:\b[a-z]\.){2,}",
            lambda match: match.group(0).replace(".", ""),
            casefolded,
        )
    tokens = re.findall(r"[a-z0-9]+", casefolded)
    if entity_type == "team":
        tokens = [token for token in tokens if token not in _TEAM_SUFFIXES]
    result = " ".join(tokens)
    return _TEAM_ALIASES.get(result, result) if entity_type == "team" else result


def corroborated_name_match(left: str, right: str) -> bool:

    first, second = normalize_name(left).split(), normalize_name(right).split()
    if first == second:
        return True
    return bool(
        len(first) >= 2
        and len(second) >= 2
        and first[1:] == second[1:]
        and first[0][0] == second[0][0]
        and (len(first[0]) == 1 or len(second[0]) == 1)
    )
