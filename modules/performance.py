"""
seb-metrics — modules/performance.py
========================================
Moteur d'estimation de la VMA + dérivation des allures de course + tendance 30j.

Logique portée du parser JS v8 (estimation VMA multi-sources + consensus médian) :

Sources de VMA (en km/h) :
  A. VMA observée : médiane top-3 des fractionnés VMA récents (90j)
     avec facteur reps (course courte → vitesse boostée vs VMA "vraie")
  B. Records distance : meilleurs 1500m, 3K, 5K → VMA via facteurs Léger-Mercier
  C. VO2 Garmin (si dispo) : VO2max × 0.285 = VMA km/h

Consensus = médiane des sources disponibles
Spread%   = (max-min)/mediane × 100 → indicateur de fiabilité

Allures dérivées (table Daniels simplifiée) :
  - VMA      : 100 % de la VMA
  - 10K      :  92 % VMA
  - Seuil    :  85 % VMA  (≈ allure d'1h à fond)
  - Semi     :  82 % VMA  (≈ 88 % FCmax sur 21k)
  - Marathon :  78 % VMA  (≈ 80 % FCmax sur 42k)

Tendance 30j :
  Comparaison estimation actuelle vs estimation calculée sur les sessions
  jusqu'à J-30 (fenêtre roulante). Le delta est exprimé en sec/km pour les
  allures et en km/h pour la VMA.
"""

from __future__ import annotations
import math
import statistics
from datetime import datetime, timedelta
from typing import Optional


# ============================================================================
# CONSTANTES
# ============================================================================

# Coefficients % VMA pour dérivation allures d'entraînement
# Calibration Sébastien : +3 points vs Daniels standard
# Justification empirique : ton marathon Paris 12/04/26 à 4'01/km (81.3% VMA),
# ton semi récent à 3'51/km (84.8% VMA) — profil endurant au-dessus des % Daniels génériques.
_PCT_VMA = {
    'vma':      1.00,   # Allure VMA pure (inchangé)
    '10k':      0.95,   # Daniels: 0.92 → +3 pts
    'seuil':    0.88,   # Daniels: 0.85 → +3 pts
    'semi':     0.85,   # Daniels: 0.82 → +3 pts (validé empiriquement: semi 3'51/km observé)
    'marathon': 0.81,   # Daniels: 0.78 → +3 pts (validé empiriquement: marathon 4'01/km observé)
}

# Facteurs de boost pour estimer la VMA "vraie" depuis fractionnés
# Plus la rep est courte, plus la vitesse observée est au-dessus de la VMA pure
_REP_FACTORS = [
    (0.30,  1.05),  # 200-300m : on enlève 5%
    (0.50,  1.03),
    (0.80,  1.01),
    (1.20,  1.00),  # ~1000m = pile VMA
    (2.00,  0.98),
    (3.00,  0.96),  # 3K = ~96% VMA
    (5.00,  0.93),  # 5K = ~92-93% VMA
]

# Facteurs Léger-Mercier pour convertir record distance en VMA (vitesse moy. × facteur)
_DIST_TO_VMA_FACTOR = [
    (1.5,  1.03),
    (3.0,  1.08),
    (5.0,  1.16),
    (10.0, 1.25),
]

# Fenêtres temporelles
_RECENT_WINDOW_DAYS = 90    # pour les VMA récentes (source A et B)
_TREND_WINDOW_DAYS  = 30    # période de comparaison de tendance


# ============================================================================
# HELPERS
# ============================================================================

def _parse_date(date_str: str, time_str: str = '00:00') -> Optional[datetime]:
    try:
        return datetime.strptime(f"{date_str} {time_str}", '%d/%m/%Y %H:%M')
    except Exception:
        return None


def _median(values: list[float]) -> Optional[float]:
    return statistics.median(values) if values else None


def _avg_bloc_speed_kmh(bloc: dict) -> Optional[float]:
    """Retourne la vitesse moyenne d'un bloc en km/h, ou None."""
    if bloc.get('ps') and bloc['ps'] > 0:
        return 3600.0 / bloc['ps']  # ps = sec/km → km/h
    return None


def _rep_factor(km: float) -> float:
    """Renvoie le facteur de conversion vitesse→VMA selon la distance de la rep."""
    for max_km, factor in _REP_FACTORS:
        if km <= max_km:
            return factor
    return _REP_FACTORS[-1][1]


