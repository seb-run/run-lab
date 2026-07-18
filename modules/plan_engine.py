"""
seb-metrics — modules/plan_engine.py
========================================
Moteur de plan d'entraînement marathon.

Génère un plan jour par jour pour un objectif marathon, calibré sur :
  - La VMA actuelle de l'utilisateur (issue de performance.estimate_vma)
  - Le PB et l'objectif chrono
  - L'historique récent (volume hebdo "naturel")
  - La date cible

Structure produite (et persistée dans ~/Documents/SebMetrics/data/plan_<goal_key>.json) :

{
  "meta": {
    "goal_name": "NYC Marathon",
    "goal_date": "2026-11-01",
    "target_time": "2h44'00",
    "strategy_time": "3h00'00",
    "weeks_total": 21,
    "generated_at": "...",
    "vma_used": 18.5,
    "paces": {"mp_strategy": 255, "mp_target": 233, ...}
  },
  "weeks": [
    {
      "week_num": 1,
      "phase": "base",
      "phase_label": "Base 1",
      "start_date": "2026-06-08",
      "target_km": 62,
      "days": [
        {"date": "2026-06-08", "dow": "Mon", "type": "rest", "title": "Repos",
         "km": 0, "duration_min": 0, "description": "...", "key": false,
         "status": "done|missed|pending|today", "actual": {...}|None}
      ]
    }
  ]
}

Adaptation : `attach_actuals(plan, sessions)` matche les jours passés avec les
séances réelles et marque les statuts.
"""
from __future__ import annotations
import json
import math
from datetime import datetime, timedelta, date
from pathlib import Path
from typing import Optional

# Réutilisation
try:
    from modules.performance import derive_paces, estimate_vma
except Exception:
    derive_paces = None
    estimate_vma = None

try:
    from modules.session_scoring import score_day, score_weeks
except Exception:
    score_day = None
    score_weeks = None


# ============================================================================
# CONSTANTES
# ============================================================================

DOW_FR = ['Lun', 'Mar', 'Mer', 'Jeu', 'Ven', 'Sam', 'Dim']
DOW_EN = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']

PHASE_LABELS = {
    'base':     "Base · construction",
    'specific': "Spécifique · allure course",
    'peak':     "Pic · volume max",
    'taper':    "Affûtage",
    'race':     "Semaine de course",
}


# ============================================================================
# HELPERS
# ============================================================================

def _parse_goal_time_sec(t: str) -> Optional[int]:
    """'2h44\\'00\"' -> 9840 sec. Tolère 2h44, 2h44'00, 2h44m00, 2:44:00."""
    if not t:
        return None
    t = t.replace('"', '').replace("'", "'").strip()
    # Pattern h..m..s
    import re
    m = re.match(r"^(\d+)h(\d+)?'?(\d+)?$", t)
    if m:
        h = int(m.group(1)); mn = int(m.group(2) or 0); s = int(m.group(3) or 0)
        return h*3600 + mn*60 + s
    m = re.match(r"^(\d+):(\d+):(\d+)$", t)
    if m:
        return int(m.group(1))*3600 + int(m.group(2))*60 + int(m.group(3))
    return None


