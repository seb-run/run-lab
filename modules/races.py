"""
seb-metrics — modules/races.py
========================================
Logique courses & records.

Ce module ne s'occupe PAS du tag manuel côté UI (qui vit en localStorage
dans le navigateur). Il fournit :

  1. Les MÉTADONNÉES de distance pour qualifier un record (plages, libellés,
     ordre d'affichage). Ces métadonnées sont sérialisées et passées au JS
     pour qu'il calcule lui-même les records depuis les courses taguées.

  2. La liste des PAST_RACES déclarées en config (pré-remplies par l'utilisateur,
     ex: Paris 2026, Amsterdam 2023). Fusionnées côté JS avec les courses taguées
     localement, en évitant les doublons par `start_time`.

  3. L'algo de TAPER (recommandation de réduction de volume S-10 → S-1 avant
     un objectif). Calculé côté Python car déterministe à partir des goals[]
     + date de génération. Le frontend l'affiche tel quel.

  4. Le bloc COUNTDOWN par objectif (jours restants, semaines, phase de prépa).
"""

from __future__ import annotations
from datetime import datetime, date, timedelta
from typing import Optional


# ============================================================================
# CONSTANTES — plages de distance pour qualifier un record
# ============================================================================
# Ordre = ordre d'affichage dans le dashboard
# (min_km, max_km) = tolérance sur la distance enregistrée par la montre
# La plage haute est volontairement plus large pour absorber la sur-mesure
# GPS courante (un marathon réel = 42.195 km, la montre enregistre souvent
# 42.30-42.45 km).

RACE_DISTANCES = [
    {'key': '5k',       'label': '5K',       'target_km': 5.0,     'min_km': 4.95,  'max_km': 5.20},
    {'key': '10k',      'label': '10K',      'target_km': 10.0,    'min_km': 9.90,  'max_km': 10.30},
    {'key': '15k',      'label': '15K',      'target_km': 15.0,    'min_km': 14.85, 'max_km': 15.30},
    {'key': 'semi',     'label': 'Semi',     'target_km': 21.0975, 'min_km': 21.00, 'max_km': 21.40},
    {'key': 'marathon', 'label': 'Marathon', 'target_km': 42.195,  'min_km': 41.90, 'max_km': 42.50},
]


# ============================================================================
# CONFIG — objectifs et courses passées
# ============================================================================

def _parse_iso_date(s: str) -> Optional[date]:
    """Parse une date ISO YYYY-MM-DD. Retourne None si invalide."""
    if not s:
        return None
    try:
        return datetime.strptime(s, '%Y-%m-%d').date()
    except (ValueError, TypeError):
        return None


def get_goals(config: dict) -> list[dict]:
    """
    Récupère la liste des objectifs depuis la config.

    Structure cible (config['goals']) :
      [
        {
          "name": "Marathon témoin (à confirmer)",
          "date": "2026-10-04",
          "target_time": "2h43'00\"",
          "strategy_time": null,
          "priority": "secondary"
        },
        {
          "name": "NYC Marathon",
          "date": "2026-11-01",
          "target_time": "2h44'00\"",
          "strategy_time": "3h00'00\"",
          "priority": "primary"
        }
      ]

    Fallback rétrocompatible : si config['goals'] n'existe pas mais que
    profile['goal_name/date/time'] est rempli, on bricole un objectif unique
    pour que l'écran fonctionne quand même.
    """
    goals = config.get('goals')
    if isinstance(goals, list) and goals:
        return goals

    # Rétrocompat : ancien format avec un seul objectif dans profile
    profile = config.get('profile') or {}
    name = profile.get('goal_name')
    g_date = profile.get('goal_date')
    if name and g_date:
        return [{
            'name': name,
            'date': g_date,
            'target_time': profile.get('goal_time'),
            'strategy_time': None,
            'priority': 'primary',
        }]
    return []


def get_past_races(config: dict) -> list[dict]:
    """
    Récupère les courses passées pré-déclarées en config.

    Structure cible (config['past_races']) :
      [
        {
          "name": "Marathon de Paris 2026",
          "start_time": "2026-04-12T08:45",
          "distance_key": "marathon",
          "km": 42.195,
          "time_s": 10213,
          "note": "Pacing régulier, +5s/km Semi2 vs Semi1"
        },
        ...
      ]

    `start_time` = clé canonique pour matcher avec une séance du cache
    (format ISO local sans fuseau, précision minute).

    Si l'utilisateur n'a rien déclaré, retourne []. Le JS pourra de toute façon
    tagger via localStorage.
    """
    past = config.get('past_races')
    if isinstance(past, list):
        return past
    return []


# ============================================================================
# COUNTDOWN — calcul jours restants et phase de prépa
# ============================================================================

def _phase_for_days_left(days_left: int) -> str:
    """
    Détermine la phase de prépa en fonction des jours restants.
      > 70j  : "Préparation"
      28-70j : "Spécifique"
      8-27j  : "Affûtage" (taper)
      0-7j   : "Pic"
      < 0    : "Passé"
    """
    if days_left < 0:
        return 'past'
    if days_left <= 7:
        return 'peak'
    if days_left <= 27:
        return 'taper'
    if days_left <= 70:
        return 'specific'
    return 'preparation'