def _dist_to_vma_factor(km: float) -> Optional[float]:
    """Facteur de conversion vitesse-de-course→VMA pour records de distance."""
    for max_km, factor in _DIST_TO_VMA_FACTOR:
        if km <= max_km * 1.1:
            return factor
    return None


# ============================================================================
# SOURCE A — VMA depuis fractionnés VMA récents
# ============================================================================

def _vma_from_fractionnes(sessions: list[dict], reference_date: datetime) -> Optional[float]:
    """
    Estime la VMA depuis les fractionnés VMA des 90 derniers jours.

    Critères de validité d'une séance "VMA pure" :
      - Type : frac_court, frac_long, fractionne
      - Au moins 3 blocs rapides (intent=active ou ps<240 s/km)
      - Distance par bloc : 0.2-1.2 km
      - Vitesse moyenne pondérée des blocs rapides ≥ 16 km/h
        (en-dessous, c'est du seuil ou tempo, pas de la VMA)

    Méthode :
      - On calcule la vitesse pondérée par la distance des blocs rapides
      - On applique un facteur de boost selon la distance moyenne des reps
      - On retient la médiane des top-3 estimations
    """
    cutoff = reference_date - timedelta(days=_RECENT_WINDOW_DAYS)
    candidates = []

    for s in sessions:
        if s.get('tp') not in ('frac_court', 'frac_long', 'fractionne'):
            continue
        dt = _parse_date(s['d'], s.get('h', '00:00'))
        if not dt or dt < cutoff or dt > reference_date:
            continue

        # Blocs rapides : intent=active prioritaire, sinon ps<240 s/km (15 km/h+)
        blocs = s.get('b', [])
        fast = []
        for b in blocs:
            is_active = b.get('intent') == 'active'
            is_fast_pace = b.get('ps') and b['ps'] < 240
            if is_active or is_fast_pace:
                spd = _avg_bloc_speed_kmh(b)
                if spd and 14 <= spd <= 24 and 0.2 <= b['km'] <= 1.2:
                    fast.append((b['km'], spd))

        # Critère : au moins 3 blocs rapides
        if len(fast) < 3:
            continue

        # Vitesse moy pondérée par la distance
        total_km = sum(km for km, _ in fast)
        if total_km <= 0:
            continue
        avg_speed = sum(km * spd for km, spd in fast) / total_km
        avg_rep_km = total_km / len(fast)

        # Critère VMA : vitesse moyenne ≥ 16 km/h (sinon c'est seuil/tempo)
        if avg_speed < 16:
            continue

        # Facteur de boost selon la distance moy des reps
        factor = _rep_factor(avg_rep_km)
        vma_estimate = avg_speed / factor
        candidates.append(vma_estimate)

    if not candidates:
        return None

    # Médiane des top-3 (plus représentatif que max → moins de bruit)
    top3 = sorted(candidates, reverse=True)[:3]
    return _median(top3)


# ============================================================================
# SOURCE B — VMA depuis records de distance récents
# ============================================================================

# Distances cibles strictes pour les records (centre, marge basse, marge haute, facteur Léger-Mercier)
_DISTANCE_TARGETS = [
    # (target_km, min_km, max_km, vma_factor)
    (1.5,  1.40,  1.65,  1.03),
    (3.0,  2.90,  3.30,  1.08),
    (5.0,  4.80,  5.50,  1.16),
    (10.0, 9.50, 11.00,  1.25),
]

# Types de séances exclus pour les records (pas représentatifs)
_EXCLUDED_TYPES_FOR_RECORDS = {'footing', 'endurance', 'sortie_longue', 'tempo'}


def _fast_phase_speed(session: dict) -> Optional[tuple[float, float]]:
    """
    Pour une séance avec des blocs `intent=active`, retourne (distance_cumulee, vitesse_moyenne)
    de la phase rapide uniquement. Sinon None.

    Utile pour extraire un "vrai 5K rapide" d'une séance de fractionné long type 5×1km à allure 10K.
    """
    blocs = session.get('b', [])
    active_blocs = [b for b in blocs if b.get('intent') == 'active' and b.get('ps') and b['ps'] > 0]
    if len(active_blocs) < 2:
        return None
    total_km = sum(b['km'] for b in active_blocs)
    if total_km <= 0:
        return None
    total_sec = sum(b['dur_s'] for b in active_blocs if b.get('dur_s'))
    if total_sec <= 0:
        return None
    speed = (total_km * 1000) / total_sec * 3.6  # m/s × 3.6 → km/h
    return (total_km, speed)


