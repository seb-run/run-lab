"""
seb-metrics — modules/parser_fit.py
========================================
Parser FIT (Garmin / Strava export) + classification de séances.

Port Python du parser JS v8 (v8_app.js, fonctions parseFitBin + fitBuildSession).

Stratégie :
  1. Lecture FIT via fitdecode (robuste sur LAPs/headers exotiques)
  2. Priorité aux messages LAP (vraies reps) > fallback km-par-km depuis records
  3. Enrichissement des LAPs avec stride/balance/oscillation issus des records
  4. Détection GPS track (densité de points autour du centre médian)
  5. Classification multi-niveau : marathon / semi / sortie_longue / frac_court /
     frac_long / tempo / footing / endurance, avec priorité au champ Garmin
     `intensity` (workout structuré) puis fallback détection segments rapides.

Constantes FIT clés utilisées (records & laps) :
  - field 0  : position_lat  (semicircles)
  - field 1  : position_long (semicircles)
  - field 3  : heart_rate (records) / 15 : avg_hr (laps)
  - field 4  : cadence (records) / 17 : avg_cadence (laps)
  - field 5  : distance (records, cm) — distance cumulée
  - field 7  : power
  - field 23 : intensity (laps) — 0=active, 1=rest, 2=warmup, 3=cooldown, 4=recovery
  - field 39 : vertical_oscillation (0.1 mm → cm)
  - field 41 : stance_time (0.1 ms → ms)  [records]
  - field 77 : avg_stance_time (laps, 0.1 ms → ms)
  - field 79 : avg_vertical_oscillation (laps, 0.1 mm → cm)
  - field 84 : balance L/R (×100 → 50.xx %)
  - field 85 : stride_length (×10 → mm → m)

Sortie : dict session sérialisable JSON avec liste de blocs.
"""

from __future__ import annotations
import os
import math
import statistics
from datetime import datetime, timezone, timedelta
from typing import Any, Optional

try:
    import fitdecode
except ImportError as e:
    raise ImportError(
        "fitdecode est requis. Installe avec : pip install fitdecode"
    ) from e


# ============================================================================
# CONSTANTES
# ============================================================================

# Époque FIT : 31 décembre 1989 00:00 UTC
_FIT_EPOCH = datetime(1989, 12, 31, tzinfo=timezone.utc)

# Seuils de validité (anti-sentinelles 0xFFFF, vitesses absurdes)
_MIN_SPEED_MPS = 0.5      # < 0.5 m/s (1.8 km/h) = walk/static
_MAX_SPEED_MPS = 15.0     # > 15 m/s (54 km/h) = aberrant pour course à pied
_MIN_HR = 40

# Filtrage course à pied
# - sport : champ FIT session.sport
#   1 = running, 2 = cycling, 11 = walking, 5 = swimming, 17 = hiking, ...
#   On accepte uniquement 1 (running)
# - vitesse moyenne entre 6 km/h (1.667 m/s) et 25 km/h (6.944 m/s)
#   → exclut marche, randonnée lente, vélo, et activités hybrides
_RUNNING_SPORT_ID  = 1
_MIN_RUN_SPEED_MPS = 1.667   # 6 km/h
_MAX_RUN_SPEED_MPS = 6.944   # 25 km/h
_MAX_HR = 220
_MIN_DIST_KM = 0.5        # rejette séances < 500 m


# ============================================================================
# HELPERS
# ============================================================================

