"""
seb-metrics — modules/strava_sync.py
========================================
Synchronisation Strava → cache sessions_cache.json.

Architecture :
  - L'agent Claude (tâche planifiée) appelle Strava MCP `list_activities` puis
    `get_activity_performance` pour les nouvelles activités, et dépose le JSON
    brut dans ~/Documents/SebMetrics/data/strava_inbox/.
  - Ce module convertit le JSON Strava au format du cache (compatible parser_fit),
    et merge dans sessions_cache.json (dedup par strava_id).

Format Strava attendu :
  {
    "id": "18807282234",
    "name": "...", "sport_type": "Run|TrailRun",
    "start_local": "2026-06-06T10:48:52",
    "summary": {distance, moving_time, elevation_gain, avg_speed, avg_cadence, total_calories, ...},
    "performance": {average_heartrate, max_heartrate, average_watts, laps: [...], best_efforts: [...]}
  }
"""
from __future__ import annotations
import json
import os
import hashlib
from datetime import datetime
from pathlib import Path
from typing import Optional


# ============================================================================
# UTILITAIRES
# ============================================================================

def _fmt_pace(sec_per_km: float) -> str:
    if not sec_per_km or sec_per_km <= 0:
        return ""
    m = int(sec_per_km // 60)
    s = int(round(sec_per_km % 60))
    if s >= 60:
        m += 1; s = 0
    return f"{m}'{s:02d}\"/km"


def _fmt_duration(sec: float) -> str:
    sec = int(sec or 0)
    h, rem = divmod(sec, 3600); m, s = divmod(rem, 60)
    if h > 0:
        return f"{h}h {m:02d}m {s:02d}s"
    return f"{m}m {s:02d}s"


def _classify_from_laps(laps: list[dict], total_km: float, avg_pace_s: float) -> tuple[str, float]:
    """Reproduit la logique de parser_fit._classify_session de façon simplifiée."""
    if total_km >= 42.0:
        return ('marathon', 0)
    if 21.0 <= total_km <= 22.5 and avg_pace_s and avg_pace_s <= 260:
        return ('semi', 0)
    if total_km >= 25.0:
        return ('sortie_longue', 0)

    # Calcul CV sur les laps
    paces = []
    for lap in laps or []:
        et = lap.get('elapsed_time') or lap.get('moving_time') or 0
        dist = lap.get('distance', 0)
        if et > 0 and dist > 0:
            pace_s_per_km = et / (dist / 1000.0)
            if 180 <= pace_s_per_km <= 600:
                paces.append(pace_s_per_km)
    if not paces:
        # fallback sur allure moyenne
        if avg_pace_s and avg_pace_s < 260:
            return ('tempo', 0)
        if avg_pace_s and avg_pace_s > 315:
            return ('footing', 0)
        return ('endurance', 0)

    mean = sum(paces) / len(paces)
    if mean > 0:
        var = sum((p - mean) ** 2 for p in paces) / len(paces)
        cv = (var ** 0.5 / mean) * 100
    else:
        cv = 0

    fast = [p for p in paces if p <= 240]   # < 4'/km
    slow = [p for p in paces if p >= 300]   # >= 5'/km
    has_mix = len(fast) >= 2 and len(slow) >= 1

    fast_lap_dists = [(l.get('distance', 0)/1000.0)
                       for l in laps if (l.get('elapsed_time') or l.get('moving_time') or 0) > 0
                       and l.get('distance', 0) > 0
                       and (l.get('elapsed_time') or l.get('moving_time'))/(l['distance']/1000.0) <= 240]
    avg_fast_km = sum(fast_lap_dists)/len(fast_lap_dists) if fast_lap_dists else 0

    if len(fast) >= 3 and has_mix:
        tp = 'frac_court' if avg_fast_km <= 1.2 else 'frac_long'
        return (tp, cv)
    if cv > 12 and len(paces) > 5:
        tp = 'frac_court' if avg_fast_km <= 1.2 else 'frac_long'
        return (tp, cv)
    if mean > 315:
        return ('footing', cv)
    if mean < 260:
        return ('tempo', cv)
    return ('endurance', cv)


def _build_blocs_from_laps(laps: list[dict]) -> list[dict]:
    """Convertit les laps Strava au format bloc du cache."""
    blocs = []
    for i, lap in enumerate(laps or [], 1):
        et = lap.get('elapsed_time') or lap.get('moving_time') or 0
        dist_m = lap.get('distance', 0)
        if et <= 0 or dist_m <= 0:
            continue
        km = round(dist_m / 1000.0, 3)
        pace_s = round(et / (dist_m / 1000.0))
        blocs.append({
            'n': i,
            'km': km,
            'dur': _fmt_duration(et),
            'dur_s': int(et),
            'a': _fmt_pace(pace_s),
            'ps': pace_s,
            'fc': round(lap['avg_hr']) if lap.get('avg_hr') else None,
            'ca': round(lap['avg_cadence']) if lap.get('avg_cadence') else None,
            'pw': round(lap['avg_watts']) if lap.get('avg_watts') else None,
            'os': None,
            'ct': None,
            'intent': 'active' if (pace_s and pace_s < 260) else None,
            'fl': None,
        })
    return blocs


# ============================================================================
# CONVERSION STRAVA → SESSION
# ============================================================================

def strava_to_session(activity: dict) -> Optional[dict]:
    """
    Convertit une activité Strava (avec champ optionnel `performance`) en
    session dict compatible avec le cache.
    """
    sport = activity.get('sport_type', '')
    if sport not in ('Run', 'TrailRun', 'VirtualRun'):
        return None

    summary = activity.get('summary', {}) or {}
    perf = activity.get('performance', {}) or {}

    dist_m = summary.get('distance', 0)
    if dist_m < 500:
        return None
    km = round(dist_m / 1000.0, 2)
    moving = summary.get('moving_time') or summary.get('elapsed_time') or 0
    if moving <= 0:
        return None

    avg_speed_mps = summary.get('avg_speed') or (dist_m / moving if moving > 0 else 0)
    speed_kmh = round(avg_speed_mps * 3.6, 2)
    pace_s = round(1000.0 / avg_speed_mps) if avg_speed_mps > 0 else None

    # Heart rate (depuis performance)
    hr = perf.get('average_heartrate')
    if hr:
        hr = round(hr)

    # Parse start_local
    start_local = activity.get('start_local', '')
    try:
        dt = datetime.fromisoformat(start_local)
    except Exception:
        try:
            dt = datetime.strptime(start_local, '%Y-%m-%dT%H:%M:%S')
        except Exception:
            return None

    # Blocs depuis les laps de performance
    laps = perf.get('laps', [])
    blocs = _build_blocs_from_laps(laps)

    # Classification
    tp, cv = _classify_from_laps(laps, km, pace_s)

    # Titre nettoyé
    title = activity.get('name', f"Activité {activity.get('id', '')}").strip()
    # Supprime les emojis basiques du nom pour matcher le style des .fit
    # On garde quand même les caractères, ils sont supportés en JSON

    return {
        'd': dt.strftime('%d/%m/%Y'),
        'h': dt.strftime('%H:%M'),
        't': title,
        'km': km,
        'dur': _fmt_duration(moving),
        'dur_s': int(moving),
        'v': speed_kmh,
        'a': _fmt_pace(pace_s) if pace_s else "",
        'ps': pace_s,
        'fc': hr,
        'tp': tp,
        'cv': round(cv, 2) if cv else 0,
        'track': False,
        'b': blocs,
        'source': f"strava_{activity.get('id')}",
        '_strava_id': str(activity.get('id', '')),
        '_md5': f"strava-{activity.get('id', '')}",
    }


# ============================================================================
# MERGE DANS LE CACHE
# ============================================================================

def merge_into_cache(cache_path: Path, activities: list[dict]) -> dict:
    """
    Merge une liste d'activités Strava dans le cache, en dédupant par strava_id.

    Returns: stats {'added': N, 'updated': N, 'skipped': N, 'total': N}
    """
    cache = {}
    if cache_path.exists():
        with open(cache_path, 'r', encoding='utf-8') as f:
            cache = json.load(f)

    # Index des strava_ids déjà présents
    existing_strava_ids = {}
    for k, v in cache.items():
        sid = v.get('_strava_id') or (v.get('source', '').replace('strava_', '') if v.get('source', '').startswith('strava_') else None)
        if sid:
            existing_strava_ids[sid] = k

    stats = {'added': 0, 'updated': 0, 'skipped': 0, 'total': len(activities)}
    for act in activities:
        sid = str(act.get('id', ''))
        if not sid:
            stats['skipped'] += 1; continue
        sess = strava_to_session(act)
        if not sess:
            stats['skipped'] += 1; continue

        key = sess['_md5']  # 'strava-{id}'
        if sid in existing_strava_ids:
            existing_key = existing_strava_ids[sid]
            cache[existing_key] = sess
            stats['updated'] += 1
        else:
            # Détection collision possible avec .fit déjà importé sur même date+km
            # (cas typique : le user dropped le .fit en plus du sync Strava)
            colliding = False
            for k, v in cache.items():
                if v.get('d') == sess['d'] and abs((v.get('km',0) - sess['km'])) < 0.2 \
                   and abs((v.get('dur_s',0) - sess['dur_s'])) < 60:
                    colliding = True
                    break
            if colliding:
                stats['skipped'] += 1
                continue
            cache[key] = sess
            stats['added'] += 1

    cache_path.parent.mkdir(parents=True, exist_ok=True)
    with open(cache_path, 'w', encoding='utf-8') as f:
        json.dump(cache, f, ensure_ascii=False, default=str)

    return stats


def import_from_inbox(inbox_dir: Path, cache_path: Path) -> dict:
    """
    Importe tous les fichiers .json de l'inbox Strava et les merge dans le cache.
    Les fichiers traités sont déplacés dans inbox_dir/processed/.
    """
    inbox_dir.mkdir(parents=True, exist_ok=True)
    processed_dir = inbox_dir / 'processed'
    processed_dir.mkdir(parents=True, exist_ok=True)

    files = sorted(inbox_dir.glob('*.json'))
    all_acts = []
    for fp in files:
        try:
            with open(fp, 'r', encoding='utf-8') as f:
                data = json.load(f)
            # Soit une liste d'activités, soit un dict avec 'activities'
            if isinstance(data, list):
                all_acts.extend(data)
            elif isinstance(data, dict):
                if 'activities' in data:
                    all_acts.extend(data['activities'])
                else:
                    all_acts.append(data)
        except Exception as e:
            print(f"  ✗ {fp.name} : {e}")
            continue

    if not all_acts:
        return {'added': 0, 'updated': 0, 'skipped': 0, 'total': 0, 'files': len(files)}

    stats = merge_into_cache(cache_path, all_acts)
    stats['files'] = len(files)

    # Archivage
    for fp in files:
        target = processed_dir / f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{fp.name}"
        fp.rename(target)

    return stats


# ============================================================================
# CLI
# ============================================================================

if __name__ == '__main__':
    import sys
    cache_path = Path.home() / 'Documents' / 'SebMetrics' / 'data' / 'sessions_cache.json'
    inbox_path = Path.home() / 'Documents' / 'SebMetrics' / 'data' / 'strava_inbox'

    if len(sys.argv) > 1 and sys.argv[1] == '--inbox':
        stats = import_from_inbox(inbox_path, cache_path)
        print(f"✓ Inbox traitée : {stats}")
    else:
        # Mode : lit un JSON depuis stdin
        data = json.load(sys.stdin)
        if isinstance(data, dict) and 'activities' in data:
            acts = data['activities']
        elif isinstance(data, list):
            acts = data
        else:
            acts = [data]
        stats = merge_into_cache(cache_path, acts)
        print(f"✓ Merge : {stats}")
