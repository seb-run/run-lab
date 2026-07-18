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

    # --- Volume ---
    vol_pct = actual_km / planned_km * 100
    vol_pts = _volume_points(vol_pct)
    reasons.append(f"Volume {vol_pct:.0f}%")

    # --- Allure ---
    quality = _is_quality_day(day)
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

        km_planned = km_done = 0.0
        sessions_planned = sessions_done = 0
        keys_total = keys_success = 0
        day_scores = []

        for day in w.get('days', []):
            try:
                dd = date.fromisoformat(day['date'])
            except Exception:
                continue
            if dd >= today:
                continue
            pk = day.get('km') or 0
            if pk > 0 and (day.get('type') or '') != 'rest':
                km_planned += pk
                sessions_planned += 1
                sc = day.get('score')
                if day.get('actual'):
                    km_done += (day['actual'].get('km') or 0)
                    sessions_done += 1
                if sc:
                    day_scores.append(sc['points'])
                if day.get('key'):
                    keys_total += 1
                    if sc and sc['verdict'] == 'success':
                        keys_success += 1
            elif day.get('actual'):
                km_done += (day['actual'].get('km') or 0)  # bonus km comptés

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
            'sessions_done': sessions_done,
            'sessions_planned': sessions_planned,
            'keys_success': keys_success,
            'keys_total': keys_total,
            'points': round(points),
            'verdict': verdict,
        }
    return plan
