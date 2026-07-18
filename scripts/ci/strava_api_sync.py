#!/usr/bin/env python3
"""
seb-metrics — scripts/ci/strava_api_sync.py
========================================
Sync Strava → inbox JSON, version CI (GitHub Actions).

Parle directement à l'API REST Strava (pas de MCP) et dépose un fichier
data/strava_inbox/sync_ci_YYYYMMDD_HHMMSS.json au format attendu par
modules/strava_sync.import_from_inbox. Le build (build.py --strava-sync)
merge ensuite dans sessions_cache.json avec dédup par strava_id.

Variables d'environnement requises (secrets GitHub Actions) :
  STRAVA_CLIENT_ID
  STRAVA_CLIENT_SECRET
  STRAVA_REFRESH_TOKEN

Optionnel :
  SEB_DATA_DIR       dossier data (défaut : ./data relatif à la racine repo)
  SYNC_LOOKBACK_DAYS fenêtre de récupération (défaut : 14 jours)

Usage : python3 scripts/ci/strava_api_sync.py
Sort avec code 0 même s'il n'y a rien de nouveau (le build gère).
"""
from __future__ import annotations
import json
import os
import sys
import time
import urllib.request
import urllib.parse
import urllib.error
from datetime import datetime, timedelta
from pathlib import Path

API = 'https://www.strava.com/api/v3'
RUN_TYPES = {'Run', 'TrailRun', 'VirtualRun'}


def _post(url: str, data: dict) -> dict:
    body = urllib.parse.urlencode(data).encode()
    req = urllib.request.Request(url, data=body, method='POST')
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode())


def _get(url: str, token: str, params: dict | None = None) -> dict | list:
    if params:
        url += '?' + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={'Authorization': f'Bearer {token}'})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode())


def get_access_token() -> str:
    cid = os.environ.get('STRAVA_CLIENT_ID')
    secret = os.environ.get('STRAVA_CLIENT_SECRET')
    refresh = os.environ.get('STRAVA_REFRESH_TOKEN')
    if not (cid and secret and refresh):
        print('✗ STRAVA_CLIENT_ID / STRAVA_CLIENT_SECRET / STRAVA_REFRESH_TOKEN manquants')
        sys.exit(1)
    tok = _post('https://www.strava.com/oauth/token', {
        'client_id': cid,
        'client_secret': secret,
        'grant_type': 'refresh_token',
        'refresh_token': refresh,
    })
    new_refresh = tok.get('refresh_token')
    if new_refresh and new_refresh != refresh:
        # Strava peut faire tourner le refresh token. À reporter dans le secret.
        print('⚠ Nouveau refresh_token émis par Strava — mets à jour le secret '
              'STRAVA_REFRESH_TOKEN (voir SETUP_AUTONOME.md §rotation).')
        print(f'::add-mask::{new_refresh}')
    return tok['access_token']


def existing_strava_ids(cache_path: Path) -> set[str]:
    if not cache_path.exists():
        return set()
    try:
        cache = json.loads(cache_path.read_text())
    except Exception:
        return set()
    ids = set()
    for v in cache.values():
        sid = v.get('_strava_id')
        if not sid and str(v.get('source', '')).startswith('strava_'):
            sid = v['source'].replace('strava_', '')
        if sid:
            ids.add(str(sid))
    return ids


def to_inbox_activity(summary_act: dict, detail: dict, laps: list[dict]) -> dict:
    """Convertit une activité REST Strava au format inbox (format MCP)."""
    start_local = (summary_act.get('start_date_local') or '').rstrip('Z')
    perf_laps = []
    for lap in laps or []:
        cad = lap.get('average_cadence')
        perf_laps.append({
            'elapsed_time': lap.get('elapsed_time'),
            'moving_time': lap.get('moving_time'),
            'distance': lap.get('distance'),
            'avg_hr': lap.get('average_heartrate'),
            # Strava renvoie la cadence "une jambe" → ×2 pour matcher le cache (spm)
            'avg_cadence': round(cad * 2) if cad else None,
            'avg_watts': lap.get('average_watts'),
        })
    return {
        'id': str(summary_act['id']),
        'name': summary_act.get('name', ''),
        'description': (detail or {}).get('description') or '',
        'sport_type': summary_act.get('sport_type', ''),
        'start_local': start_local,
        'summary': {
            'distance': summary_act.get('distance', 0),
            'moving_time': summary_act.get('moving_time', 0),
            'elapsed_time': summary_act.get('elapsed_time', 0),
            'elevation_gain': summary_act.get('total_elevation_gain', 0),
            'avg_speed': summary_act.get('average_speed', 0),
            'max_speed': summary_act.get('max_speed', 0),
            'avg_cadence': summary_act.get('average_cadence'),
            'relative_effort': summary_act.get('suffer_score'),
            'total_calories': (detail or {}).get('calories'),
            'kudos_count': summary_act.get('kudos_count', 0),
            'achievement_count': summary_act.get('achievement_count', 0),
            'pr_count': summary_act.get('pr_count', 0),
        },
        'performance': {
            'average_heartrate': summary_act.get('average_heartrate'),
            'max_heartrate': summary_act.get('max_heartrate'),
            'average_watts': summary_act.get('average_watts'),
            'laps': perf_laps,
        },
    }


def main():
    repo_root = Path(__file__).resolve().parents[2]
    data_dir = Path(os.environ.get('SEB_DATA_DIR') or (repo_root / 'data'))
    inbox = data_dir / 'strava_inbox'
    inbox.mkdir(parents=True, exist_ok=True)
    cache_path = data_dir / 'sessions_cache.json'

    lookback = int(os.environ.get('SYNC_LOOKBACK_DAYS', '14'))
    after_epoch = int((datetime.now() - timedelta(days=lookback)).timestamp())

    token = get_access_token()
    known = existing_strava_ids(cache_path)
    print(f'▸ Cache : {len(known)} activités Strava connues')

    acts = _get(f'{API}/athlete/activities', token,
                {'after': after_epoch, 'per_page': 50})
    runs = [a for a in acts if a.get('sport_type') in RUN_TYPES]
    new_runs = [a for a in runs if str(a['id']) not in known]
    print(f'▸ API Strava : {len(acts)} activités sur {lookback}j, '
          f'{len(runs)} runs, {len(new_runs)} nouvelles')

    if not new_runs:
        print('✓ Rien de nouveau.')
        return

    enriched = []
    for a in new_runs:
        aid = a['id']
        detail, laps = {}, []
        try:
            detail = _get(f'{API}/activities/{aid}', token)
            laps = detail.get('laps') or []
            if not laps:
                laps = _get(f'{API}/activities/{aid}/laps', token)
        except urllib.error.HTTPError as e:
            print(f'  ⚠ Détail {aid} : HTTP {e.code} — résumé seul')
        enriched.append(to_inbox_activity(a, detail, laps))
        print(f"  + {a.get('start_date_local','')[:10]} · {a.get('name','')[:48]} "
              f"({a.get('distance',0)/1000:.1f} km, {len(laps)} laps)")
        time.sleep(0.4)  # courtoisie rate-limit

    out = inbox / f"sync_ci_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    out.write_text(json.dumps({'activities': enriched}, ensure_ascii=False, indent=1))
    print(f'✓ {len(enriched)} activité(s) → {out.relative_to(repo_root)}')


if __name__ == '__main__':
    main()