def fmt_pace(pace_sec_per_km: float) -> str:
    """Formate une allure en secondes/km vers \"M'SS\\\"/km\"."""
    if not pace_sec_per_km or pace_sec_per_km <= 0 or not math.isfinite(pace_sec_per_km):
        return ""
    m = int(pace_sec_per_km // 60)
    s = round(pace_sec_per_km % 60)
    if s >= 60:
        m += 1
        s = 0
    return f"{m}'{s:02d}\"/km"


def fmt_duration(sec: float) -> str:
    """Formate une durée en secondes vers \"Xh YYm ZZs\" ou \"Ym ZZs\"."""
    if not sec or sec <= 0:
        return ""
    h = int(sec // 3600)
    m = int((sec % 3600) // 60)
    s = round(sec % 60)
    if h > 0:
        return f"{h}h {m:02d}m {s:02d}s"
    return f"{m}m {s:02d}s"


def parse_pace(pace_str: str) -> Optional[float]:
    """\"4'30\\\"/km\" → 270 (secondes/km). Retourne None si invalide."""
    if not pace_str:
        return None
    import re
    m = re.match(r"(\d+)'(\d+)\"", pace_str)
    if not m:
        return None
    return int(m.group(1)) * 60 + int(m.group(2))


def _avg(values: list[float]) -> Optional[float]:
    """Moyenne robuste, retourne None si liste vide."""
    if not values:
        return None
    return sum(values) / len(values)


def _safe_get(rec: dict, field_num: int) -> Any:
    """Récupère un champ FIT par numéro, retourne None si absent."""
    return rec.get(field_num)


# ============================================================================
# LECTURE FIT VIA FITDECODE
# ============================================================================

def _read_fit_raw(fit_path: str) -> dict:
    """
    Lit un fichier .fit et retourne un dict :
      { 'session': dict[int, Any] | None,
        'records': list[dict[int, Any]],
        'laps':    list[dict[int, Any]] }
    Les clés sont des numéros de champ FIT bruts (compatibilité avec le parser JS v8).
    """
    session = None
    records: list[dict[int, Any]] = []
    laps: list[dict[int, Any]] = []
    # Valeurs décodées par NOM de champ (déjà mises à l'échelle par fitdecode).
    # Utilisées pour la dynamique de course : éviter de refaire à la main les
    # facteurs d'échelle (÷10, ÷100…) qui diffèrent d'un champ à l'autre.
    session_named: dict[str, Any] = {}
    laps_named: list[dict[str, Any]] = []
    hrv_rr: list[float] = []

    # fitdecode expose les champs par nom ET par def_num — on extrait par def_num
    # pour garder une compatibilité 1:1 avec les fields utilisés dans v8_app.js.
    with fitdecode.FitReader(fit_path) as fit:
        for frame in fit:
            if not isinstance(frame, fitdecode.FitDataMessage):
                continue
            msg_type = frame.name  # 'session', 'record', 'lap', ...
            if msg_type == 'hrv':
                # Intervalles R-R (secondes) enregistrés par la ceinture
                for field in frame.fields:
                    if field.name == 'time' and field.value:
                        hrv_rr.extend([v for v in field.value if v])
                continue
            if msg_type not in ('session', 'record', 'lap'):
                continue

            # Construction d'un dict {def_num: raw_value} pour compat parser v8
            rec: dict[int, Any] = {}
            for field in frame.fields:
                if field.def_num is None or field.def_num < 0:
                    continue
                val = field.raw_value
                # fitdecode peut renvoyer datetime pour timestamp — on garde
                rec[field.def_num] = val

            named = {f.name: f.value for f in frame.fields if f.value is not None}
            if msg_type == 'session' and session is None:
                session = rec
                session_named = named
            elif msg_type == 'record':
                records.append(rec)
            elif msg_type == 'lap':
                laps.append(rec)
                laps_named.append(named)

    return {'session': session or {}, 'records': records, 'laps': laps,
            'session_named': session_named, 'laps_named': laps_named,
            'hrv_rr': hrv_rr}


# ============================================================================
# CONSTRUCTION SÉANCE DEPUIS PARSED FIT
# ============================================================================

_FEEL_LABELS = {0: 'Très faible', 25: 'Faible', 50: 'Normal',
                75: 'Fort', 100: 'Très fort'}

# Écart au-delà duquel l'appui gauche/droite mérite d'être regardé. Garmin
# considère qu'un coureur symétrique reste dans ±1 % ; on alerte à 2 %.
_ASYM_THRESHOLD = 2.0
# Allongement du temps de contact au sol entre le 1er et le dernier tiers
# au-delà duquel on parle de dégradation mécanique.
_STANCE_FADE_PCT = 4.0
_STEP_FADE_PCT = -3.0


def _thirds(laps_named: list[dict], min_lap_m: float = 400.0) -> tuple[list, list]:
    """Découpe les laps exploitables en premier / dernier tiers de la distance."""
    usable = [l for l in (laps_named or [])
              if (l.get('total_distance') or 0) >= min_lap_m]
    total = sum(l['total_distance'] for l in usable)
    if total <= 0 or len(usable) < 4:
        return [], []
    cut = total / 3
    first, last, acc = [], [], 0.0
    for l in usable:
        if acc < cut:
            first.append(l)
        elif acc >= total - cut:
            last.append(l)
        acc += l['total_distance']
    return first, last


def _wavg(laps: list[dict], key: str) -> Optional[float]:
    """Moyenne pondérée par la distance d'un champ de lap."""
    num = den = 0.0
    for l in laps:
        v, d = l.get(key), l.get('total_distance') or 0
        if v is not None and d > 0:
            num += v * d
            den += d
    return (num / den) if den else None


def _pct_change(a: Optional[float], b: Optional[float]) -> Optional[float]:
    if a is None or b is None or a == 0:
        return None
    return round((b - a) / a * 100, 1)


def _build_dynamics(session_named: dict, laps_named: list[dict],
                    hrv_rr: list[float]) -> Optional[dict]:
    """
    Dynamique de course et charge, depuis les champs que Strava ne transmet pas.

    Trois usages visés :
      · fatigue mécanique — dérive du temps de contact au sol et de la foulée
        entre le premier et le dernier tiers de la séance ;
      · asymétrie gauche/droite — répartition du temps d'appui ;
      · charge — effet d'entraînement, charge Garmin, ressenti saisi à la montre.
    """
    s = session_named or {}
    if not s:
        return None
    dyn: dict[str, Any] = {}

    def put(key, name, factor=1.0, nd=1):
        v = s.get(name)
        if isinstance(v, (int, float)):
            dyn[key] = round(v * factor, nd)

    put('stance_ms', 'avg_stance_time', 1, 0)          # ms
    put('osc_cm', 'avg_vertical_oscillation', 0.1, 1)  # mm → cm
    put('vratio', 'avg_vertical_ratio', 1, 2)          # %
    put('balance_l', 'avg_stance_time_balance', 1, 2)  # % d'appui à gauche
    put('step_m', 'avg_step_length', 0.001, 2)         # mm → m
    put('temp_c', 'avg_temperature', 1, 0)
    put('temp_max', 'max_temperature', 1, 0)
    put('resp', 'enhanced_avg_respiration_rate', 1, 1)
    put('power', 'avg_power', 1, 0)
    put('np', 'normalized_power', 1, 0)
    put('te_aero', 'total_training_effect', 1, 1)
    put('te_ana', 'total_anaerobic_training_effect', 1, 1)
    put('load', 'training_load_peak', 1, 1)
    put('strides', 'total_strides', 1, 0)

    # Ressenti saisi sur la montre en fin de séance
    if isinstance(s.get('workout_rpe'), (int, float)):
        dyn['rpe'] = round(s['workout_rpe'] / 10, 1)      # 0-100 → 0-10
    if isinstance(s.get('workout_feel'), (int, float)):
        feel = int(s['workout_feel'])
        dyn['feel'] = feel
        dyn['feel_label'] = _FEEL_LABELS.get(feel, str(feel))

    # --- Dérive mécanique premier tiers → dernier tiers ---------------------
    first, last = _thirds(laps_named)
    if first and last:
        drift = {}
        for key, field, nd in (('stance', 'avg_stance_time', 0),
                               ('step', 'avg_step_length', 0),
                               ('vratio', 'avg_vertical_ratio', 2),
                               ('osc', 'avg_vertical_oscillation', 0),
                               ('hr', 'avg_heart_rate', 0),
                               ('cad', 'avg_running_cadence', 1)):
            a, b = _wavg(first, field), _wavg(last, field)
            if a is None or b is None:
                continue
            drift[key] = {'start': round(a, nd), 'end': round(b, nd),
                          'pct': _pct_change(a, b)}
        if drift:
            dyn['drift'] = drift

    # --- Asymétrie d'appui ---------------------------------------------------
    bals = [l['avg_stance_time_balance'] for l in (laps_named or [])
            if isinstance(l.get('avg_stance_time_balance'), (int, float))
            and (l.get('total_distance') or 0) >= 400]
    if bals:
        dyn['balance_min'] = round(min(bals), 2)
        dyn['balance_max'] = round(max(bals), 2)
        dyn['balance_series'] = [round(b, 2) for b in bals]

    # --- Asymétrie en fonction de l'allure -----------------------------------
    # Antécédent d'adducteur (hiver 2025) : la compensation ne se voyait pas à
    # allure facile mais s'ouvrait quand l'allure montait. On compare donc
    # l'équilibre d'appui sur les kilomètres rapides et sur les kilomètres
    # lents de la MÊME séance — un déséquilibre qui apparaît avec la vitesse
    # est un signal différent d'un déséquilibre constant.
    paced = [l for l in (laps_named or [])
             if (l.get('total_distance') or 0) >= 400
             and isinstance(l.get('avg_stance_time_balance'), (int, float))
             and (l.get('enhanced_avg_speed') or 0) > 0]
    if len(paced) >= 6:
        paced.sort(key=lambda l: l['enhanced_avg_speed'])
        third = max(2, len(paced) // 3)
        slow, fast = paced[:third], paced[-third:]
        b_slow = _wavg(slow, 'avg_stance_time_balance')
        b_fast = _wavg(fast, 'avg_stance_time_balance')
        v_slow = _wavg(slow, 'enhanced_avg_speed')
        v_fast = _wavg(fast, 'enhanced_avg_speed')
        if b_slow and b_fast and v_slow and v_fast and v_fast > v_slow * 1.03:
            dyn['balance_lent'] = round(b_slow, 2)
            dyn['balance_rapide'] = round(b_fast, 2)
            # Positif = l'asymétrie s'aggrave quand l'allure monte
            dyn['asym_vs_allure'] = round(abs(b_fast - 50) - abs(b_slow - 50), 2)
            dyn['allure_lent_s'] = round(1000 / v_slow)
            dyn['allure_rapide_s'] = round(1000 / v_fast)

    # --- Variabilité R-R pendant l'effort ------------------------------------
    # NB : ce n'est PAS le "statut HRV" de Garmin, qui se mesure au repos la
    # nuit et n'existe pas dans le fichier d'activité. On mesure ici la
    # variabilité pendant la course, à comparer à soi-même sur séances
    # équivalentes, jamais à une norme.
    rr = [v for v in (hrv_rr or []) if 0.25 < v < 2.0]
    if len(rr) > 100:
        diffs = [(rr[i + 1] - rr[i]) * 1000 for i in range(len(rr) - 1)]
        rmssd = (sum(d * d for d in diffs) / len(diffs)) ** 0.5
        dyn['rr_beats'] = len(rr)
        dyn['rmssd_effort'] = round(rmssd, 1)

    # --- Drapeaux ------------------------------------------------------------
    flags = []
    if dyn.get('balance_l') is not None and abs(dyn['balance_l'] - 50) > _ASYM_THRESHOLD:
        flags.append('asym')
    d = dyn.get('drift') or {}
    if (d.get('stance', {}).get('pct') or 0) >= _STANCE_FADE_PCT:
        flags.append('stance_fade')
    if (d.get('step', {}).get('pct') or 0) <= _STEP_FADE_PCT:
        flags.append('step_fade')
    if (dyn.get('asym_vs_allure') or 0) >= 1.5:
        flags.append('asym_vitesse')
    dyn['flags'] = flags
    return dyn


def _build_blocs_from_laps(laps: list[dict], records: list[dict]) -> list[dict]:
    """Construit la liste de blocs depuis les messages LAP (vraies intervals)."""
    blocs: list[dict] = []
    for lp in laps:
        # total_distance : field 9 (centimètres dans FIT raw → ÷ 1e5 pour km)
        ld_raw = _safe_get(lp, 9) or 0
        ld_km = ld_raw / 1e5 if isinstance(ld_raw, (int, float)) else 0
        if not math.isfinite(ld_km) or ld_km < 0 or ld_km > 200:
            ld_km = 0

        # timer_time (7) vs elapsed_time (8) — on prend le min (Garmin les inverse parfois)
        t7 = (_safe_get(lp, 7) or 0) / 1000
        t8 = (_safe_get(lp, 8) or 0) / 1000
        if t7 > 0 and t8 > 0:
            lt = min(t7, t8)
        else:
            lt = t7 or t8

        # Skip laps triviaux (<20 m ET <10 s)
        if ld_km <= 0.02 and lt <= 10:
            continue

        speed_mps = (ld_km * 1000) / lt if lt > 0 and ld_km > 0 else 0
        valid_speed = _MIN_SPEED_MPS < speed_mps <= _MAX_SPEED_MPS

        bloc = {
            'n': len(blocs) + 1,
            'km': round(ld_km, 3),
            'dur': fmt_duration(lt),
            'dur_s': round(lt),
            'a': fmt_pace(1000 / speed_mps) if valid_speed else "",
            'ps': round(1000 / speed_mps) if valid_speed else None,  # secondes/km
        }

        # FC moyenne du lap (field 15)
        fc = _safe_get(lp, 15)
        if fc and _MIN_HR < fc < _MAX_HR:
            bloc['fc'] = fc

        # Cadence moyenne (field 17) — souvent en SPM mono-jambe, ×2 si <120
        ca = _safe_get(lp, 17)
        if ca and ca > 0:
            bloc['ca'] = ca * 2 if ca < 120 else ca

        # Puissance moyenne (field 19)
        pw = _safe_get(lp, 19)
        if pw and pw > 0:
            bloc['pw'] = pw

        # Oscillation verticale moyenne (field 77 sur laps, 0.1 mm → cm)
        osc77 = _safe_get(lp, 77)
        if osc77 and osc77 > 0:
            bloc['os'] = round(osc77 / 10, 1) / 10  # 0.1 mm → cm avec 1 décimale

        # Temps de contact au sol moyen (field 79 sur laps, 0.1 ms → ms)
        ct79 = _safe_get(lp, 79)
        if ct79 and ct79 > 0:
            bloc['ct'] = round(ct79 / 10)

        # Équilibre d'appui G/D (field 119, ×100 → 50.xx %)
        bal119 = _safe_get(lp, 119)
        if bal119 and bal119 > 0:
            bloc['bal'] = round(bal119 / 100, 2)

        # Ratio vertical (field 118, ×100 → 9.xx %)
        vr118 = _safe_get(lp, 118)
        if vr118 and vr118 > 0:
            bloc['vr'] = round(vr118 / 100, 2)

        # Longueur de foulée (field 120, ×10 → mm → m)
        sl120 = _safe_get(lp, 120)
        if sl120 and sl120 > 0:
            bloc['fl'] = round(sl120 / 10000, 3)

        # Température (field 50, °C)
        t50 = _safe_get(lp, 50)
        if t50 is not None and -50 < t50 < 60:
            bloc['tc'] = t50

        # Intensité Garmin (field 23) — workout structuré
        intensity_raw = _safe_get(lp, 23)
        if intensity_raw is not None:
            intent_map = {0: 'active', 1: 'rest', 2: 'warmup', 3: 'cooldown', 4: 'recovery'}
            bloc['intent'] = intent_map.get(intensity_raw, str(intensity_raw))

        blocs.append(bloc)

    # Merge du dernier lap si trivial (<200 m) dans le précédent
    if len(blocs) >= 2 and blocs[-1]['km'] < 0.2:
        last = blocs[-1]
        prev = blocs[-2]
        total_km = prev['km'] + last['km']
        total_sec = prev['dur_s'] + last['dur_s']
        new_speed = (total_km * 1000) / total_sec if total_sec > 0 else 0
        prev['km'] = round(total_km, 3)
        prev['dur'] = fmt_duration(total_sec)
        prev['dur_s'] = total_sec
        prev['a'] = fmt_pace(1000 / new_speed) if new_speed > 0 else ""
        prev['ps'] = round(1000 / new_speed) if new_speed > 0 else None
        # FC pondérée par la distance
        if prev.get('fc') and last.get('fc'):
            prev['fc'] = round((prev['fc'] * prev['km'] + last['fc'] * last['km']) / (prev['km'] + last['km']))
        blocs.pop()

    # Enrichissement avec stride / balance / oscillation depuis records
    if len(records) > 10 and len(blocs) > 1:
        cum_dist = 0.0
        for bloc in blocs:
            b_start = cum_dist
            b_end = cum_dist + bloc['km']
            b_recs = []
            for r in records:
                d_raw = _safe_get(r, 5) or 0
                d_km = d_raw / 100000  # distance en cm × 100 ? non : record field 5 est en cm
                # En réalité field 5 = distance scaled ×100 (m → cm). v8 utilise /1e5 = km.
                if b_start <= d_km < b_end:
                    b_recs.append(r)

            # Stride length (field 85, échelle 10 → mm → m)
            strides = [r.get(85) for r in b_recs if r.get(85) and r.get(85) > 0]
            if strides:
                bloc['fl'] = round(sum(strides) / len(strides) / 10) / 1000

            # Balance L/R (field 84, ~5000 → 50.0%)
            bals = [r.get(84) for r in b_recs if r.get(84) and 4000 < r.get(84) < 6000]
            if bals:
                bloc['bal'] = round(sum(bals) / len(bals)) / 100

            # Oscillation depuis records si pas déjà mise par lap field 77
            if 'os' not in bloc:
                oscs = [r.get(39) for r in b_recs if r.get(39) and r.get(39) > 0]
                if oscs:
                    bloc['os'] = round(sum(oscs) / len(oscs) / 10) / 10

            cum_dist = b_end

    return blocs


def _build_blocs_fallback_km(records: list[dict], total_km: float, total_sec: float, avg_hr: Optional[int]) -> list[dict]:
    """Fallback : construit des blocs km-par-km depuis les records (pas de LAPs exploitables)."""
    if len(records) <= 10:
        # Pas de records → 1 seul bloc résumé
        speed = (total_km * 1000) / total_sec if total_sec > 0 else 0
        return [{
            'n': 1,
            'km': round(total_km, 2),
            'dur': fmt_duration(total_sec),
            'dur_s': round(total_sec),
            'a': fmt_pace(1000 / speed) if speed > 0 else "",
            'ps': round(1000 / speed) if speed > 0 else None,
            'fc': avg_hr if avg_hr and _MIN_HR < avg_hr < _MAX_HR else None,
        }]

    blocs: list[dict] = []
    current_km = 0
    segment_start_idx = 0

    for i, rec in enumerate(records):
        dist_m = (_safe_get(rec, 5) or 0) / 100  # cm → m
        km_num = int(dist_m // 1000)

        if km_num > current_km or i == len(records) - 1:
            segment = records[segment_start_idx:max(i, segment_start_idx + 1)]
            if len(segment) > 1:
                t0 = _safe_get(segment[0], 253)
                t1 = _safe_get(segment[-1], 253)
                bd = (t1 - t0) if t0 and t1 else 0
                if hasattr(bd, 'total_seconds'):
                    bd = bd.total_seconds()

                d0 = (_safe_get(segment[0], 5) or 0) / 1e5
                d1 = (_safe_get(segment[-1], 5) or 0) / 1e5
                dd = d1 - d0
                if dd <= 0:
                    dd = 1.0

                speed = (dd * 1000) / bd if bd > 0 else 0
                bloc = {
                    'n': current_km + 1,
                    'km': round(min(dd, 1.5), 2),
                    'dur': fmt_duration(bd),
                    'dur_s': round(bd) if bd else 0,
                    'a': fmt_pace(1000 / speed) if speed > 0 else "",
                    'ps': round(1000 / speed) if speed > 0 else None,
                }
                hrs = [r.get(3) for r in segment if r.get(3) and _MIN_HR < r.get(3) < _MAX_HR]
                if hrs:
                    bloc['fc'] = round(sum(hrs) / len(hrs))
                cds = [r.get(4) for r in segment if r.get(4) and r.get(4) > 0]
                if cds:
                    avg_cd = sum(cds) / len(cds)
                    bloc['ca'] = round(avg_cd * 2) if avg_cd < 120 else round(avg_cd)
                pws = [r.get(7) for r in segment if r.get(7) and r.get(7) > 0]
                if pws:
                    bloc['pw'] = round(sum(pws) / len(pws))
                blocs.append(bloc)

            current_km = km_num
            segment_start_idx = i

    if not blocs:
        speed = (total_km * 1000) / total_sec if total_sec > 0 else 0
        blocs.append({
            'n': 1,
            'km': round(total_km, 2),
            'dur': fmt_duration(total_sec),
            'dur_s': round(total_sec),
            'a': fmt_pace(1000 / speed) if speed > 0 else "",
            'ps': round(1000 / speed) if speed > 0 else None,
            'fc': avg_hr if avg_hr and _MIN_HR < avg_hr < _MAX_HR else None,
        })

    return blocs


def _detect_track(records: list[dict], total_km: float) -> bool:
    """Détecte si la séance s'est passée sur piste (densité GPS >1/3 dans rayon 200m du centre médian)."""
    SEMI = 180 / 2147483648  # conversion semicircles → degrés
    gps = [(r.get(0), r.get(1)) for r in records if r.get(0) and r.get(1) and r.get(0) != 0x7FFFFFFF]
    if len(gps) < 50 or total_km < 2:
        return False

    lats = sorted(p[0] * SEMI for p in gps)
    lngs = sorted(p[1] * SEMI for p in gps)
    median_lat = lats[len(lats) // 2]
    median_lng = lngs[len(lngs) // 2]
    cos_lat = math.cos(median_lat * math.pi / 180)

    near = 0
    for (lat_s, lng_s) in gps:
        lat = lat_s * SEMI
        lng = lng_s * SEMI
        a = (lat - median_lat) * 111320
        b = (lng - median_lng) * 111320 * cos_lat
        if math.sqrt(a * a + b * b) < 200:
            near += 1

    return near >= len(gps) / 3


def _classify_session(blocs: list[dict], total_km: float) -> tuple[str, float]:
    """
    Classification du type de séance.

    Renvoie : (type, coefficient_variation_pace)
      type ∈ {marathon, semi, sortie_longue, frac_court, frac_long, tempo, footing, endurance}

    Priorités :
      1. Distance pure : marathon ≥ 42, semi 21-22.5, SL ≥ 25
      2. Champ intensity Garmin (workout structuré) → frac_court/long selon avg_km
      3. Détection segments rapides consécutifs
      4. Coefficient de variation
      5. Allure moyenne (tempo si rapide, footing si lent)
    """
    bP = [b['ps'] for b in blocs if b.get('ps') and 150 < b['ps'] < 500]
    cv = 0
    if len(bP) > 2:
        mean_p = sum(bP) / len(bP)
        std = math.sqrt(sum((p - mean_p) ** 2 for p in bP) / len(bP))
        cv = round(100 * std / mean_p, 1) if mean_p else 0

    # Distance pure
    if total_km >= 42:
        return ('marathon', cv)
    if 21 <= total_km <= 22.5 and bP and (sum(bP) / len(bP)) <= 260:
        return ('semi', cv)
    if total_km >= 25:
        return ('sortie_longue', cv)

    # Intensity Garmin
    int_active = [b for b in blocs if b.get('intent') == 'active']
    int_rest = [b for b in blocs if b.get('intent') in ('rest', 'recovery')]
    use_intensity = len(int_active) >= 2 and len(int_rest) >= 1

    fast_segs = []
    if use_intensity:
        for b in blocs:
            if b.get('intent') == 'active':
                fast_segs.append({'km': b['km'], 'n': 1})
    else:
        cur = None
        for b in blocs:
            ps = b.get('ps')
            is_fast = ps and ps < 260
            if is_fast:
                if not cur:
                    cur = {'km': 0, 'n': 0}
                cur['km'] += b['km']
                cur['n'] += 1
            else:
                if cur:
                    fast_segs.append(cur)
                    cur = None
        if cur:
            fast_segs.append(cur)

    total_fast_km = sum(s['km'] for s in fast_segs)
    avg_seg_km = total_fast_km / len(fast_segs) if fast_segs else 0
    has_mix = len(fast_segs) >= 2 and (
        use_intensity or any(b.get('ps') and b['ps'] >= 300 for b in blocs)
    )

    if use_intensity and len(fast_segs) >= 3:
        return ('frac_court' if avg_seg_km <= 1.2 else 'frac_long', cv)
    if len(fast_segs) >= 2 and has_mix:
        return ('frac_court' if avg_seg_km <= 1.2 else 'frac_long', cv)
    if cv > 12 and len(bP) > 5:
        return ('frac_court' if avg_seg_km <= 1.2 else 'frac_long', cv)
    if bP and (sum(bP) / len(bP)) > 315:
        return ('footing', cv)
    if bP and (sum(bP) / len(bP)) < 260:
        return ('tempo', cv)

    return ('endurance', cv)


# ============================================================================
# API PUBLIQUE
# ============================================================================

def parse_fit_file(fit_path: str) -> Optional[dict]:
    """
    Parse un fichier .fit et retourne un dict session prêt à sérialiser en JSON.

    Format de sortie :
      {
        'd':      'JJ/MM/AAAA',       # date locale
        'h':      'HH:MM',
        't':      str,                # titre (= nom de fichier nettoyé)
        'km':     float,
        'dur':    str (Xh YYm ZZs),
        'dur_s':  int (secondes),
        'v':      float (km/h moyen),
        'a':      str (allure formattée),
        'ps':     int (sec/km),
        'fc':     int | None,
        'tp':     str (type séance),
        'cv':     float (coeff variation %),
        'track':  bool,
        'b':      list[dict] (blocs),
        'source': str (nom du fichier source),
      }
    Retourne None si la séance est invalide (trop courte, etc.).
    """
    try:
        parsed = _read_fit_raw(fit_path)
    except Exception as e:
        print(f"  ✗ Erreur parsing {os.path.basename(fit_path)} : {e}")
        return None

    ss = parsed['session']
    records = parsed['records']
    laps = parsed['laps']

    # Distance totale (field 9 sur session, cm dans le format raw)
    td_raw = _safe_get(ss, 9) or 0
    td_km = td_raw / 1e5 if isinstance(td_raw, (int, float)) else 0
    if td_km > 500 or td_km < 0:
        td_km = 0

    # FC moyenne (field 16)
    avg_hr = _safe_get(ss, 16)

    # Vitesse moyenne (field 14, mm/s → m/s)
    as_raw = _safe_get(ss, 14) or 0
    avg_speed = as_raw / 1000 if isinstance(as_raw, (int, float)) else 0
    if not math.isfinite(avg_speed) or avg_speed <= 0 or avg_speed > _MAX_SPEED_MPS:
        avg_speed = 0

    # Durée : min(timer_time, elapsed_time)
    t7 = (_safe_get(ss, 7) or 0) / 1000
    t8 = (_safe_get(ss, 8) or 0) / 1000
    if t7 > 0 and t8 > 0:
        total_sec = min(t7, t8)
    else:
        total_sec = t7 or t8

    # Recalcul vitesse depuis distance + durée si nécessaire
    if avg_speed <= 0 and total_sec > 0 and td_km > 0:
        avg_speed = (td_km * 1000) / total_sec

    # Rejet séances trop courtes
    if td_km < _MIN_DIST_KM:
        return None

    # === FILTRAGE COURSE À PIED ==============================================
    # Le champ FIT session.sport (field 5) identifie le sport déclaré par Garmin.
    # On rejette tout ce qui n'est pas running (1) : vélo, marche, natation, etc.
    sport_id = _safe_get(ss, 5)
    if sport_id is not None and sport_id != _RUNNING_SPORT_ID:
        return None

    # Filtre vitesse course : 6 km/h ≤ avg_speed ≤ 25 km/h
    # Exclut : marches/randos (< 6 km/h) et activités cyclisme mal taggées (> 25 km/h)
    if avg_speed > 0 and (avg_speed < _MIN_RUN_SPEED_MPS or avg_speed > _MAX_RUN_SPEED_MPS):
        return None
    # =========================================================================

    # Timestamp de la séance (field 253, secondes depuis FIT epoch)
    ts_raw = _safe_get(ss, 253)
    if isinstance(ts_raw, datetime):
        dt = ts_raw
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        dt = dt.astimezone()  # convertit en heure locale
    elif isinstance(ts_raw, (int, float)) and ts_raw > 0:
        dt = (_FIT_EPOCH + timedelta(seconds=ts_raw)).astimezone()
    else:
        # Fallback : mtime du fichier
        dt = datetime.fromtimestamp(os.path.getmtime(fit_path))

    # Construction des blocs
    if len(laps) > 1:
        blocs = _build_blocs_from_laps(laps, records)
        # Si les laps n'ont rien donné de valable, fallback
        if not blocs or all(b['km'] < 0.1 for b in blocs):
            blocs = _build_blocs_fallback_km(records, td_km, total_sec, avg_hr)
    else:
        blocs = _build_blocs_fallback_km(records, td_km, total_sec, avg_hr)

    # Détection track
    is_track = _detect_track(records, td_km)

    # Classification
    tp, cv = _classify_session(blocs, td_km)

    # Dynamique de course / charge (champs absents de l'API Strava)
    dyn = _build_dynamics(parsed.get('session_named') or {},
                          parsed.get('laps_named') or [],
                          parsed.get('hrv_rr') or [])

    # Nom de fichier nettoyé
    fname = os.path.basename(fit_path)
    title = fname.replace('.fit', '').replace('.gz', '').replace('_', ' ').strip()

    return {
        'd': dt.strftime('%d/%m/%Y'),
        'h': dt.strftime('%H:%M'),
        't': title,
        'km': round(td_km, 2),
        'dur': fmt_duration(total_sec),
        'dur_s': round(total_sec),
        'v': round(avg_speed * 3.6, 2),
        'a': fmt_pace(1000 / avg_speed) if avg_speed > 0 else "",
        'ps': round(1000 / avg_speed) if avg_speed > 0 else None,
        'fc': avg_hr if avg_hr and _MIN_HR < avg_hr < _MAX_HR else None,
        'tp': tp,
        'cv': cv,
        'track': is_track,
        'b': blocs,
        'dyn': dyn,
        'source': fname,
    }


def parse_fit_directory(directory: str, on_progress=None) -> list[dict]:
    """
    Parse récursivement tous les .fit d'un dossier.

    Args:
      directory : chemin racine
      on_progress : callback(current, total, filename) — optionnel

    Returns:
      Liste de sessions parsées (None filtrés).
    """
    fit_files = []
    for root, _, files in os.walk(directory):
        for f in files:
            if f.lower().endswith(('.fit', '.fit.gz')):
                fit_files.append(os.path.join(root, f))

    sessions = []
    total = len(fit_files)
    for i, fp in enumerate(fit_files, 1):
        if on_progress:
            on_progress(i, total, os.path.basename(fp))
        sess = parse_fit_file(fp)
        if sess:
            sessions.append(sess)

    # Tri par date (plus récent en premier — cohérent avec v8 qui fait sort desc)
    sessions.sort(key=lambda s: datetime.strptime(s['d'] + ' ' + s['h'], '%d/%m/%Y %H:%M'), reverse=True)
    return sessions


# ============================================================================
# CLI standalone (debug)
# ============================================================================

if __name__ == '__main__':
    import sys
    import json
    if len(sys.argv) < 2:
        print("Usage: python parser_fit.py <fichier.fit | dossier/>")
        sys.exit(1)

    target = sys.argv[1]
    if os.path.isfile(target):
        result = parse_fit_file(target)
        print(json.dumps(result, indent=2, ensure_ascii=False, default=str))
    elif os.path.isdir(target):
        def progress(i, n, fn):
            print(f"  [{i}/{n}] {fn}")
        sessions = parse_fit_directory(target, on_progress=progress)
        print(f"\n✓ {len(sessions)} séances parsées")
        if sessions:
            print(f"  Dernière : {sessions[0]['d']} — {sessions[0]['t']} ({sessions[0]['km']} km)")
    else:
        print(f"✗ Chemin invalide : {target}")
        sys.exit(1)
