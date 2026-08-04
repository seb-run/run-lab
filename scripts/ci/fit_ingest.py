#!/usr/bin/env python3
"""
seb-metrics — scripts/ci/fit_ingest.py
======================================
Intègre les fichiers .fit déposés dans `data/fit_inbox/` au cache des séances.

Pourquoi ce script existe : l'API Strava ne transmet ni la dynamique de course
(temps de contact au sol, longueur de foulée, oscillation, équilibre G/D), ni la
charge Garmin, ni le ressenti saisi sur la montre, ni les intervalles R-R. Tout
cela vit dans le .fit d'origine.

Principe : le .fit ENRICHIT la séance déjà synchronisée depuis Strava plutôt que
d'en créer une seconde. L'appariement se fait sur date + distance + durée. Si
aucune séance ne correspond (cas d'une séance jamais passée par Strava), le .fit
crée l'entrée.

Le transport en amont (ce qui remplit fit_inbox/) est volontairement découplé :
voir scripts/ci/intervals_sync.py. Changer de source ne touche pas ce script.

Usage :
    python3 scripts/ci/fit_ingest.py [--data DIR] [--dry-run]
"""
from __future__ import annotations
import argparse
import json
import shutil
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from modules.cache import file_md5              # noqa: E402
from modules.parser_fit import parse_fit_file   # noqa: E402

# Tolérances d'appariement .fit ↔ séance déjà en cache
MATCH_KM = 0.3
MATCH_SEC = 120

# Champs que le .fit apporte et que Strava n'a pas : on les recopie toujours.
FIT_ONLY_FIELDS = ('dyn',)


def find_twin(cache: dict, sess: dict) -> str | None:
    """Clé de la séance déjà en cache correspondant à ce .fit, si elle existe."""
    for key, v in cache.items():
        if v.get('d') != sess.get('d'):
            continue
        if abs((v.get('km') or 0) - (sess.get('km') or 0)) > MATCH_KM:
            continue
        if abs((v.get('dur_s') or 0) - (sess.get('dur_s') or 0)) > MATCH_SEC:
            continue
        return key
    return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--data', default=str(REPO_ROOT / 'data'))
    ap.add_argument('--dry-run', action='store_true')
    args = ap.parse_args()

    data_dir = Path(args.data)
    inbox = data_dir / 'fit_inbox'
    processed = inbox / 'processed'
    cache_path = data_dir / 'sessions_cache.json'

    if not inbox.exists():
        print('▸ Pas de dossier fit_inbox — rien à faire.')
        return 0

    files = sorted(f for f in inbox.iterdir()
                   if f.is_file() and f.name.lower().endswith(('.fit', '.fit.gz')))
    if not files:
        print('▸ fit_inbox vide — rien à faire.')
        return 0

    cache = {}
    if cache_path.exists():
        cache = json.loads(cache_path.read_text(encoding='utf-8'))

    enriched = created = skipped = 0
    for fp in files:
        try:
            sess = parse_fit_file(str(fp))
        except Exception as e:
            print(f'  ✗ {fp.name} : {e}')
            skipped += 1
            continue
        if not sess:
            print(f'  – {fp.name} : ignoré (pas une séance de course exploitable)')
            skipped += 1
            continue

        sess['_md5'] = file_md5(str(fp))
        twin_key = find_twin(cache, sess)

        if twin_key:
            twin = cache[twin_key]
            for field in FIT_ONLY_FIELDS:
                if sess.get(field):
                    twin[field] = sess[field]
            # Le .fit est la source la plus fiable pour les blocs (temps moteur
            # réel, pas de temps écoulé) — on les reprend s'ils sont plus fins.
            if len(sess.get('b') or []) >= len(twin.get('b') or []):
                twin['b'] = sess['b']
                twin['tp'] = sess['tp']
                twin['cv'] = sess['cv']
            twin['_fit'] = fp.name
            enriched += 1
            dyn = sess.get('dyn') or {}
            print(f"  ⊕ {sess['d']} {sess['km']}km — enrichie "
                  f"({len(dyn)} indicateurs, flags: {dyn.get('flags') or 'aucun'})")
        else:
            cache[sess['_md5']] = sess
            created += 1
            print(f"  + {sess['d']} {sess['km']}km — nouvelle séance depuis .fit")

        if not args.dry_run:
            processed.mkdir(parents=True, exist_ok=True)
            shutil.move(str(fp), str(processed / fp.name))

    if not args.dry_run:
        cache_path.write_text(json.dumps(cache, ensure_ascii=False, default=str),
                              encoding='utf-8')
    print(f"✓ {enriched} séance(s) enrichie(s), {created} créée(s), {skipped} ignorée(s)"
          + (' [dry-run]' if args.dry_run else ''))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