def _vma_from_distance_records(sessions: list[dict], reference_date: datetime) -> Optional[float]:
    """
    Estime la VMA depuis les meilleures performances récentes sur 1500m-10K.

    Deux cas distincts :

    1. **Séance continue** (test, semi, marathon, intervalle long unique...) :
       - Distance dans une fourchette serrée par cible
       - Vitesse moyenne ≥ 15 km/h
       - Type non footing/endurance/sortie_longue/tempo
       - Conversion via facteur Léger-Mercier (× 1.03 à × 1.25 selon distance)

    2. **Phase rapide cumulée d'un fractionnement** (5×1km, 6×1000m, etc.) :
       - Vitesse cumulée des blocs intent=active
       - La vitesse cumulée représente déjà ~95-97% de la VMA (pas du %vitesse-course)
       - Conversion via facteur reps inversé (1/0.95 à 1/0.98), PAS Léger-Mercier
       - C'est en pratique un confirmateur de la source A
    """
    cutoff = reference_date - timedelta(days=_RECENT_WINDOW_DAYS)
    estimates = []

    # ===== Cas 1 : séances continues =====
    for target_km, min_km, max_km, factor in _DISTANCE_TARGETS:
        best_speed = None
        for s in sessions:
            dt = _parse_date(s['d'], s.get('h', '00:00'))
            if not dt or dt < cutoff or dt > reference_date:
                continue
            tp = s.get('tp', '')
            # On exclut frac (traités en cas 2) et types non représentatifs
            if tp in ('frac_court', 'frac_long', 'fractionne'):
                continue
            if tp in _EXCLUDED_TYPES_FOR_RECORDS:
                continue
            if not (min_km <= s['km'] <= max_km):
                continue
            if not s.get('ps') or s['ps'] <= 0:
                continue
            speed = 3600.0 / s['ps']
            if speed < 15 or speed > 25:
                continue
            if best_speed is None or speed > best_speed:
                best_speed = speed
        if best_speed:
            estimates.append(best_speed * factor)

    # ===== Cas 2 : phases rapides cumulées des frac (confirmateur de source A) =====
    best_phase_vma = None
    for s in sessions:
        if s.get('tp') not in ('frac_court', 'frac_long', 'fractionne'):
            continue
        dt = _parse_date(s['d'], s.get('h', '00:00'))
        if not dt or dt < cutoff or dt > reference_date:
            continue
        phase = _fast_phase_speed(s)
        if not phase:
            continue
        phase_km, phase_speed = phase
        # Validité : phase > 2 km cumulés, vitesse 15-22 km/h
        if phase_km < 2.0 or phase_speed < 15 or phase_speed > 22:
            continue

        # Conversion phase → VMA : on récupère la distance moy des reps actives
        active_blocs = [b for b in s.get('b', []) if b.get('intent') == 'active' and b.get('km')]
        if not active_blocs:
            continue
        avg_rep_km = phase_km / len(active_blocs)
        # Facteur de reps : court=boost, long=neutre
        rep_factor = _rep_factor(avg_rep_km)
        vma_estimate = phase_speed / rep_factor
        if best_phase_vma is None or vma_estimate > best_phase_vma:
            best_phase_vma = vma_estimate

    if best_phase_vma:
        estimates.append(best_phase_vma)

    return _median(estimates) if estimates else None


# ============================================================================
# CONSENSUS VMA
# ============================================================================

# Poids des sources pour le consensus pondéré
_SOURCE_WEIGHTS = {
    'A': 1.5,   # Fractionnés VMA observés récemment = source la plus fiable
    'B': 1.0,   # Records distance = peut être bruitée
}

# Seuil de divergence : au-delà, on écarte la source divergente
_MAX_DIVERGENCE_PCT = 15.0


