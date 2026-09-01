from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class InsightEvidence:
    key: str
    value: float
    impact: float
    reliability: float
    source_feature: str


@dataclass(frozen=True, slots=True)
class Explanation:
    text: str
    evidence_key: str
    source_feature: str
    confidence: float


class ExplanationEngine:
    def explain(
        self,
        evidence: list[InsightEvidence],
        *,
        maximum_reasons: int = 3,
        overall_confidence: float,
    ) -> tuple[Explanation, ...]:
        if maximum_reasons < 1:
            raise ValueError()
        supported: list[tuple[float, Explanation]] = []
        for item in evidence:
            text = _render(item)
            if text is None:
                continue
            confidence = max(0.0, min(item.reliability, 1.0))
            supported.append(
                (
                    abs(item.impact) * confidence,
                    Explanation(
                        text=text,
                        evidence_key=item.key,
                        source_feature=item.source_feature,
                        confidence=confidence,
                    ),
                )
            )
        supported.sort(key=lambda item: (-item[0], item[1].evidence_key))
        reasons = [item[1] for item in supported[:maximum_reasons]]
        if overall_confidence < 0.5:
            caveat = Explanation(
                text=(
                    "La stima ha affidabilità limitata: considera un intervallo "
                    "di risultati più ampio."
                ),
                evidence_key="low_confidence",
                source_feature="prediction_reliability",
                confidence=overall_confidence,
            )
            if len(reasons) >= maximum_reasons:
                reasons[-1] = caveat
            else:
                reasons.append(caveat)
        return tuple(reasons)


def _render(evidence: InsightEvidence) -> str | None:
    value = evidence.value
    if evidence.key == "player_expected_points":
        return f"Con le regole della tua lega, la stima individuale è di {value:.1f} fantapunti."
    if evidence.key == "player_unavailable" and value == 1:
        return "Risulta indisponibile nelle informazioni note al momento del calcolo."
    if evidence.key == "scoring_appearance_probability":
        if value >= 0.75:
            return (
                "Ha un'alta probabilità di raggiungere i minuti richiesti dalla lega per il voto."
            )
        if value <= 0.25:
            return (
                "Ha una bassa probabilità di raggiungere i minuti richiesti dalla lega per il voto."
            )
    if evidence.key == "start_probability" and value >= 0.75:
        return "Ha un'alta probabilità di partire titolare."
    if evidence.key == "appearance_probability" and value >= 0.75:
        return "Ha un'alta probabilità di scendere in campo e prendere voto."
    if evidence.key == "expected_minutes" and value >= 65:
        return f"La proiezione media è di circa {value:.0f} minuti."
    if evidence.key == "opponent_xg_against_percentile" and value >= 0.65:
        return "L'avversario sta concedendo occasioni sopra la media del campionato."
    if evidence.key == "shot_volume_trend" and value > 0:
        return "Il volume recente di tiri è in crescita rispetto al suo livello abituale."
    if evidence.key == "goal_probability" and value >= 0.2:
        return f"La probabilità stimata di segnare è del {value:.0%}."
    if evidence.key == "clean_sheet_probability" and value >= 0.35:
        return "La simulazione assegna alla sua squadra una buona probabilità di porta inviolata."
    if evidence.key == "lineup_expected_delta" and value > 0:
        return f"La simulazione migliora la formazione di circa {value:.1f} punti attesi."
    if evidence.key == "role_flexibility_delta" and value > 0:
        return "Aumenta il numero di soluzioni di formazione legali disponibili."
    if evidence.key == "lineup_high_appearance_count" and value >= 1:
        return (
            f"{int(value)} degli 11 titolari hanno almeno l'80% "
            "di probabilità stimata di prendere voto."
        )
    if evidence.key == "lineup_expected_substitutions" and value > 0.1:
        return f"La panchina copre in media {value:.1f} assenze con cambi consentiti dalla lega."
    if evidence.key == "lineup_modifier_points" and value != 0:
        return f"Il modificatore configurato contribuisce per circa {value:+.1f} punti attesi."
    return None
