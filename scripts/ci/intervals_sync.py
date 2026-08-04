#!/usr/bin/env python3
"""
seb-metrics — scripts/ci/intervals_sync.py
==========================================
Récupère les .fit d'origine depuis intervals.icu et les dépose dans
`data/fit_inbox/`, où scripts/ci/fit_ingest.py prend le relais.

Pourquoi intervals.icu et pas Garmin en direct : Garmin réserve son API Connect
aux développeurs approuvés (dossier orienté entreprise). intervals.icu est
partenaire officiel : il aspire les séances depuis Garmin Connect tout seul,
conserve le fichier d'origine, et expose une API à clé personnelle — pas de
login à rejouer, pas de MFA, rien qui expire tout seul.

Le pipeline ne dépend PAS de ce script en particulier : n'importe quelle source
qui dépose des .fit dans data/fit_inbox/ fait l'affaire. Si intervals.icu
disparaît un jour, seul ce fichier est à remplacer.

Secrets attendus (GitHub Actions) :
  INTERVALS_API_KEY    clé personnelle (intervals.icu → Settings → Developer)
  INTERVALS_ATHLETE_ID identifiant athlète, de la forme i123456

Variables optionnelles :
  SEB_DATA_DIR         dossier data (défaut : ./data)
  INTERVALS_LOOKBACK   fenêtre en jours (défaut : 7)
"""
from __future__ import annotations
import base64
import json
import os
import sys
import urllib.error
import urllib.request
from datetime import date, timedelta
from pathlib import Path

API = 'https://intervals.icu/api/v1'
TIMEOUT = 45

# L'API ne documente pas un chemin unique pour le fichier d'origine selon les
# versions. On essaie les variantes connues dans l'ordre et on retient celle qui
# répond — la variante gagnante est affichée dans les logs du job.
FILE_ENDPOINTS = (
    '{api}/activity/{aid}/fit-file',
    '{api}/activity/{aid}/file',
    '{api}/athlete/{ath}/activities/{aid}/file',
)


def _auth_header(key: str) -> str:
    token = base64.b64encode(f'API_KEY:{key}'.encode()).decode()
    return f'Basic {token}'


def _request(url: str, key: str) -> bytes:
    req = urllib.request.Request(url, headers={
        'Authorization': _auth_header(key),
        'User-Agent': 'seb-metrics/1.0',
    })
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        return r.read()


def list_activities(key: str, athlete: str, days: int) -> list[dict]:
    oldest = (date.today() - timedelta(days=days)).isoformat()
    newest = date.today().isoformat()
    url = (f'{API}/athlete/{athlete}/activities'
           f'?oldest={oldest}&newest={newest}')
    data = json.loads(_request(url, key).decode('utf-8'))
    return [a for a in data if str(a.get('type', '')).lower().startswith('run')]


def download_fit(key: str, athlete: str, activity_id: str) -> bytes | None:
    last_error = None
    for tpl in FILE_ENDPOINTS:
        url = tpl.format(api=API, aid=activity_id, ath=athlete)
        try:
            blob = _request(url, key)
        except urllib.error.HTTPError as e:
            last_error = f'HTTP {e.code}'
            continue
        except Exception as e:  # noqa: BLE001
            last_error = str(e)
            continue
        # Un .fit commence par un en-tête dont l'octet 8-11 vaut ".FIT"
        if blob[:2] and (b'.FIT' in blob[:16] or blob[:2] == b'\x1f\x8b'):
            print(f'    (endpoint retenu : {tpl.split("{api}")[-1]})')
            return blob
        last_error = 'réponse non reconnue comme .fit'
    print(f'    ⚠ téléchargement impossible ({last_error})')
    return None


def main() -> int:
    key = os.environ.get('INTERVALS_API_KEY')
    athlete = os.environ.get('INTERVALS_ATHLETE_ID')
    if not key or not athlete:
        print('▸ INTERVALS_API_KEY / INTERVALS_ATHLETE_ID absents — étape ignorée.')
        return 0

    repo_root = Path(__file__).resolve().parents[2]
    data_dir = Path(os.environ.get('SEB_DATA_DIR') or (repo_root / 'data'))
    inbox = data_dir / 'fit_inbox'
    processed = inbox / 'processed'
    inbox.mkdir(parents=True, exist_ok=True)

    already = {p.name for p in list(inbox.glob('*.fit'))
               + list(processed.glob('*.fit'))} if inbox.exists() else set()

    days = int(os.environ.get('INTERVALS_LOOKBACK', '7'))
    try:
        acts = list_activities(key, athlete, days)
    except Exception as e:  # noqa: BLE001
        print(f'✗ Liste des activités impossible : {e}')
        return 0  # jamais bloquant : le reste du build doit passer

    print(f'▸ intervals.icu : {len(acts)} course(s) sur {days} j')
    got = 0
    for a in acts:
        aid = str(a.get('id') or '')
        name = f'{aid}.fit'
        if not aid or name in already:
            continue
        print(f"  ↓ {a.get('start_date_local', '')[:10]} · "
              f"{str(a.get('name', ''))[:40]}")
        blob = download_fit(key, athlete, aid)
        if blob:
            (inbox / name).write_bytes(blob)
            got += 1

    print(f'✓ {got} fichier(s) .fit déposé(s) dans fit_inbox/')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