def _weighted_consensus(sources: dict) -> tuple[Optional[float], Optional[float]]:
    """
    Calcule un consensus pondéré entre sources A et B.

    Retourne (consensus_vma_kmh, spread_pct).

    Logique :
      - 0 source valide → (None, None)
      - 1 source valide → on la retourne
      - 2 sources : si l'écart entre elles dépasse _MAX_DIVERGENCE_PCT,
        on garde la source la mieux pondérée (en pratique A : fractionnés observés)
        sinon moyenne pondérée
    """
    valid = {k: v for k, v in sources.items() if v is not None}

    if not valid:
        return (None, None)

    if len(valid) == 1:
        return (list(valid.values())[0], None)

    # 2 sources : on regarde l'écart entre les deux
    values = list(valid.values())
    mean_naive = sum(values) / len(values)
    gap_pct = (max(values) - min(values)) / mean_naive * 100

    if gap_pct > _MAX_DIVERGENCE_PCT:
        # Divergence trop forte : on garde la source au poids le plus élevé
        best_key = max(valid.keys(), key=lambda k: _SOURCE_WEIGHTS.get(k, 1.0))
        return (valid[best_key], gap_pct)

    # Sinon, moyenne pondérée
    total_weight = sum(_SOURCE_WEIGHTS.get(k, 1.0) for k in valid)
    weighted_sum = sum(v * _SOURCE_WEIGHTS.get(k, 1.0) for k, v in valid.items())
    consensus = weighted_sum / total_weight
    return (consensus, gap_pct)


def estimate_vma(sessions: list[dict], reference_date: Optional[datetime] = None) -> dict:
    """
    Estime la VMA par consensus pondéré multi-sources.

    Returns:
      {
        'vma':        float | None (km/h),
        'sources':    {'A': float | None, 'B': float | None},
        'spread_pct': float | None,
        'confidence': int (0-100),
        'kept':       list[str]  # sources retenues dans le consensus
      }
    """
    if reference_date is None:
        reference_date = datetime.now()

    src_a = _vma_from_fractionnes(sessions, reference_date)
    src_b = _vma_from_distance_records(sessions, reference_date)

    sources = {'A': src_a, 'B': src_b}
    consensus, gap_pct = _weighted_consensus(sources)

    if consensus is None:
        return {
            'vma': None,
            'sources': sources,
            'spread_pct': None,
            'confidence': 0,
            'kept': [],
        }

    # Sources retenues dans le consensus
    if gap_pct is None:
        # Une seule source valide
        kept = [k for k, v in sources.items() if v is not None]
        confidence = 60
    elif gap_pct > _MAX_DIVERGENCE_PCT:
        # Divergence forte : seule la source la mieux pondérée a été retenue
        best_key = max((k for k, v in sources.items() if v is not None),
                       key=lambda k: _SOURCE_WEIGHTS.get(k, 1.0))
        kept = [best_key]
        confidence = 55   # confidence modérée : on n'a gardé qu'une source
    else:
        # Sources concordantes
        kept = [k for k, v in sources.items() if v is not None]
        confidence = max(70, round(100 - gap_pct * 3))

    return {
        'vma': round(consensus, 2),
        'sources': {k: round(v, 2) if v else None for k, v in sources.items()},
        'spread_pct': round(gap_pct, 1) if gap_pct is not None else None,
        'confidence': confidence,
        'kept': kept,
    }


# ============================================================================
# DÉRIVATION DES ALLURES
# ============================================================================

def derive_paces(vma_kmh: float) -> dict:
    """
    Dérive les allures cibles depuis la VMA.

    Args:
      vma_kmh : VMA en km/h

    Returns:
      Dict { 'vma', '10k', 'seuil', 'semi', 'marathon' } → secondes/km
      (pour la VMA, on retourne aussi en s/km pour cohérence)
    """
    out = {}
    for label, pct in _PCT_VMA.items():
        speed_kmh = vma_kmh * pct
        if speed_kmh > 0:
            sec_per_km = 3600.0 / speed_kmh
            out[label] = round(sec_per_km)
        else:
            out[label] = None
    return out


# ============================================================================
# TENDANCE 30 JOURS
# ============================================================================

