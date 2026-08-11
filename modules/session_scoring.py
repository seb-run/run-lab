"""
seb-metrics — modules/session_scoring.py
========================================
Scoring des séances réalisées vs plan : réussie / partielle / échouée.

Pour chaque jour du plan ayant une séance réelle attachée, calcule :
  - un score volume   (km réalisés vs km prévus)
  - un score allure   (allure réalisée vs allure cible, laps rapides pour la qualité)
  - un score global 0-100 et un verdict : 'success' | 'partial' | 'failed'

Attaché au jour sous la clé `score` :
  {
    "points": 87,
    "verdict": "success",
    "volume_pct": 98,          # % du volume prévu réalisé
    "volume_points": 100,
    "pace_points": 72,          # None si pas d'allure cible
    "pace_target_s": 255,       # sec/km
    "pace_actual_s": 261,       # sec/km (laps rapides pour la qualité)
    "pace_delta_s": 6,          # + = plus lent que la cible
    "reasons": ["Volume 98%", "Allure +6\"/km vs cible"]
  }

Au niveau semaine (clé `compliance` sur chaque semaine écoulée/en cours) :
  {
    "km_pct": 94,               # % volume hebdo réalisé (jours passés)
    "sessions_done": 5, "sessions_planned": 6,
    "keys_success": 1, "keys_total": 2,
    "points": 88, "verdict": "success"
  }
"""
from __future__ import annotations
import re
from datetime import date, datetime
from typing import Optional

# ============================================================================
# CONSTANTES
# ============================================================================

# Types de séance considérés "qualité" → l'allure se juge sur les laps rapides
QUALITY_TYPES = {'interval', 'vma', 'seuil', 'threshold', 'tempo', 'mp', 'marathon_pace', 'race'}
# Types continus → l'allure se juge sur la moyenne de la séance
STEADY_TYPES = {'easy', 'recovery', 'long', 'long_mp', 'shake', 'progressive'}

# Seuils de verdict
SUCCESS_MIN = 80
PARTIAL_MIN = 55

VERDICT_LABELS = {
    'success': 'Réussie',
    'partial': 'Partielle',
    'failed': 'Échouée',
    'missed': 'Manquée',
}


# ============================================================================
# HELPERS
# ============================================================================

_PACE_RE = re.compile(r"(\d+)'(\d{1,2})")


def parse_pace_str(pace: Optional[str]) -> Optional[int]:
    """
    "4'15\"/km" → 255. Gère les fourchettes ("4'50-5'00") en prenant le milieu.
    """
    if not pace or not isinstance(pace, str):
        return None
    matches = _PACE_RE.findall(pace)
    if not matches:
        return None
    secs = [int(m) * 60 + int(s) for m, s in matches]
    return round(sum(secs) / len(secs))


def fmt_pace(sec: Optional[float]) -> Optional[str]:
    if not sec:
        return None
    m, s = divmod(round(sec), 60)
    return f"{m}'{s:02d}\"/km"


def _is_quality_day(day: dict) -> bool:
    t = (day.get('type') or '').lower()
    if t in QUALITY_TYPES:
        return True
    # Les séances clés hors sortie longue sont traitées comme qualité
    if day.get('key') and not t.startswith('long'):
        return True
    return False


def _fast_laps_pace(sessions: list[dict], target_s: int) -> Optional[int]:
    """
    Allure moyenne pondérée des laps "rapides" d'une (ou plusieurs) séance(s),
    i.e. les laps dont l'allure est ≤ cible + 45s/km (exclut échauffement/récup).
    Retourne None si aucun lap exploitable.
    """
    threshold = target_s + 45
    tot_d, tot_t = 0.0, 0.0
    for s in sessions:
        for lap in (s.get('b') or []):
            ps, km = lap.get('ps'), lap.get('km') or 0
            if not ps or km <= 0.05:
                continue
            if ps <= threshold:
                tot_d += km
                tot_t += ps * km
    if tot_d < 0.3:  # moins de 300m rapides : pas significatif
        return None
    return round(tot_t / tot_d)