def _fmt_pace(sec_per_km: float) -> str:
    if not sec_per_km or sec_per_km <= 0:
        return "--"
    m = int(sec_per_km // 60); s = int(round(sec_per_km % 60))
    if s >= 60:
        m += 1; s = 0
    return f"{m}'{s:02d}\"/km"


def _fmt_duration(sec: float) -> str:
    sec = int(sec or 0)
    h, rem = divmod(sec, 3600); m, _ = divmod(rem, 60)
    if h > 0:
        return f"{h}h{m:02d}"
    return f"{m}min"


def _iso_monday(d: date) -> date:
    return d - timedelta(days=d.weekday())


# ============================================================================
# CALCUL DES ALLURES MARATHON
# ============================================================================

def _build_pace_palette(vma_kmh: Optional[float], target_time_s: Optional[int],
                       strategy_time_s: Optional[int]) -> dict:
    """
    Construit la palette d'allures utilisée par le plan.

    Sortie (toutes en sec/km, str formatté également) :
      vma, 10k, seuil, semi, marathon (depuis VMA, calibration Sébastien)
      mp_target  (cible chrono pure : marathon visé)
      mp_strategy (stratégie jour J, plus prudente)
      le_long    (sortie longue : ~mp_strategy + 30-40s)
      footing    (récupération / endurance : marathon + ~50-60s)
    """
    out = {'paces_sec': {}, 'paces_str': {}}

    if vma_kmh and derive_paces:
        d = derive_paces(vma_kmh)
        for k, v in d.items():
            if v:
                out['paces_sec'][k] = v
                out['paces_str'][k] = _fmt_pace(v)

    if target_time_s:
        mp_target = round(target_time_s / 42.195)
        out['paces_sec']['mp_target'] = mp_target
        out['paces_str']['mp_target'] = _fmt_pace(mp_target)

    if strategy_time_s:
        mp_strategy = round(strategy_time_s / 42.195)
        out['paces_sec']['mp_strategy'] = mp_strategy
        out['paces_str']['mp_strategy'] = _fmt_pace(mp_strategy)

    # Dérivés
    base = out['paces_sec'].get('mp_strategy') or out['paces_sec'].get('mp_target') or out['paces_sec'].get('marathon')
    if base:
        out['paces_sec']['le_long']  = base + 35   # SL ~ +35s/km vs MP
        out['paces_sec']['footing']  = base + 70   # footing récup ~ +70s/km
        out['paces_str']['le_long']  = _fmt_pace(out['paces_sec']['le_long'])
        out['paces_str']['footing']  = _fmt_pace(out['paces_sec']['footing'])

    return out


# ============================================================================
# VOLUME HEBDOMADAIRE PARAMÉTRIQUE
# ============================================================================

def _compute_user_peak_km(sessions: list[dict]) -> float:
    """Moyenne des 4 meilleures semaines des 6 derniers mois (km)."""
    if not sessions:
        return 55.0
    cutoff = datetime.now() - timedelta(days=180)
    wk = {}
    for s in sessions:
        try:
            d = datetime.strptime(s['d'], '%d/%m/%Y')
        except Exception:
            continue
        if d < cutoff:
            continue
        iy, iw, _ = d.isocalendar()
        key = (iy, iw)
        wk[key] = wk.get(key, 0) + s.get('km', 0)
    if not wk:
        return 55.0
    top4 = sorted(wk.values(), reverse=True)[:4]
    return sum(top4) / len(top4)


def _phase_for_week(week_index_from_end: int) -> str:
    """
    week_index_from_end : 0 = semaine de course, augmente vers le passé.
    Pour un plan 21 semaines :
      W21..W14 = base (8 sem)
      W13..W6  = specific (8 sem)
      W5..W3   = peak (3 sem)
      W2..W1   = taper (2 sem)
      W0       = race
    """
    if week_index_from_end == 0:
        return 'race'
    if week_index_from_end <= 2:
        return 'taper'
    if week_index_from_end <= 5:
        return 'peak'
    if week_index_from_end <= 13:
        return 'specific'
    return 'base'


def _volume_coef(phase: str, week_index_from_end: int) -> float:
    """Coefficient appliqué au volume pic naturel pour chaque semaine."""
    # Pic = 1.10 (15% au-dessus du naturel pour progresser)
    if phase == 'race':
        return 0.30   # 25-30% du pic, ~ marathon le dimanche
    if phase == 'taper':
        if week_index_from_end == 1:
            return 0.45
        return 0.65
    if phase == 'peak':
        # 3 semaines : 1.05 → 1.10 → 0.90 (décharge avant taper)
        if week_index_from_end == 3:
            return 0.90
        if week_index_from_end == 4:
            return 1.10
        return 1.05
    if phase == 'specific':
        # 8 semaines de specifique, cycle 3 charges + 1 récup
        cycle_pos = (13 - week_index_from_end) % 4
        if cycle_pos == 3:
            return 0.80    # semaine récup
        return 1.00 + 0.02 * (13 - week_index_from_end)  # progression douce
    # base : progression depuis 0.75 jusqu'à 0.95
    weeks_in_base = max(week_index_from_end - 13, 1)
    return min(0.95, 0.75 + 0.025 * (8 - weeks_in_base))


# ============================================================================
# GÉNÉRATION D'UNE SEMAINE
# ============================================================================

def _build_week_days(week_start: date, week_num: int, weeks_total: int,
                     phase: str, target_km: float, paces: dict,
                     goal_date: date) -> list[dict]:
    """
    Construit les 7 jours d'une semaine.

    Schéma type (varie selon phase) :
      Lun : repos
      Mar : qualité 1 (VMA / seuil / intervalles)
      Mer : footing + lignes droites
      Jeu : qualité 2 (allure marathon, tempo, ou seuil long)
      Ven : repos / footing récup
      Sam : footing + activation
      Dim : sortie longue
    """
    days = []
    weeks_left = weeks_total - week_num  # 0 = semaine de course
    days_to_race = (goal_date - week_start).days

    p = paces.get('paces_str', {})
    s = paces.get('paces_sec', {})

    # Allures par défaut si non renseignées
    pace_mp = p.get('mp_strategy') or p.get('mp_target') or p.get('marathon', '4\'15"/km')
    pace_mp_target = p.get('mp_target') or p.get('marathon', '4\'00"/km')
    pace_long = p.get('le_long', '4\'50"/km')
    pace_easy = p.get('footing', '5\'20"/km')
    pace_seuil = p.get('seuil', '3\'50"/km')
    pace_10k = p.get('10k', '3\'40"/km')
    pace_vma = p.get('vma', '3\'15"/km')

    # ===== SEMAINE DE COURSE =====
    if phase == 'race':
        # Calcul des jours selon position de la course dans la semaine
        for i in range(7):
            day_date = week_start + timedelta(days=i)
            dow = DOW_EN[day_date.weekday()]
            if day_date == goal_date:
                days.append({
                    'date': day_date.isoformat(), 'dow': dow,
                    'type': 'race', 'title': '🏁 MARATHON NYC',
                    'km': 42.2, 'duration_min': 180, 'key': True,
                    'description': f"Course objectif. Pacing {pace_mp} pour finir sub-3h. Hydratation + glucides toutes les 30min.",
                    'target_pace': pace_mp,
                })
            elif day_date < goal_date:
                # Jours avant la course : repos / activation très légère
                if (goal_date - day_date).days <= 1:
                    days.append({'date': day_date.isoformat(), 'dow': dow,
                                 'type': 'rest', 'title': 'Repos veille',
                                 'km': 0, 'duration_min': 0, 'key': False,
                                 'description': 'Repos complet. Sommeil, hydratation, glucides.'})
                elif (goal_date - day_date).days == 2:
                    days.append({'date': day_date.isoformat(), 'dow': dow,
                                 'type': 'shake', 'title': 'Activation 20min',
                                 'km': 4, 'duration_min': 20, 'key': False,
                                 'description': f"20min très facile {pace_easy} + 4-5 lignes droites de 80m. Réveille les jambes."})
                else:
                    days.append({'date': day_date.isoformat(), 'dow': dow,
                                 'type': 'easy', 'title': 'Footing court',
                                 'km': 6, 'duration_min': 35, 'key': False,
                                 'description': f"35min {pace_easy}. Maintien des automatismes."})
            else:
                # Après la course : récup
                days.append({'date': day_date.isoformat(), 'dow': dow,
                             'type': 'rest', 'title': 'Récupération',
                             'km': 0, 'duration_min': 0, 'key': False,
                             'description': 'Marche, étirements, alimentation.'})
        return days

    # ===== SEMAINES STANDARDS =====
    # Répartition du volume entre les 6 jours d'entraînement (lun=repos)
    if phase == 'taper':
        # Reduction des distances
        if weeks_left == 1:
            distrib = {'Mon': 0, 'Tue': 0.18, 'Wed': 0.15, 'Thu': 0.22, 'Fri': 0, 'Sat': 0.15, 'Sun': 0.30}
        else:
            distrib = {'Mon': 0, 'Tue': 0.18, 'Wed': 0.15, 'Thu': 0.20, 'Fri': 0.08, 'Sat': 0.14, 'Sun': 0.25}
    elif phase == 'peak':
        distrib = {'Mon': 0, 'Tue': 0.18, 'Wed': 0.13, 'Thu': 0.20, 'Fri': 0.10, 'Sat': 0.12, 'Sun': 0.27}
    elif phase == 'specific':
        distrib = {'Mon': 0, 'Tue': 0.18, 'Wed': 0.13, 'Thu': 0.20, 'Fri': 0.10, 'Sat': 0.12, 'Sun': 0.27}
    else:  # base
        distrib = {'Mon': 0, 'Tue': 0.16, 'Wed': 0.14, 'Thu': 0.18, 'Fri': 0.10, 'Sat': 0.14, 'Sun': 0.28}

    # Génération jour par jour
    for i in range(7):
        day_date = week_start + timedelta(days=i)
        dow = DOW_EN[day_date.weekday()]
        km = round(target_km * distrib.get(dow, 0), 1)

        # ===== LUNDI : repos =====
        if dow == 'Mon':
            days.append({'date': day_date.isoformat(), 'dow': dow,
                         'type': 'rest', 'title': 'Repos',
                         'km': 0, 'duration_min': 0, 'key': False,
                         'description': 'Repos complet ou mobilité/yoga 20-30min. Récupération.'})
            continue

        # ===== MARDI : qualité 1 =====
        if dow == 'Tue':
            qual = _quality_tuesday(phase, weeks_left, target_km, p, s)
            qual.update({'date': day_date.isoformat(), 'dow': dow,
                         'km': qual.get('km', round(target_km*0.18, 1))})
            days.append(qual); continue

        # ===== MERCREDI : footing =====
        if dow == 'Wed':
            days.append({'date': day_date.isoformat(), 'dow': dow,
                         'type': 'easy', 'title': f"Footing {round(km)}km",
                         'km': km, 'duration_min': round(km * 5.4), 'key': False,
                         'description': f"{round(km)}km à {pace_easy}. Allure conversationnelle, FC en zone 2."})
            continue

        # ===== JEUDI : qualité 2 =====
        if dow == 'Thu':
            qual = _quality_thursday(phase, weeks_left, target_km, p, s)
            qual.update({'date': day_date.isoformat(), 'dow': dow,
                         'km': qual.get('km', round(target_km*0.20, 1))})
            days.append(qual); continue

        # ===== VENDREDI : récup ou repos =====
        if dow == 'Fri':
            if km > 0:
                days.append({'date': day_date.isoformat(), 'dow': dow,
                             'type': 'recovery', 'title': f"Footing récup {round(km)}km",
                             'km': km, 'duration_min': round(km * 6), 'key': False,
                             'description': f"{round(km)}km très facile, allure récupération. FC zone 1-2 bas."})
            else:
                days.append({'date': day_date.isoformat(), 'dow': dow,
                             'type': 'rest', 'title': 'Repos',
                             'km': 0, 'duration_min': 0, 'key': False,
                             'description': 'Repos complet ou mobilité légère.'})
            continue

        # ===== SAMEDI : footing + activation =====
        if dow == 'Sat':
            days.append({'date': day_date.isoformat(), 'dow': dow,
                         'type': 'easy', 'title': f"Footing {round(km)}km + lignes",
                         'km': km, 'duration_min': round(km * 5.3), 'key': False,
                         'description': f"{round(km)}km à {pace_easy} + 4×100m lignes droites en fin. Activation pour la SL de dimanche."})
            continue

        # ===== DIMANCHE : sortie longue =====
        if dow == 'Sun':
            sl = _long_run_sunday(phase, weeks_left, target_km, p, s, km)
            sl.update({'date': day_date.isoformat(), 'dow': dow})
            days.append(sl); continue

    return days


def _quality_tuesday(phase: str, weeks_left: int, target_km: float, p: dict, s: dict) -> dict:
    """Séance qualité du mardi : VMA / 10K / Seuil court."""
    base_km = round(target_km * 0.18, 1)
    pace_vma = p.get('vma', '3\'15"/km')
    pace_10k = p.get('10k', '3\'40"/km')
    pace_seuil = p.get('seuil', '3\'50"/km')
    pace_easy = p.get('footing', '5\'20"/km')

    if phase == 'base':
        # Alternance VMA courte / fartlek
        if weeks_left % 2 == 0:
            return {'type': 'intervals', 'title': 'VMA courte · 10×400m',
                    'km': base_km, 'duration_min': round(base_km*5.5), 'key': True,
                    'description': f"20min échauffement {pace_easy}\n10×400m à VMA {pace_vma} · récup 1min trot\n10min retour calme {pace_easy}",
                    'target_pace': pace_vma}
        return {'type': 'fartlek', 'title': 'Fartlek 6×3min',
                'km': base_km, 'duration_min': round(base_km*5.5), 'key': True,
                'description': f"15min échauffement\n6×3min à allure 10K {pace_10k} · récup 2min footing\n10min retour calme",
                'target_pace': pace_10k}
    if phase == 'specific':
        if weeks_left % 2 == 0:
            return {'type': 'intervals', 'title': 'VMA longue · 5×1000m',
                    'km': base_km, 'duration_min': round(base_km*5.5), 'key': True,
                    'description': f"20min échauffement {pace_easy}\n5×1000m à 95-100% VMA {pace_vma} · récup 2min trot\n10min retour calme",
                    'target_pace': pace_vma}
        return {'type': 'intervals', 'title': '6×800m allure 5K',
                'km': base_km, 'duration_min': round(base_km*5.5), 'key': True,
                'description': f"20min échauffement\n6×800m à allure 5K (≈{pace_10k}) · récup 1'30 trot\n10min retour calme",
                'target_pace': pace_10k}
    if phase == 'peak':
        return {'type': 'intervals', 'title': '5×1km VMA',
                'km': base_km, 'duration_min': round(base_km*5.5), 'key': True,
                'description': f"20min échauffement\n5×1000m à VMA {pace_vma} · récup 2min\n10min retour calme. Entretien VO2max.",
                'target_pace': pace_vma}
    if phase == 'taper':
        return {'type': 'intervals', 'title': '4×800m VMA · maintien',
                'km': round(base_km * 0.8, 1), 'duration_min': round(base_km*4.5), 'key': True,
                'description': f"15min échauffement\n4×800m à VMA {pace_vma} · récup 1'30\n10min retour calme. Réveil neuromusculaire.",
                'target_pace': pace_vma}
    return {'type': 'easy', 'title': f'Footing {base_km}km', 'km': base_km,
            'duration_min': round(base_km*5.4), 'key': False,
            'description': f'Footing facile {pace_easy}'}


def _quality_thursday(phase: str, weeks_left: int, target_km: float, p: dict, s: dict) -> dict:
    """Séance qualité du jeudi : Seuil / Allure marathon."""
    base_km = round(target_km * 0.20, 1)
    pace_seuil = p.get('seuil', '3\'50"/km')
    pace_mp = p.get('mp_strategy', '4\'15"/km')
    pace_mp_target = p.get('mp_target', '4\'00"/km')
    pace_easy = p.get('footing', '5\'20"/km')
    pace_long = p.get('le_long', '4\'50"/km')

    if phase == 'base':
        return {'type': 'tempo', 'title': 'Tempo 20min seuil',
                'km': base_km, 'duration_min': round(base_km*5.2), 'key': True,
                'description': f"15min échauffement {pace_easy}\n20min en continu allure seuil {pace_seuil}\n10min retour calme",
                'target_pace': pace_seuil}
    if phase == 'specific':
        # Alternance allure marathon / seuil long
        if weeks_left % 2 == 0:
            mp_km = round(base_km * 0.6)
            return {'type': 'mp_run', 'title': f'{mp_km}km allure marathon',
                    'km': base_km, 'duration_min': round(base_km*5), 'key': True,
                    'description': f"15min échauffement {pace_easy}\n{mp_km}km à allure marathon cible {pace_mp}\n10min retour calme. Habituation à l'allure de course.",
                    'target_pace': pace_mp}
        return {'type': 'tempo', 'title': '2×15min seuil',
                'km': base_km, 'duration_min': round(base_km*5.2), 'key': True,
                'description': f"15min échauffement\n2×15min seuil {pace_seuil} · récup 3min trot\n10min retour calme",
                'target_pace': pace_seuil}
    if phase == 'peak':
        # Séances clés: long blocs MP
        mp_km = round(base_km * 0.7)
        return {'type': 'mp_run', 'title': f'{mp_km}km allure marathon · bloc',
                'km': base_km, 'duration_min': round(base_km*5), 'key': True,
                'description': f"15min échauffement\n{mp_km}km en bloc à allure marathon cible {pace_mp_target}\n10min retour calme. Test de tenue.",
                'target_pace': pace_mp_target}
    if phase == 'taper':
        mp_km = round(base_km * 0.4)
        return {'type': 'mp_run', 'title': f'{mp_km}km MP + 4 lignes',
                'km': base_km * 0.8, 'duration_min': round(base_km*4.5), 'key': True,
                'description': f"15min échauffement\n{mp_km}km allure marathon {pace_mp}\n10min calme + 4 lignes droites 80m. Vivacité.",
                'target_pace': pace_mp}
    return {'type': 'easy', 'title': f'Footing {base_km}km', 'km': base_km,
            'duration_min': round(base_km*5.4), 'key': False,
            'description': f'Footing facile {pace_easy}'}


def _long_run_sunday(phase: str, weeks_left: int, target_km: float, p: dict, s: dict, planned_km: float) -> dict:
    """Sortie longue du dimanche, avec progression et blocs MP en phase spécifique."""
    pace_long = p.get('le_long', '4\'50"/km')
    pace_mp = p.get('mp_strategy', '4\'15"/km')
    pace_mp_target = p.get('mp_target', '4\'00"/km')
    pace_easy = p.get('footing', '5\'20"/km')

    if phase == 'base':
        # 18-26km en endurance fondamentale
        km = max(planned_km, 18)
        return {'type': 'long', 'title': f'Sortie longue {round(km)}km',
                'km': round(km, 1), 'duration_min': round(km*5.3), 'key': True,
                'description': f"{round(km)}km en endurance {pace_long}. Apprends à tenir le rythme sans monter dans les tours.",
                'target_pace': pace_long}
    if phase == 'specific':
        # SL avec bloc MP au milieu ou progressif
        km = max(planned_km, 24)
        # Variante : 3 modèles tournants selon weeks_left
        cycle = (13 - weeks_left) % 3
        if cycle == 0:
            mp_km = 12
            return {'type': 'long_mp', 'title': f'SL {round(km)}km · 12km MP au milieu',
                    'km': round(km, 1), 'duration_min': round(km*5), 'key': True,
                    'description': f"{round(km)}km dont 12km à allure marathon {pace_mp_target} insérés au milieu. Le reste {pace_long}.",
                    'target_pace': pace_mp_target}
        elif cycle == 1:
            return {'type': 'long_prog', 'title': f'SL progressive {round(km)}km',
                    'km': round(km, 1), 'duration_min': round(km*5), 'key': True,
                    'description': f"{round(km)}km progressif : démarre {pace_long}, finis allure marathon {pace_mp}. Travail mental de fin.",
                    'target_pace': pace_mp}
        else:
            return {'type': 'long', 'title': f'SL endurance {round(km)}km',
                    'km': round(km, 1), 'duration_min': round(km*5.2), 'key': True,
                    'description': f"{round(km)}km en endurance fondamentale {pace_long}. Récup active après la SL spécifique.",
                    'target_pace': pace_long}
    if phase == 'peak':
        # SL signature : 30-35km avec gros bloc MP
        km = max(planned_km, 30)
        if weeks_left == 4:
            return {'type': 'long_mp', 'title': f'SL signature {round(km)}km · 20km MP',
                    'km': round(km, 1), 'duration_min': round(km*4.9), 'key': True,
                    'description': f"{round(km)}km dont 20km à allure marathon cible {pace_mp_target}. La séance clé du plan. Nutrition jour J en répétition.",
                    'target_pace': pace_mp_target}
        if weeks_left == 5:
            return {'type': 'long_mp', 'title': f'SL {round(km)}km · 2×8km MP',
                    'km': round(km, 1), 'duration_min': round(km*5), 'key': True,
                    'description': f"{round(km)}km · 2 blocs de 8km à allure marathon {pace_mp_target} séparés par 3km {pace_long}.",
                    'target_pace': pace_mp_target}
        return {'type': 'long_prog', 'title': f'SL progressive {round(km)}km',
                'km': round(km, 1), 'duration_min': round(km*5), 'key': True,
                'description': f"{round(km)}km progressif. Démarre {pace_long}, fini à {pace_mp}. Forge l'endurance spécifique.",
                'target_pace': pace_mp}
    if phase == 'taper':
        if weeks_left == 2:
            km = round(planned_km, 1)
            return {'type': 'long', 'title': f'SL pré-affûtage {round(km)}km',
                    'km': km, 'duration_min': round(km*5.1), 'key': True,
                    'description': f"{round(km)}km dont 10km en allure marathon {pace_mp}. Dernière SL de qualité.",
                    'target_pace': pace_mp}
        km = round(planned_km, 1)
        return {'type': 'long', 'title': f'SL de maintien {round(km)}km',
                'km': km, 'duration_min': round(km*5.3), 'key': False,
                'description': f"{round(km)}km en endurance {pace_long}. On garde le geste sans creuser la fatigue.",
                'target_pace': pace_long}
    km = max(planned_km, 16)
    return {'type': 'long', 'title': f'Sortie longue {round(km)}km',
            'km': round(km, 1), 'duration_min': round(km*5.3), 'key': True,
            'description': f"{round(km)}km à {pace_long}.",
            'target_pace': pace_long}


# ============================================================================
# GÉNÉRATION DU PLAN COMPLET
# ============================================================================

def generate_plan(
    goal_name: str,
    goal_date: str,        # 'YYYY-MM-DD'
    target_time: str,      # ex. "2h44'00"
    strategy_time: Optional[str],  # ex. "3h00'00"
    sessions: list[dict],
    vma_kmh: Optional[float] = None,
    weeks_total: Optional[int] = None,
    user_peak_km: Optional[float] = None,
) -> dict:
    """Génère le plan complet semaine par semaine."""
    g_date = datetime.strptime(goal_date, '%Y-%m-%d').date()
    today = date.today()

    # Calcul du nombre de semaines (semaine 1 = lundi de cette semaine)
    week0_monday = _iso_monday(today)
    days_to_race = (g_date - week0_monday).days
    if weeks_total is None:
        weeks_total = max(1, math.ceil(days_to_race / 7))
    # Limite raisonnable
    weeks_total = min(weeks_total, 30)

    # Détermination de la VMA à utiliser
    if vma_kmh is None and estimate_vma and sessions:
        try:
            est = estimate_vma(sessions)
            vma_kmh = est.get('vma')
        except Exception:
            vma_kmh = None

    target_s = _parse_goal_time_sec(target_time)
    strategy_s = _parse_goal_time_sec(strategy_time) if strategy_time else None
    paces = _build_pace_palette(vma_kmh, target_s, strategy_s)

    # Volume cible : pic naturel ou fourni
    peak = user_peak_km if user_peak_km else _compute_user_peak_km(sessions)
    # On vise un pic plan à 110% du pic naturel (progression réaliste)
    plan_peak = peak * 1.10

    # Construction des semaines
    weeks_data = []
    for week_num in range(1, weeks_total + 1):
        week_start = week0_monday + timedelta(weeks=week_num - 1)
        weeks_left = weeks_total - week_num  # 0 = semaine course
        phase = _phase_for_week(weeks_left)
        coef = _volume_coef(phase, weeks_left)
        target_km = round(plan_peak * coef, 1)

        days = _build_week_days(week_start, week_num, weeks_total, phase, target_km,
                                paces, g_date)

        weeks_data.append({
            'week_num': week_num,
            'weeks_left': weeks_left,
            'phase': phase,
            'phase_label': PHASE_LABELS.get(phase, phase),
            'start_date': week_start.isoformat(),
            'end_date': (week_start + timedelta(days=6)).isoformat(),
            'target_km': target_km,
            'days': days,
        })

    plan = {
        'meta': {
            'goal_name': goal_name,
            'goal_date': goal_date,
            'target_time': target_time,
            'strategy_time': strategy_time,
            'weeks_total': weeks_total,
            'plan_peak_km': round(plan_peak, 1),
            'user_peak_km': round(peak, 1),
            'vma_used': vma_kmh,
            'paces_str': paces.get('paces_str', {}),
            'paces_sec': paces.get('paces_sec', {}),
            'generated_at': datetime.now().isoformat(timespec='seconds'),
        },
        'weeks': weeks_data,
    }
    return plan


# ============================================================================
# MATCHING SÉANCES RÉELLES → PLAN
# ============================================================================

def attach_actuals(plan: dict, sessions: list[dict]) -> dict:
    """
    Marque chaque jour passé du plan :
      - 'done'   : séance prévue ET réalisée
      - 'bonus'  : séance réalisée un jour de repos (km prévu = 0)
      - 'over'   : séance réalisée nettement plus volumineuse que prévu
      - 'under'  : séance réalisée nettement moins volumineuse que prévu
      - 'missed' : jour avec km prévu et rien couru
      - 'pending': futur
      - 'today'  : aujourd'hui sans séance enregistrée
    Et attache .actual avec les détails de la séance Strava.
    """
    today = date.today()
    sess_by_date = {}
    for s in sessions:
        try:
            d = datetime.strptime(s['d'], '%d/%m/%Y').date()
        except Exception:
            continue
        sess_by_date.setdefault(d, []).append(s)

    for w in plan.get('weeks', []):
        for day in w.get('days', []):
            try:
                dd = date.fromisoformat(day['date'])
            except Exception:
                continue

            actuals = sess_by_date.get(dd, [])
            if actuals:
                total_km = sum(s.get('km', 0) for s in actuals)
                fcs = [s.get('fc') for s in actuals if s.get('fc')]
                avg_fc = round(sum(fcs)/len(fcs)) if fcs else None
                paces = [(s.get('ps'), s.get('km', 0)) for s in actuals if s.get('ps')]
                avg_pace = None
                if paces:
                    tot_w = sum(w_ for _, w_ in paces)
                    if tot_w > 0:
                        avg_pace = round(sum(p*w_ for p, w_ in paces)/tot_w)
                day['actual'] = {
                    'km': round(total_km, 1),
                    'duration_min': round(sum(s.get('dur_s', 0) for s in actuals) / 60),
                    'pace_sec': avg_pace,
                    'pace_str': _fmt_pace(avg_pace) if avg_pace else None,
                    'fc': avg_fc,
                    'type': actuals[0].get('tp'),
                    'title': actuals[0].get('t'),
                    'n': len(actuals),
                }
                planned_km = day.get('km', 0) or 0
                # Classification de la séance réalisée vs prévue
                if planned_km == 0 or day.get('type') == 'rest':
                    day['status'] = 'bonus'
                elif total_km < planned_km * 0.7:
                    day['status'] = 'under'
                elif total_km > planned_km * 1.3:
                    day['status'] = 'over'
                else:
                    day['status'] = 'done'
                # Scoring fin : réussie / partielle / échouée
                if score_day:
                    try:
                        day['score'] = score_day(day, actuals)
                    except Exception:
                        day['score'] = None
                continue

            if dd == today:
                day['status'] = 'today'
                day['actual'] = None
                continue
            if dd < today:
                if (day.get('km') or 0) > 0 and day.get('type') != 'rest':
                    day['status'] = 'missed'
                else:
                    day['status'] = 'done'  # repos prévu = ok
                day['actual'] = None
                continue
            day['status'] = 'pending'
            day['actual'] = None

    # Scores hebdo (conformité volume + qualité)
    if score_weeks:
        try:
            score_weeks(plan)
        except Exception:
            pass
    return plan


# ============================================================================
# ADAPTATION DU PLAN AUX SÉANCES RÉELLES
# ============================================================================

def adapt_plan(plan: dict) -> dict:
    """
    Adapte le plan en fonction du réel constaté (statuts attach_actuals).

    Trois mécaniques :
      1. **Reprogrammation séance clé manquée** : si une séance key=True a été
         manquée hier ou avant-hier, on tente de la repositionner sur le
         prochain jour de repos OU un footing facile, dans la semaine en cours.
         La séance déplacée garde son intent. La séance d'origine devient un
         footing récup léger.

      2. **Ajustement volume hebdo** : pour la semaine en cours, on compare
         volume cumulé réel vs cumulé prévu jusqu'à hier. Si écart > 15% :
            - sous-volume → on +5km sur la sortie longue du dimanche
            - sur-volume  → on -10% sur les footings/qualité à venir

      3. **Détection fatigue accumulée** : si ≥ 2 séances clés manquées sur
         les 10 derniers jours, on flag la semaine en cours en "récup" et on
         réduit les jours qui restent à 80%.

    Toutes les adaptations sont loggées dans plan['adaptations'] = [...]
    """
    today = date.today()
    plan.setdefault('adaptations', [])
    plan['adaptations'] = []  # repart à zéro pour ce build

    # --- 1. Récupère la semaine en cours et la prochaine
    current_w_idx = None
    for i, w in enumerate(plan.get('weeks', [])):
        try:
            ws = date.fromisoformat(w['start_date'])
            we = date.fromisoformat(w['end_date'])
            if ws <= today <= we:
                current_w_idx = i; break
        except Exception:
            continue
    if current_w_idx is None:
        return plan

    cur_week = plan['weeks'][current_w_idx]

    # --- 2. Détecte les séances clés manquées récentes
    missed_keys = []
    recent_cutoff = today - timedelta(days=10)
    for w in plan['weeks']:
        for day in w.get('days', []):
            try:
                dd = date.fromisoformat(day['date'])
            except Exception:
                continue
            if dd < recent_cutoff or dd >= today:
                continue
            if day.get('status') == 'missed' and day.get('key'):
                missed_keys.append(day)

    # --- 3. Reprogrammation : essaye de placer une séance clé manquée
    if missed_keys:
        # Cherche un slot dispo dans la semaine en cours (jours futurs uniquement)
        for missed in missed_keys[-1:]:  # on prend la plus récente
            slot = None
            for day in cur_week.get('days', []):
                try:
                    dd = date.fromisoformat(day['date'])
                except Exception:
                    continue
                if dd <= today:
                    continue
                # Slot acceptable : repos ou easy/recovery (pas de key déjà en place)
                if day.get('key'): continue
                if day.get('type') in ('rest', 'recovery', 'easy', 'shake'):
                    slot = day; break
            if slot:
                # Crée une note (on ne réécrit pas le titre original, on annote)
                slot['_rescheduled_from'] = missed.get('date')
                slot['_rescheduled_title'] = missed.get('title')
                slot['_rescheduled_desc']  = missed.get('description')
                slot['_rescheduled_pace']  = missed.get('target_pace')
                plan['adaptations'].append({
                    'kind': 'reschedule_key',
                    'from_date': missed.get('date'),
                    'to_date':   slot.get('date'),
                    'title':     missed.get('title'),
                    'reason':    "Séance clé manquée — repositionnée sur un jour libre",
                })

    # --- 4. Bilan volume semaine en cours (strictement passé : exclut aujourd'hui)
    planned_to_date = 0.0
    actual_to_date  = 0.0
    for day in cur_week.get('days', []):
        try:
            dd = date.fromisoformat(day['date'])
        except Exception:
            continue
        if dd >= today:
            continue
        planned_to_date += day.get('km', 0) or 0
        if day.get('actual'):
            actual_to_date += day['actual'].get('km', 0) or 0

    drift = (actual_to_date - planned_to_date)
    if planned_to_date > 0:
        drift_pct = drift / planned_to_date * 100
    else:
        drift_pct = 0

    # Note dans la semaine
    cur_week['volume_actual_to_date'] = round(actual_to_date, 1)
    cur_week['volume_planned_to_date'] = round(planned_to_date, 1)
    cur_week['volume_drift_pct'] = round(drift_pct, 1)

    # Ajustement (seulement si jours restants exploitables)
    future_days = [d for d in cur_week.get('days', [])
                   if date.fromisoformat(d['date']) > today and (d.get('km') or 0) > 0]
    # Pas d'ajustement si pas assez de données passées (< 2 jours)
    has_enough_history = planned_to_date >= 5
    if future_days and has_enough_history:
        if drift_pct < -15:
            # Sous-volume : +5km sur la sortie longue dimanche
            sl = next((d for d in future_days if d.get('type','').startswith('long')), None)
            if sl:
                bonus = min(5, max(2, abs(drift) / 2))
                sl['km'] = round(sl['km'] + bonus, 1)
                sl['description'] += f"\n[ADAPTÉ : +{bonus:.0f}km pour compenser le déficit volume de la semaine.]"
                plan['adaptations'].append({
                    'kind': 'volume_boost',
                    'date': sl.get('date'),
                    'delta_km': bonus,
                    'reason': f"Déficit volume {abs(drift_pct):.0f}%",
                })
        elif drift_pct > 15:
            # Sur-volume : -10% sur les footings/qualité à venir
            for d in future_days:
                if d.get('type') in ('easy', 'recovery'):
                    new_km = round(d['km'] * 0.9, 1)
                    d['km'] = new_km
                    d['description'] += "\n[ADAPTÉ : -10% pour gérer la charge de la semaine.]"
            plan['adaptations'].append({
                'kind': 'volume_reduce',
                'week_num': cur_week['week_num'],
                'delta_pct': -10,
                'reason': f"Sur-volume {drift_pct:+.0f}%",
            })

    # --- 5. Fatigue accumulée
    missed_recent = sum(1 for w in plan['weeks'] for d in w.get('days', [])
                       if d.get('status') == 'missed' and d.get('key'))
    if missed_recent >= 3 and future_days:
        for d in future_days:
            if d.get('key'):
                # Downgrade la qualité en footing
                d['_downgraded_from'] = {'title': d.get('title'), 'km': d.get('km'),
                                         'description': d.get('description')}
                d['title'] = f"Footing récup {round(d['km'] * 0.7)}km"
                d['type']  = 'recovery'
                d['km']    = round(d['km'] * 0.7, 1)
                d['key']   = False
                d['description'] = "Séance qualité downgradée en récup. Plusieurs séances clés manquées récemment — priorité à la régénération."
        plan['adaptations'].append({
            'kind': 'recovery_week',
            'week_num': cur_week['week_num'],
            'reason': f"{missed_recent} séances clés manquées — semaine de récup forcée",
        })

    return plan


def get_today_message(plan: dict) -> Optional[str]:
    """Retourne un message court résumant la séance du jour et l'adaptation."""
    today = get_today_session(plan)
    if not today:
        return None
    msg = f"{today.get('title','')}"
    if today.get('km'):
        msg += f" · {today['km']}km"
    if today.get('target_pace'):
        msg += f" · {today['target_pace']}"
    if today.get('_rescheduled_from'):
        msg += f"\n[REPLACÉ : {today.get('_rescheduled_title','')} — initialement {today['_rescheduled_from']}]"
    return msg


def get_today_session(plan: dict) -> Optional[dict]:
    """Retourne le dict du jour pour la séance d'aujourd'hui (ou None)."""
    today = date.today().isoformat()
    for w in plan.get('weeks', []):
        for day in w.get('days', []):
            if day.get('date') == today:
                return day
    return None


def get_current_week(plan: dict) -> Optional[dict]:
    """Retourne la semaine en cours."""
    today = date.today()
    for w in plan.get('weeks', []):
        try:
            ws = date.fromisoformat(w['start_date'])
            we = date.fromisoformat(w['end_date'])
            if ws <= today <= we:
                return w
        except Exception:
            continue
    return None


# ============================================================================
# PERSISTANCE
# ============================================================================

try:
    from modules.paths import data_dir as _data_dir
    PLAN_PATH = _data_dir() / 'plan_nyc.json'
except Exception:
    PLAN_PATH = Path.home() / 'Documents' / 'SebMetrics' / 'data' / 'plan_nyc.json'


def save_plan(plan: dict, path: Optional[Path] = None) -> Path:
    p = path or PLAN_PATH
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, 'w', encoding='utf-8') as f:
        json.dump(plan, f, ensure_ascii=False, indent=2, default=str)
    return p


