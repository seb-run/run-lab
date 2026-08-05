#!/usr/bin/env python3
"""
seb-metrics — scripts/dedupe_cache.py
========================================
Fusionne dans l'historique les séances présentes deux fois : une par la voie
.fit (intervals.icu), une par la voie Strava.

Le build applique désormais cette fusion à chaque passage. Ce script sert à
rattraper l'existant, et à inspecter ce qui serait fusionné avant de le faire.

Par défaut il ne touche à rien et se contente d'afficher le rapport. Il faut
`--write` pour écrire, et une sauvegarde horodatée est alors déposée à côté
du cache.

    python3 scripts/dedupe_cache.py                 # simulation
    python3 scripts/dedupe_cache.py --write         # applique
    SEB_DATA_DIR=./data python3 scripts/dedupe_cache.py --write
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from modules.dedup import dedupe, format_report   # noqa: E402
from modules.paths import data_dir                # noqa: E402

ROOT = Path(__file__).resolve().parent.parent


def find_cache() -> Path | None:
    """Localise le cache de séances.

    `data_dir()` vise l'installation Mac (~/Documents/SebMetrics/data), qui
    n'existe pas quand on travaille depuis le dépôt. On regarde donc aussi le
    `data/` du dépôt, et on retient le premier chemin qui existe vraiment.
    """
    candidats = [
        data_dir() / 'sessions_cache.json',
        ROOT / 'data' / 'sessions_cache.json',
    ]
    for c in candidats:
        if c.exists():
            return c
    return None


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--write', action='store_true',
                    help="applique la fusion (sinon simulation)")
    ap.add_argument('--cache', help="chemin du cache (défaut : data/sessions_cache.json)")
    args = ap.parse_args()

    path = Path(args.cache) if args.cache else find_cache()
    if path is None or not path.exists():
        print("✗ Cache introuvable. Cherché dans :")
        print(f"    {data_dir() / 'sessions_cache.json'}")
        print(f"    {ROOT / 'data' / 'sessions_cache.json'}")
        print("  Précise le chemin avec --cache, ou pose SEB_DATA_DIR.")
        return 1

    cache = json.loads(path.read_text(encoding='utf-8'))
    merged, report = dedupe(cache)

    print(f"\n▸ Doublons .fit / Strava — {path}")
    print(format_report(report))

    if not report['fusionnees']:
        print("\n✓ Rien à fusionner.")
        return 0

    if not args.write:
        print("\n  Simulation : rien n'a été écrit. Relance avec --write pour appliquer.")
        return 0

    stamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup = path.with_name(f"{path.stem}.avant_dedup_{stamp}.json")
    shutil.copy2(path, backup)

    path.write_text(json.dumps(merged, ensure_ascii=False, default=str),
                    encoding='utf-8')

    print(f"\n✓ Écrit : {path}")
    print(f"  Sauvegarde : {backup.name}")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