# Critère "donnée VMA fiable" pour la détection de fenêtre d'affûtage :
# Une séance compte comme "vraie VMA" si ses blocs rapides moyens ≥ 17 km/h.
# En dessous, c'est du seuil long ou du 10K (typique de prépa marathon).
# Si moins de N vraies séances VMA dans la fenêtre 90j, le past n'est pas
# représentatif d'une VRAIE VMA — il sous-estime forcément, donc le delta
# affiché serait trompeur.
_MIN_VMA_SESSIONS_FOR_RELIABLE_PAST = 3
_TRUE_VMA_MIN_SPEED_KMH = 17.0


def _count_usable_vma_sessions(sessions: list[dict], reference_date: datetime) -> int:
    """
    Compte les séances "vraie VMA" dans la fenêtre [reference_date - 90j, reference_date].

    Une séance compte si :
      - Type frac_court / frac_long / fractionne
      - ≥ 3 blocs rapides (intent=active ou ps<240)
      - Distance par bloc 0.2-1.2 km
      - **Vitesse moyenne pondérée des blocs rapides ≥ 17 km/h**
        (en dessous = seuil long / 10K, pas VMA pure)
    """
    cutoff = reference_date - timedelta(days=_RECENT_WINDOW_DAYS)
    count = 0
    for s in sessions:
        if s.get('tp') not in ('frac_court', 'frac_long', 'fractionne'):
            continue
        dt = _parse_date(s['d'], s.get('h', '00:00'))
        if not dt or dt < cutoff or dt > reference_date:
            continue
        blocs = s.get('b', [])
        fast = []
        for b in blocs:
            is_active = b.get('intent') == 'active'
            is_fast = b.get('ps') and b['ps'] < 240
            if is_active or is_fast:
                spd = _avg_bloc_speed_kmh(b)
                if spd and 14 <= spd <= 24 and 0.2 <= b['km'] <= 1.2:
                    fast.append((b['km'], spd))
        if len(fast) < 3:
            continue
        total_km = sum(km for km, _ in fast)
        if total_km <= 0:
            continue
        avg_speed = sum(km * spd for km, spd in fast) / total_km
        if avg_speed >= _TRUE_VMA_MIN_SPEED_KMH:
            count += 1
    return count


def compute_trend(sessions: list[dict], reference_date: Optional[datetime] = None) -> dict:
    """
    Calcule l'estimation VMA + allures actuelles ET il y a 30j.
    Retourne les deltas + un flag de fiabilité.

    Returns:
      {
        'now':  {'vma', 'paces', 'confidence', 'spread_pct', 'sources', 'kept'},
        'past': {'vma', 'paces', 'confidence', 'spread_pct'},
        'delta': {
          'vma':       float | None (km/h),
          'paces':     {str: int | None}  (sec/km, négatif = plus rapide),
          'reliable':  bool,
          'reason':    str | None  ('taper_window', 'no_data', None)
        },
        'window_days': 30
      }
    """
    if reference_date is None:
        reference_date = datetime.now()
    past_date = reference_date - timedelta(days=_TREND_WINDOW_DAYS)

    now_est = estimate_vma(sessions, reference_date)
    past_est = estimate_vma(sessions, past_date)

    now_paces  = derive_paces(now_est['vma'])  if now_est['vma']  else {}
    past_paces = derive_paces(past_est['vma']) if past_est['vma'] else {}

    # Détection d'une fenêtre d'affûtage / disette de données dans le past
    past_vma_sessions = _count_usable_vma_sessions(sessions, past_date)

    # Deltas bruts
    delta_vma = None
    if now_est['vma'] and past_est['vma']:
        delta_vma = round(now_est['vma'] - past_est['vma'], 2)

    delta_paces = {}
    for k in ('vma', '10k', 'seuil', 'semi', 'marathon'):
        np_v = now_paces.get(k)
        pp_v = past_paces.get(k)
        if np_v is not None and pp_v is not None:
            delta_paces[k] = np_v - pp_v
        else:
            delta_paces[k] = None

    # Évaluation de la fiabilité
    if past_est['vma'] is None:
        reliable = False
        reason = 'no_data'
    elif past_vma_sessions < _MIN_VMA_SESSIONS_FOR_RELIABLE_PAST:
        # Pas assez de vraies VMA dans la fenêtre past — soit affûtage, soit
        # cycle marathon (séances seuil/10K mais pas VMA pure)
        reliable = False
        reason = 'low_vma_density'
    else:
        reliable = True
        reason = None

    return {
        'now': {
            'vma': now_est['vma'],
            'paces': now_paces,
            'confidence': now_est['confidence'],
            'spread_pct': now_est['spread_pct'],
            'sources': now_est['sources'],
            'kept': now_est.get('kept', []),
        },
        'past': {
            'vma': past_est['vma'],
            'paces': past_paces,
            'confidence': past_est['confidence'],
            'spread_pct': past_est['spread_pct'],
            'vma_sessions_count': past_vma_sessions,
        },
        'delta': {
            'vma': delta_vma,
            'paces': delta_paces,
            'reliable': reliable,
            'reason': reason,
        },
        'window_days': _TREND_WINDOW_DAYS,
    }