def compute_countdowns(goals: list[dict], today: Optional[date] = None) -> list[dict]:
    """
    Pour chaque objectif valide, calcule un bloc countdown.

    Returns une liste de dicts :
      [
        {
          'name': str,
          'date': 'YYYY-MM-DD',
          'date_fr': 'JJ/MM/AAAA',
          'days_left': int,
          'weeks_left': int,         # arrondi flooré, pour affichage "S-12"
          'phase': str,              # 'preparation' | 'specific' | 'taper' | 'peak' | 'past'
          'target_time': str | None,
          'strategy_time': str | None,
          'priority': str,
          'in_taper_window': bool,   # True si days_left dans [1, 70]
        },
        ...
      ]
    Triée par date croissante (objectif le plus proche en premier).
    """
    if today is None:
        today = date.today()

    result = []
    for g in goals or []:
        g_date = _parse_iso_date(g.get('date'))
        if not g_date:
            continue
        days_left = (g_date - today).days
        weeks_left = days_left // 7 if days_left >= 0 else 0
        result.append({
            'name':            g.get('name', 'Objectif'),
            'date':            g.get('date'),
            'date_fr':         g_date.strftime('%d/%m/%Y'),
            'days_left':       days_left,
            'weeks_left':      weeks_left,
            'phase':           _phase_for_days_left(days_left),
            'target_time':     g.get('target_time'),
            'strategy_time':   g.get('strategy_time'),
            'priority':        g.get('priority', 'secondary'),
            'in_taper_window': 1 <= days_left <= 70,
        })

    result.sort(key=lambda x: x['date'] or '9999')
    return result


# ============================================================================
# TAPER — recommandation S-10 → S-1
# ============================================================================
# Algo porté du v8 : réduction progressive du volume hebdomadaire les 10
# semaines avant un objectif marathon. Le pourcentage est relatif au pic
# de charge de la prépa (= 100% à S-10, descente progressive, S-1 réduite
# à 6 jours).
#
# Coefficients calibrés sur prépa marathon classique (4-5j/semaine pour Seb) :

_TAPER_PROFILE = [
    {'week': 10, 'volume_pct': 100, 'note': 'Pic de prépa'},
    {'week':  9, 'volume_pct':  95, 'note': 'Maintien charge'},
    {'week':  8, 'volume_pct': 100, 'note': 'Rebond / 2e pic'},
    {'week':  7, 'volume_pct':  90, 'note': 'Maintien charge'},
    {'week':  6, 'volume_pct':  95, 'note': 'Avant-dernière grosse semaine'},
    {'week':  5, 'volume_pct': 100, 'note': 'Dernière grosse semaine'},
    {'week':  4, 'volume_pct':  85, 'note': 'Début taper'},
    {'week':  3, 'volume_pct':  70, 'note': 'Taper franc'},
    {'week':  2, 'volume_pct':  55, 'note': 'Taper marqué'},
    {'week':  1, 'volume_pct':  40, 'note': 'Semaine de course (6 jours, repos veille)'},
]


def compute_taper(countdown: dict) -> Optional[dict]:
    """
    Pour un objectif dans la fenêtre [1, 70] jours, retourne le profil taper
    avec la semaine courante marquée.

    Returns:
      {
        'goal_name': str,
        'goal_date_fr': str,
        'days_left': int,
        'current_week': int,   # 1 à 10
        'weeks': [...]         # _TAPER_PROFILE enrichi de {'is_current', 'is_past'}
      }
    Ou None si l'objectif est hors fenêtre taper.
    """
    days_left = countdown.get('days_left')
    if days_left is None or days_left < 1 or days_left > 70:
        return None

    # current_week = nombre de semaines restantes (1 = S-1, 10 = S-10)
    # J-7 à J-1 → S-1 ; J-8 à J-14 → S-2 ; etc.
    current_week = max(1, min(10, (days_left + 6) // 7))

    weeks = []
    for w in _TAPER_PROFILE:
        weeks.append({
            **w,
            'is_current': w['week'] == current_week,
            'is_past':    w['week'] > current_week,
        })

    return {
        'goal_name':    countdown['name'],
        'goal_date_fr': countdown['date_fr'],
        'days_left':    days_left,
        'current_week': current_week,
        'weeks':        weeks,
    }


# ============================================================================
# BLOC RACES — assemblage du payload pour le template
# ============================================================================

def build_races_payload(config: dict, today: Optional[date] = None) -> dict:
    """
    Construit le payload `races` injecté dans le JSON inline du template.

    Returns:
      {
        'distances':   [...],   # RACE_DISTANCES
        'past_races':  [...],   # courses pré-déclarées en config
        'goals':       [...],   # raw config goals
        'countdowns':  [...],   # countdowns enrichis
        'tapers':      [...]    # tapers pour les objectifs en fenêtre
      }
    """
    goals = get_goals(config)
    countdowns = compute_countdowns(goals, today=today)
    tapers = [t for t in (compute_taper(c) for c in countdowns) if t is not None]

    return {
        'distances':  RACE_DISTANCES,
        'past_races': get_past_races(config),
        'goals':      goals,
        'countdowns': countdowns,
        'tapers':     tapers,
    }


# ============================================================================
# CLI DEBUG
# ============================================================================

if __name__ == '__main__':
    import json
    import sys
    from pathlib import Path

    cfg_path = Path.home() / 'Documents' / 'SebMetrics' / 'data' / 'config.json'
    if not cfg_path.exists():
        print(f"✗ Config introuvable : {cfg_path}")
        sys.exit(1)

    with open(cfg_path) as f:
        cfg = json.load(f)

    payload = build_races_payload(cfg)
    print(json.dumps(payload, indent=2, ensure_ascii=False))
