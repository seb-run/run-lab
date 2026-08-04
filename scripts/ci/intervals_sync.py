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
# ORDRE IMPORTANT : intervals.icu sert deux fichiers différents pour une même
# séance — l'ORIGINAL reçu de Garmin, et son propre ré-encodage. Le ré-encodage
# perd la dynamique par lap, la température, la puissance, l'effet
# d'entraînement et le RPE saisi sur la montre. On cherche donc l'original
# d'abord, et on ne se rabat sur le ré-encodage qu'en dernier recours.
FILE_ENDPOINTS = (
    '{api}/activity/{aid}/file',
    '{api}/activity/{aid}/original',
    '{api}/athlete/{ath}/activities/{aid}/file',
    '{api}/activity/{aid}/fit-file',
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


def probe_athlete(key: str, athlete: str) -> None:
    """Vérifie que l'identifiant athlète résout bien vers un compte."""
    try:
        prof = json.loads(_request(f'{API}/athlete/{athlete}/profile',
                                   key).decode('utf-8'))
        who = (prof.get('athlete') or prof)
        print(f"  compte : {who.get('name') or who.get('id') or athlete}")
    except Exception as e:  # noqa: BLE001
        print(f'  ⚠ profil athlète illisible ({e}) — vérifier INTERVALS_ATHLETE_ID')


def list_activities(key: str, athlete: str, days: int) -> list[dict]:
    oldest = (date.today() - timedelta(days=days)).isoformat()
    newest = date.today().isoformat()
    url = (f'{API}/athlete/{athlete}/activities'
           f'?oldest={oldest}&newest={newest}')
    data = json.loads(_request(url, key).decode('utf-8'))
    if not isinstance(data, list):
        print(f'  ⚠ réponse inattendue : {str(data)[:200]}')
        return []

    # Diagnostic : sans ça, un filtre trop strict et un compte réellement vide
    # produisent exactement le même « 0 course ».
    types = sorted({str(a.get('type') or a.get('sport') or '?') for a in data})
    print(f'  {len(data)} activité(s) toutes disciplines sur la fenêtre'
          + (f" — types vus : {', '.join(types)}" if types else ''))
    if data:
        first = data[0]
        print(f"  exemple de champs : {', '.join(sorted(first.keys())[:14])}")

    runs = [a for a in data
            if str(a.get('type') or a.get('sport') or '').lower().startswith('run')]
    if data and not runs:
        print('  ⚠ aucune activité reconnue comme course : le filtre de type '
              'ne correspond pas aux valeurs ci-dessus.')
    return runs


def download_fit(key: str, athlete: str, activity_id: str,
                 verbose: bool = False) -> bytes | None:
    last_error = None
    for tpl in FILE_ENDPOINTS:
        url = tpl.format(api=API, aid=activity_id, ath=athlete)
        short = tpl.split('{api}')[-1]
        try:
            blob = _request(url, key)
        except urllib.error.HTTPError as e:
            last_error = f'HTTP {e.code}'
            if verbose:
                print(f'      {short} → HTTP {e.code}')
            continue
        except Exception as e:  # noqa: BLE001
            last_error = str(e)
            continue
        # Un .fit commence par un en-tête dont l'octet 8-11 vaut ".FIT"
        if blob[:2] and (b'.FIT' in blob[:16] or blob[:2] == b'\x1f\x8b'):
            print(f'    (endpoint retenu : {short} — {len(blob) // 1024} Ko)')
            return blob
        last_error = 'réponse non reconnue comme .fit'
        if verbose:
            print(f'      {short} → {len(blob)} octets, pas un .fit')
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

    # Déduplication par la donnée, pas par le fichier : une séance dont la
    # dynamique est déjà extraite n'a aucune raison d'être re-téléchargée. Ça
    # évite d'archiver les .fit dans le dépôt (plusieurs Mo par séance).
    done_dates: set[str] = set()
    cache_path = data_dir / 'sessions_cache.json'
    if cache_path.exists():
        try:
            cache = json.loads(cache_path.read_text(encoding='utf-8'))
            done_dates = {v.get('d') for v in cache.values() if v.get('dyn')}
        except Exception:  # noqa: BLE001
            pass
    already = {p.name for p in list(inbox.glob('*.fit'))
               + list(processed.glob('*.fit'))} if inbox.exists() else set()

    days = int(os.environ.get('INTERVALS_LOOKBACK', '7'))
    # Re-télécharge même les séances déjà enrichies. Utile quand on change de
    # variante de fichier (original vs ré-encodage) : sans ça, la déduplication
    # gèlerait définitivement la première version récupérée.
    force = os.environ.get('INTERVALS_FORCE', '').strip() in ('1', 'true', 'yes')
    print(f'▸ intervals.icu · athlète {athlete} · fenêtre {days} j'
          + (' · FORCE' if force else ''))
    probe_athlete(key, athlete)
    try:
        acts = list_activities(key, athlete, days)
    except Exception as e:  # noqa: BLE001
        print(f'✗ Liste des activités impossible : {e}')
        return 0  # jamais bloquant : le reste du build doit passer

    print(f'▸ {len(acts)} course(s) retenue(s)')
    if not acts:
        print('  → si intervals.icu affiche pourtant tes séances sur son site, '
              'dis-le-moi : le problème est ici. Sinon, la reprise '
              "d'historique depuis Garmin est encore en cours côté Garmin.")
    got = 0
    for a in acts:
        aid = str(a.get('id') or '')
        name = f'{aid}.fit'
        if not aid or name in already:
            continue
        # Date locale au format du cache (JJ/MM/AAAA)
        iso = str(a.get('start_date_local') or '')[:10]
        if len(iso) == 10 and not force:
            jour = f'{iso[8:10]}/{iso[5:7]}/{iso[0:4]}'
            if jour in done_dates:
                continue
        print(f"  ↓ {a.get('start_date_local', '')[:10]} · "
              f"{str(a.get('name', ''))[:40]}")
        blob = download_fit(key, athlete, aid, verbose=(got == 0))
        if blob:
            (inbox / name).write_bytes(blob)
            got += 1

    print(f'✓ {got} fichier(s) .fit déposé(s) dans fit_inbox/')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