def load_plan(path: Optional[Path] = None) -> Optional[dict]:
    p = path or PLAN_PATH
    if not p.exists():
        return None
    try:
        with open(p, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return None


# ============================================================================
# CLI DEBUG
# ============================================================================

if __name__ == '__main__':
    import sys
    cache_path = Path.home() / 'Documents' / 'SebMetrics' / 'data' / 'sessions_cache.json'
    if not cache_path.exists():
        print("✗ Cache introuvable")
        sys.exit(1)
    with open(cache_path) as f:
        cache = json.load(f)
    sessions = list(cache.values())

    plan = generate_plan(
        goal_name='NYC Marathon',
        goal_date='2026-11-01',
        target_time="2h44'00",
        strategy_time="3h00'00",
        sessions=sessions,
    )
    attach_actuals(plan, sessions)
    save_plan(plan)
    print(f"✓ Plan généré : {len(plan['weeks'])} semaines, sauvé dans {PLAN_PATH}")
    today = get_today_session(plan)
    if today:
        print(f"\nSéance du jour : {today['title']} ({today['km']}km)")
        print(f"  → {today['description']}")
    cur = get_current_week(plan)
    if cur:
        print(f"\nSemaine en cours : W{cur['week_num']} · {cur['phase_label']} · {cur['target_km']}km cible")
