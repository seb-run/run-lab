#!/usr/bin/env python3
"""
seb-metrics — scripts/repair_stop_laps.py
=========================================
Correctif rétroactif du bug « montre non coupée ».

Symptôme : une pause pendant la séance (feu rouge, boulangerie, arrêt gastrique)
produit un km à 9-10'/km alors que l'allure réelle était régulière. Ce lap fait
exploser le coefficient de variation, et la séance bascule en `frac_court` dans
l'historique du dashboard.

Cause : `modules/strava_sync.py` lisait `elapsed_time` (temps écoulé) au lieu de
`moving_time` (temps en mouvement) sur les laps Strava. Corrigé à la source ;
ce script répare l'existant.

Deux passes :

  1. Ré-import de l'inbox Strava (`data/strava_inbox/processed/*.json`) avec la
     logique corrigée → allures des laps ET classification refaites à l'identique
     de ce qu'aurait produit un sync propre. C'est la réparation complète.

  2. Reclassification des séances non couvertes par l'inbox, à partir des laps
     déjà en cache, en élaguant les laps d'arrêt. Répare le type de séance ; ne
     peut pas restituer l'allure réelle du km concerné (le temps en mouvement
     n'est pas stocké). Pour ces séances, un backfill API est possible :
     SYNC_FORCE=1 SYNC_LOOKBACK_DAYS=90 python3 scripts/ci/strava_api_sync.py

Usage :
    python3 scripts/repair_stop_laps.py [--dry-run] [--data DIR]
"""
from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from modules.strava_sync import (  # noqa: E402
    _classify_from_laps, import_from_inbox,
)


def blocs_to_pseudo_laps(blocs: list[dict]) -> list[dict]:
    """Reconstruit des laps au format Strava depuis les blocs du cache."""
    laps = []
    for b in blocs or []:
        km, ps = b.get('km') or 0, b.get('ps')
        if km <= 0 or not ps:
            continue
        secs = ps * km
        laps.append({
            'distance': km * 1000.0,
            'moving_time': secs,
            'elapsed_time': secs,
            'avg_hr': b.get('fc'),
            'avg_cadence': b.get('ca'),
        })
    return laps


def suspect_laps(blocs: list[dict], margin: int = 90) -> list[int]:
    """Indices (1-based) des laps anormalement lents vs la médiane de la séance."""
    usable = [(i, b) for i, b in enumerate(blocs or [], 1)
              if (b.get('km') or 0) > 0.4 and b.get('ps')]
    if len(usable) < 4:
        return []
    ordered = sorted(b['ps'] for _, b in usable)
    median = ordered[len(ordered) // 2]
    return [i for i, b in usable if b['ps'] > median + margin]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--dry-run', action='store_true')
    ap.add_argument('--data', default=str(REPO_ROOT / 'data'))
    args = ap.parse_args()

    data_dir = Path(args.data)
    cache_path = data_dir / 'sessions_cache.json'
    inbox_dir = data_dir / 'strava_inbox'
    if not cache_path.exists():
        print(f'✗ Cache introuvable : {cache_path}')
        return 1

    before = json.loads(cache_path.read_text(encoding='utf-8'))
    before_types = {k: v.get('tp') for k, v in before.items()}

    # ---- Passe 1 : ré-import de l'inbox avec la logique corrigée -------------
    processed = inbox_dir / 'processed'
    reimported = 0
    if processed.exists() and not args.dry_run:
        stats = import_from_inbox(processed, cache_path)
        reimported = stats.get('updated', 0) + stats.get('added', 0)
        print(f"▸ Passe 1 — ré-import inbox : {reimported} séance(s) reconstruite(s)")
    elif args.dry_run:
        n = len(list(processed.glob('*.json'))) if processed.exists() else 0
        print(f"▸ Passe 1 — {n} fichier(s) inbox seraient ré-importés (dry-run)")

    cache = json.loads(cache_path.read_text(encoding='utf-8'))

    # ---- Passe 2 : reclassification des séances restantes --------------------
    changed = []
    for key, sess in cache.items():
        # Uniquement les séances issues de Strava : elles seules ont été classées
        # par le classifieur simplifié buggé. Les séances issues des .fit ont été
        # classées par parser_fit, qui prend déjà min(timer, elapsed) et n'est pas
        # concerné — les repasser à la moulinette Strava dégraderait l'historique.
        if not str(sess.get('source', '')).startswith('strava_'):
            continue
        blocs = sess.get('b') or []
        if not suspect_laps(blocs):
            continue
        laps = blocs_to_pseudo_laps(blocs)
        if len(laps) < 4:
            continue
        tp, cv = _classify_from_laps(laps, sess.get('km') or 0, sess.get('ps') or 0)
        old_tp = sess.get('tp')
        if tp != old_tp:
            changed.append((sess.get('d'), sess.get('t'), old_tp, tp,
                            len(suspect_laps(blocs))))
            if not args.dry_run:
                sess['tp'] = tp
                sess['cv'] = round(cv, 2)
                sess['_repaired_stop_laps'] = True

    print(f"▸ Passe 2 — {len(changed)} séance(s) reclassée(s)")
    for d, t, old, new, n in changed[:40]:
        print(f"   {d}  {str(t)[:34]:34s} {old:14s} → {new:14s} ({n} lap(s) d'arrêt)")
    if len(changed) > 40:
        print(f"   … et {len(changed) - 40} autres")

    if not args.dry_run:
        cache_path.write_text(json.dumps(cache, ensure_ascii=False, default=str),
                              encoding='utf-8')
        total = sum(1 for k, v in cache.items() if before_types.get(k) != v.get('tp'))
        print(f"✓ Cache réécrit — {total} type(s) de séance modifié(s) au total")
    else:
        print('(dry-run : rien écrit)')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