# Snippet à AJOUTER à la fin de modules/performance.py (avant le bloc CLI DEBUG)
# Ne touche à AUCUNE fonction existante.

# ============================================================================
# HISTORIQUE — calcul d'estimations VMA sur fenêtres glissantes
# ============================================================================

def compute_history(
    sessions: list[dict],
    step_days: int = 14,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
) -> list[dict]:
    """
    Calcule une série d'estimations VMA sur une grille de dates passées.

    À chaque date de la grille, on appelle estimate_vma() en fixant la
    reference_date à cette date — l'estimation utilise donc uniquement les
    sessions qui existaient à cette époque-là (fenêtre glissante 90j).

    Args:
        sessions    : liste complète des sessions du cache
        step_days   : pas entre deux points (14 = 1 point toutes les 2 semaines)
        start_date  : début de la série. Par défaut = date de la 1ère session + 90j
                      (avant ce délai, on n'a pas assez de données pour estimer)
        end_date    : fin de la série. Par défaut = date de la dernière session

    Returns:
        Liste de dicts triés chronologiquement :
        [
          {
            'date':       'YYYY-MM-DD',
            'vma':        float | None,
            'paces':      {str: int | None},
            'confidence': int,
            'sources':    {'A': float | None, 'B': float | None},
            'kept':       list[str]
          },
          ...
        ]

    Sécurité perf : pour 5 ans d'historique au pas de 14j on a ~130 points,
    chaque point relit toutes les sessions = O(n×points) où n = nombre de
    sessions. Pour 1000 sessions et 130 points, ~130k itérations max — OK.
    """
    if not sessions:
        return []

    # Détermine la grille temporelle
    dated = []
    for s in sessions:
        dt = _parse_date(s['d'], s.get('h', '00:00'))
        if dt:
            dated.append(dt)
    if not dated:
        return []
    dated.sort()

    # Par défaut, on commence 90j après la première session (sinon les premières
    # estimations sont vides faute de données dans la fenêtre 90j en arrière)
    if start_date is None:
        start_date = dated[0] + timedelta(days=_RECENT_WINDOW_DAYS)
    if end_date is None:
        end_date = dated[-1]

    # Génération de la grille
    grid = []
    current = start_date
    while current <= end_date:
        grid.append(current)
        current = current + timedelta(days=step_days)

    # Estimation à chaque point de grille
    history = []
    for ref_date in grid:
        est = estimate_vma(sessions, reference_date=ref_date)
        paces = derive_paces(est['vma']) if est['vma'] else {}
        history.append({
            'date':       ref_date.strftime('%Y-%m-%d'),
            'vma':        est['vma'],
            'paces':      paces,
            'confidence': est['confidence'],
            'sources':    est['sources'],
            'kept':       est.get('kept', []),
            'spread_pct': est['spread_pct'],
        })

    return history

# ============================================================================
# CLI DEBUG
# ============================================================================

if __name__ == '__main__':
    import sys
    import json
    from pathlib import Path

    cache_path = Path.home() / 'Documents' / 'SebMetrics' / 'data' / 'sessions_cache.json'
    if not cache_path.exists():
        print(f"✗ Cache introuvable : {cache_path}")
        sys.exit(1)

    with open(cache_path) as f:
        cache = json.load(f)

    sessions = list(cache.values())
    print(f"  → {len(sessions)} séances chargées\n")

    trend = compute_trend(sessions)
    print(json.dumps(trend, indent=2, ensure_ascii=False))