_HR_CAP_RE = re.compile(r"FC\s*(?:<|≤|<=|max\.?|inf(?:érieure)?\s*à)\s*(\d{2,3})", re.I)


def parse_hr_cap(description: Optional[str]) -> Optional[int]:
    """
    Extrait une consigne de FC plafond depuis la description d'une séance.
    "12 km ... FC < 140." → 140. Retourne None si aucune consigne.
    """
    if not description or not isinstance(description, str):
        return None
    m = _HR_CAP_RE.search(description)
    return int(m.group(1)) if m else None


def _flat_laps(sessions: list[dict], min_lap_km: float = 0.05
               ) -> list[tuple[float, int, int]]:
    """Laps exploitables (km, allure s/km, FC) de la/des séance(s)."""
    out = []
    for s in sessions:
        for lap in (s.get('b') or []):
            km, ps, fc = lap.get('km') or 0, lap.get('ps'), lap.get('fc')
            if km > min_lap_km and ps and fc:
                out.append((km, ps, fc))
    return out


def hr_decoupling_pct(sessions: list[dict], skip_km: float = 2.0,
                      min_km: float = 6.0) -> Optional[float]:
    """
    Découplage aérobie (méthode Friel) : dérive du rapport vitesse/FC entre la
    première et la seconde moitié de la séance, échauffement exclu.

    > 0  = la FC monte à vitesse égale (dérive cardiaque : chaleur, déshydratation,
           fatigue, glycogène bas). Repère classique : < 5 % bon, > 8 % notable.
    < 0  = la FC baisse / la vitesse monte (négatif split, échauffement long).

    Retourne None si la séance est trop courte ou trop fractionnée pour que la
    mesure ait un sens.
    """
    # Les laps courts (lignes droites, récups, fractions) sont exclus : ils
    # feraient passer une accélération volontaire pour une dérive cardiaque.
    laps = _flat_laps(sessions, min_lap_km=0.4)
    if sum(k for k, _, _ in laps) < min_km:
        return None

    # Laps anormalement lents (feu rouge, pause, marche) : la FC reste haute
    # alors que la vitesse s'effondre → fausse dérive massive. On les écarte.
    paces = sorted(ps for _, ps, _ in laps)
    median_ps = paces[len(paces) // 2]
    laps = [l for l in laps if l[1] <= median_ps + 90]
    if sum(k for k, _, _ in laps) < min_km:
        return None

    kept, acc = [], 0.0
    for km, ps, fc in laps:
        acc += km
        if acc <= skip_km:
            continue
        kept.append((km, ps, fc))
    if len(kept) < 4:
        return None

    half = sum(k for k, _, _ in kept) / 2
    first, second, acc = [], [], 0.0
    for lap in kept:
        (first if acc < half else second).append(lap)
        acc += lap[0]
    if len(first) < 2 or len(second) < 2:
        return None

    def eff(group):
        # vitesse moyenne (km/s) / FC moyenne, pondérées par la distance
        dist = sum(k for k, _, _ in group)
        if dist <= 0:
            return None
        time_s = sum(k * ps for k, ps, _ in group)
        fc_avg = sum(k * fc for k, _, fc in group) / dist
        if time_s <= 0 or fc_avg <= 0:
            return None
        return (dist / time_s) / fc_avg

    e1, e2 = eff(first), eff(second)
    if not e1 or not e2:
        return None
    return round((e1 - e2) / e1 * 100, 1)


def hr_block(day: dict, actual_sessions: list[dict],
             actual: dict, quality: bool) -> Optional[dict]:
    """
    Bloc cardiaque d'une séance : FC moyenne, consigne éventuelle, dépassement,
    découplage. Purement descriptif — n'entre PAS dans le score.

    Raison : sans donnée météo, une dérive estivale (chaleur, humidité) est
    indiscernable d'une dérive de fatigue. On mesure et on transmet au coach,
    on ne sanctionne pas.
    """
    avg = actual.get('fc')
    cap = parse_hr_cap(day.get('description'))
    drift = hr_decoupling_pct(actual_sessions)
    if avg is None and drift is None:
        return None

    over = (avg - cap) if (avg and cap) else None
    flags = []
    if over is not None and over > 3:
        flags.append('over_cap')
    if drift is not None and not quality and drift >= 8:
        flags.append('drift_high')
    return {
        'avg': avg,
        'cap': cap,
        'over_cap': over,
        'decoupling_pct': drift,
        'flags': flags,
    }


def _volume_points(pct: float) -> float:
    """Score volume : plateau 100 entre 90% et 115%, dégressif au-delà/en-deçà."""
    if pct >= 150:
        return 70.0          # très au-delà du prévu : malus net (gestion de charge)
    if pct >= 130:
        return 85.0          # nettement trop long : léger malus (gestion de charge)
    if pct > 115:
        return 100 - (pct - 115) * 1.0
    if pct >= 90:
        return 100.0
    if pct >= 40:
        return (pct - 40) / 50 * 100   # 40% → 0 pts, 90% → 100 pts
    return 0.0


def _pace_points(delta_s: float, quality: bool) -> float:
    """
    Score allure selon l'écart à la cible (delta > 0 = plus lent).
    Qualité : tolérance serrée. Continu : tolérance large, trop rapide pénalisé
    aussi (discipline de zones).
    """
    if quality:
        if delta_s <= -15:
            return 90.0      # nettement trop rapide : séance dénaturée, léger malus
        if delta_s <= 5:
            return 100.0
        if delta_s >= 30:
            return 0.0
        return 100 - (delta_s - 5) * 4.0
    # Continu (footing, SL, récup)
    ad = abs(delta_s)
    if ad <= 20:
        return 100.0
    if ad >= 60:
        return 0.0
    return 100 - (ad - 20) * 2.5


# ============================================================================
# SCORING D'UN JOUR
# ============================================================================

def score_day(day: dict, actual_sessions: list[dict]) -> Optional[dict]:
    """
    Calcule le score d'un jour de plan avec séance(s) réelle(s).
    Retourne None si non applicable (repos, bonus, pas de km prévus).
    """
    planned_km = day.get('km') or 0
    if planned_km <= 0 or (day.get('type') or '') == 'rest':
        return None
    actual = day.get('actual') or {}
    actual_km = actual.get('km') or sum(s.get('km', 0) for s in actual_sessions)
    if actual_km <= 0:
        return None

    reasons = []
    if day.get('_replaced_by_coach'):
        reasons.append("Séance remplacée par le coach (validée)")

    # --- Volume ---
    vol_pct = actual_km / planned_km * 100
    vol_pts = _volume_points(vol_pct)
    reasons.append(f"Volume {vol_pct:.0f}%")

    # --- Allure ---
    # Séance remplacée par le coach (change_type validé) : la cible d'origine
    # a été effacée à l'application. On n'invente pas de nouvelle cible ici,
    # on juge le remplacement sur son volume seul plutôt que d'afficher un
    # échec d'allure contre une cible caduque.
    quality = _is_quality_day(day) and not day.get('_replaced_by_coach')
    target_s = parse_pace_str(day.get('target_pace'))
    pace_pts = None
    pace_actual_s = None
    delta_s = None
    if target_s:
        if quality:
            pace_actual_s = _fast_laps_pace(actual_sessions, target_s)
        if pace_actual_s is None:
            pace_actual_s = actual.get('pace_sec')
        if pace_actual_s:
            delta_s = pace_actual_s - target_s
            pace_pts = _pace_points(delta_s, quality)
            sign = '+' if delta_s >= 0 else '−'
            reasons.append(f"Allure {sign}{abs(delta_s):.0f}\"/km vs cible")

    # --- Cardiaque (descriptif, hors score) ---
    hrb = hr_block(day, actual_sessions, actual, quality)
    if hrb:
        if hrb.get('over_cap') is not None and 'over_cap' in hrb['flags']:
            reasons.append(f"FC moy {hrb['avg']} vs consigne <{hrb['cap']}")
        if hrb.get('decoupling_pct') is not None and 'drift_high' in hrb['flags']:
            reasons.append(f"Dérive cardiaque {hrb['decoupling_pct']:+.1f}%")

    # --- Score global ---
    if pace_pts is not None:
        points = 0.55 * vol_pts + 0.45 * pace_pts
    else:
        points = vol_pts

    if points >= SUCCESS_MIN:
        verdict = 'success'
    elif points >= PARTIAL_MIN:
        verdict = 'partial'
    else:
        verdict = 'failed'

    return {
        'points': round(points),
        'verdict': verdict,
        'verdict_label': VERDICT_LABELS[verdict],
        'volume_pct': round(vol_pct),
        'volume_points': round(vol_pts),
        'pace_points': round(pace_pts) if pace_pts is not None else None,
        'pace_target_s': target_s,
        'pace_actual_s': pace_actual_s,
        'pace_actual_str': fmt_pace(pace_actual_s),
        'pace_delta_s': round(delta_s) if delta_s is not None else None,
        'is_quality': quality,
        'hr': hrb,
        'reasons': reasons,
    }


# ============================================================================
# SCORING HEBDO
# ============================================================================

def score_weeks(plan: dict) -> dict:
    """Attache `compliance` à chaque semaine écoulée ou en cours."""
    today = date.today()
    for w in plan.get('weeks', []):
        try:
            ws = date.fromisoformat(w['start_date'])
        except Exception:
            continue
        if ws > today:
            w.pop('compliance', None)
            continue

        # Trois totaux, pour trois questions différentes :
        # « où en est le prorata ? »   → km_planned / km_done (jusqu'à hier)
        # « qu'ai-je couru cette sem ? » → km_done_week (tout, y compris demain)
        # « quel est l'objectif ? »    → km_planned_week (tout)
        km_planned = km_done = 0.0
        km_planned_week = km_done_week = 0.0
        sessions_planned = sessions_done = 0
        sessions_done_week = 0
        keys_total = keys_success = 0
        day_scores = []

        for day in w.get('days', []):
            try:
                dd = date.fromisoformat(day['date'])
            except Exception:
                continue
            pk = day.get('km') or 0
            actual_km = (day.get('actual') or {}).get('km') or 0

            # Totaux hebdo complets (indépendants d'aujourd'hui)
            if pk > 0 and (day.get('type') or '') != 'rest':
                km_planned_week += pk
            if actual_km > 0:
                km_done_week += actual_km
                sessions_done_week += 1

            if dd >= today:
                continue
            if pk > 0 and (day.get('type') or '') != 'rest':
                km_planned += pk
                sessions_planned += 1
                sc = day.get('score')
                if day.get('actual'):
                    km_done += actual_km
                    sessions_done += 1
                if sc:
                    day_scores.append(sc['points'])
                if day.get('key'):
                    keys_total += 1
                    if sc and sc['verdict'] == 'success':
                        keys_success += 1
            elif day.get('actual'):
                km_done += actual_km  # bonus km comptés

        if km_planned <= 0:
            w.pop('compliance', None)
            continue

        km_pct = km_done / km_planned * 100
        avg_score = sum(day_scores) / len(day_scores) if day_scores else 0
        points = 0.6 * min(km_pct, 100) + 0.4 * avg_score
        verdict = ('success' if points >= SUCCESS_MIN
                   else 'partial' if points >= PARTIAL_MIN else 'failed')

        w['compliance'] = {
            'km_pct': round(km_pct),
            'km_done': round(km_done, 1),
            'km_planned': round(km_planned, 1),
            'km_done_week': round(km_done_week, 1),
            'km_planned_week': round(km_planned_week, 1),
            'sessions_done': sessions_done,
            'sessions_planned': sessions_planned,
            'sessions_done_week': sessions_done_week,
            'keys_success': keys_success,
            'keys_total': keys_total,
            'points': round(points),
            'verdict': verdict,
        }
    return plan
