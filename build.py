#!/usr/bin/env python3
"""
seb-metrics — build.py
========================================
Orchestrateur principal du dashboard.

Usages :
  # Première utilisation : import historique Strava complet
  python3 build.py --strava /chemin/vers/strava

  # Workflow quotidien (déclenché par update.command sur le Bureau)
  python3 build.py --update

  # Rebuild HTML uniquement depuis le cache (sans reparser ni push)
  python3 build.py --rebuild-html

  # Force reparsing complet
  python3 build.py --update --rebuild

  # Duplication pour une autre personne
  python3 build.py --name Christophe --birthdate 15/08/1970 \\
                   --strava /chemin/strava-chris \\
                   --z1-max 116 --z2-max 144 --z3-max 158 --z4-max 173 \\
                   --goal "Marathon de Berlin" --goal-date 2026-09-20
"""

from __future__ import annotations
import argparse
import os
import sys
import shutil
from typing import Optional
from pathlib import Path
from datetime import datetime

# Permet l'import des modules locaux
sys.path.insert(0, str(Path(__file__).parent))

# Import paresseux : fitdecode n'est nécessaire que pour parser des .fit
# (jamais le cas en CI, qui ne fait que sync Strava + rebuild HTML)
try:
    from modules.parser_fit import parse_fit_file
except ImportError:
    parse_fit_file = None
from modules.cache import ParseCache, parse_with_cache, file_md5
from modules.builder import build_html, build_profile
from modules.git_push import push_dashboard
from modules.config import load_config, update_config_from_args, merge_config_with_args, CONFIG_PATH
from modules.strava_sync import import_from_inbox
from modules.plan_engine import (
    generate_plan, attach_actuals, adapt_plan, save_plan, load_plan, PLAN_PATH,
)


# ============================================================================
# CHEMINS
# ============================================================================

PROJECT_DIR  = Path(__file__).parent.resolve()
TEMPLATES_DIR = PROJECT_DIR / 'templates'
OUTPUT_DIR    = PROJECT_DIR / 'output'
OUTPUT_HTML   = OUTPUT_DIR / 'index.html'

# Dossiers utilisateur (créés par INSTALL.command)
# En CI : SEB_DATA_DIR pointe sur ./data à la racine du repo (voir modules/paths.py)
from modules.paths import data_dir as _data_dir
USER_ROOT     = Path.home() / 'Documents' / 'SebMetrics'
DROP_DIR      = USER_ROOT / 'A_Ajouter'
ARCHIVE_DIR   = USER_ROOT / 'Archives'
DATA_DIR      = _data_dir()
CACHE_FILE    = DATA_DIR / 'sessions_cache.json'
STRAVA_INBOX  = DATA_DIR / 'strava_inbox'


# ============================================================================
# IMPORT STRAVA (bulk initial)
# ============================================================================

def import_strava(strava_path: str, cache: ParseCache, force: bool = False) -> int:
    """Importe en bulk tous les .fit d'un dossier Strava export."""
    if parse_fit_file is None:
        print("✗ fitdecode requis pour parser des .fit : pip install fitdecode")
        return 0
    strava = Path(strava_path)
    if not strava.exists():
        print(f"✗ Dossier Strava introuvable : {strava}")
        return 0

    fit_files = []
    for ext in ('*.fit', '*.fit.gz'):
        fit_files.extend(strava.rglob(ext))

    if not fit_files:
        print(f"⚠ Aucun .fit trouvé dans {strava}")
        return 0

    print(f"\n▸ Import Strava : {len(fit_files)} fichiers .fit détectés")
    print(f"  Source : {strava}\n")

    count_new = 0
    count_cached = 0
    count_skipped = 0
    count_errors = 0

    for i, fp in enumerate(fit_files, 1):
        try:
            md5 = file_md5(str(fp))
            if not force and cache.get(md5):
                count_cached += 1
            else:
                session = parse_fit_file(str(fp))
                if session:
                    session['_md5'] = md5
                    cache.set(md5, session)
                    count_new += 1
                else:
                    count_skipped += 1
        except Exception as e:
            count_errors += 1
            print(f"  ✗ {fp.name} : {e}")

        if i % 50 == 0 or i == len(fit_files):
            print(f"  [{i}/{len(fit_files)}] new={count_new} cached={count_cached} skipped={count_skipped}")

    cache.save()
    print(f"\n  ✓ {count_new} nouvelles · {count_cached} en cache · {count_skipped} ignorées · {count_errors} erreurs")
    return count_new


# ============================================================================
# UPDATE INCRÉMENTAL (workflow quotidien)
# ============================================================================

def update_from_drop(cache: ParseCache) -> int:
    """Traite tous les .fit déposés dans ~/Documents/SebMetrics/A_Ajouter/."""
    if not DROP_DIR.exists():
        DROP_DIR.mkdir(parents=True, exist_ok=True)
        ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
        print(f"  ℹ Dossier drop créé : {DROP_DIR}")
        return 0

    fit_files = list(DROP_DIR.glob('*.fit')) + list(DROP_DIR.glob('*.fit.gz'))
    if not fit_files:
        print(f"  ℹ Aucun .fit à traiter dans {DROP_DIR}")
        return 0
    if parse_fit_file is None:
        print("  ✗ fitdecode requis pour parser des .fit : pip install fitdecode")
        return 0

    print(f"\n▸ Traitement de {len(fit_files)} fichier(s) déposé(s)")
    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)

    count = 0
    for fp in fit_files:
        try:
            session = parse_with_cache(str(fp), cache, parse_fit_file)
            if session:
                # Archive : rename YYYYMMDD_type.fit
                date_obj = datetime.strptime(session['d'], '%d/%m/%Y')
                archive_name = f"{date_obj.strftime('%Y%m%d')}_{session['tp']}_{fp.name}"
                archive_path = ARCHIVE_DIR / archive_name
                shutil.move(str(fp), str(archive_path))
                print(f"  ✓ {session['d']} · {session['km']} km · {session['tp']} → archivé")
                count += 1
            else:
                # Fichier invalide → reste dans A_Ajouter pour inspection
                print(f"  ⚠ {fp.name} : non parsable, laissé en place")
        except Exception as e:
            print(f"  ✗ {fp.name} : {e}")

    cache.save()
    return count


# ============================================================================
# CLI
# ============================================================================

def parse_args():
    p = argparse.ArgumentParser(
        description="seb-metrics — build du dashboard running",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument('--strava', help="Dossier d'export Strava (.fit) à importer en bulk")
    p.add_argument('--strava-sync', action='store_true', dest='strava_sync',
                   help="Importe les activités JSON déposées dans data/strava_inbox/")
    p.add_argument('--regen-plan', action='store_true', dest='regen_plan',
                   help="Force la régénération du plan d'entraînement")
    p.add_argument('--update', action='store_true',
                   help="Traite les .fit du dossier A_Ajouter (workflow quotidien)")
    p.add_argument('--rebuild', action='store_true',
                   help="Force reparsing complet (ignore le cache)")
    p.add_argument('--rebuild-html', action='store_true',
                   help="Régénère uniquement le HTML depuis le cache (pas de push)")
    p.add_argument('--no-push', action='store_true',
                   help="Désactive le push GitHub automatique")
    p.add_argument('--start-date', dest='start_date',
                   help="Ignore les séances antérieures à cette date (format YYYY-MM-DD)")
    p.add_argument('--save-config', action='store_true', dest='save_config',
                   help="Sauvegarde les paramètres CLI courants dans la config persistante")
    p.add_argument('--show-config', action='store_true', dest='show_config',
                   help="Affiche la config persistante et quitte")

    # Profil (pour duplication)
    p.add_argument('--name', help="Prénom de l'utilisateur")
    p.add_argument('--birthdate', help="Date de naissance JJ/MM/AAAA")
    p.add_argument('--z1-max', type=int, dest='z1_max', help="FC max zone 1")
    p.add_argument('--z2-max', type=int, dest='z2_max', help="FC max zone 2")
    p.add_argument('--z3-max', type=int, dest='z3_max', help="FC max zone 3")
    p.add_argument('--z4-max', type=int, dest='z4_max', help="FC max zone 4")
    p.add_argument('--goal', help="Nom de la course objectif")
    p.add_argument('--goal-date', dest='goal_date', help="Date de l'objectif YYYY-MM-DD")
    p.add_argument('--goal-time', dest='goal_time', help="Temps visé (ex: 2h43'00\")")
    return p.parse_args()


def build_profile_from_args(args, config: Optional[dict] = None) -> dict:
    """Construit un profil avec overrides CLI > config > défauts."""
    overrides = {}
    config = config or {}
    profile_cfg = config.get('profile', {}) if isinstance(config.get('profile'), dict) else {}
    zones_cfg = profile_cfg.get('hr_zones', {}) if isinstance(profile_cfg.get('hr_zones'), dict) else {}

    # 1. Valeurs depuis la config persistante
    for key in ('name', 'birthdate', 'goal_name', 'goal_date', 'goal_time', 'role', 'github_repo'):
        if key in profile_cfg:
            overrides[key] = profile_cfg[key]

    zones = {}
    for k in ('z1_max', 'z2_max', 'z3_max', 'z4_max'):
        if k in zones_cfg:
            zones[k] = zones_cfg[k]

    # 2. Surcharge par les args CLI si fournis
    if args.name:      overrides['name']      = args.name
    if args.birthdate:
        # Convertit JJ/MM/AAAA → YYYY-MM-DD
        if '/' in args.birthdate:
            parts = args.birthdate.split('/')
            overrides['birthdate'] = f"{parts[2]}-{parts[1].zfill(2)}-{parts[0].zfill(2)}"
        else:
            overrides['birthdate'] = args.birthdate
    if args.goal:      overrides['goal_name'] = args.goal
    if args.goal_date: overrides['goal_date'] = args.goal_date
    if args.goal_time: overrides['goal_time'] = args.goal_time

    if args.z1_max: zones['z1_max'] = args.z1_max
    if args.z2_max: zones['z2_max'] = args.z2_max
    if args.z3_max: zones['z3_max'] = args.z3_max
    if args.z4_max: zones['z4_max'] = args.z4_max

    if zones:
        overrides['hr_zones'] = zones

    return build_profile(overrides)


# ============================================================================
# MAIN
# ============================================================================

def main():
    args = parse_args()

    # Initialisation
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # ----- Gestion de la config persistante -----
    config = load_config()

    # --show-config : affiche et quitte
    if args.show_config:
        import json as _json
        print(f"\n  Config persistante : {CONFIG_PATH}\n")
        if config:
            print(_json.dumps(config, indent=2, ensure_ascii=False))
        else:
            print("  (vide ou inexistante)")
        return

    # --save-config : on persiste les args CLI courants
    if args.save_config:
        new_cfg = update_config_from_args(args)
        print(f"\n  ✓ Config sauvegardée : {CONFIG_PATH}")
        import json as _json
        print(_json.dumps(new_cfg, indent=2, ensure_ascii=False))
        # On continue le build après save (l'utilisateur veut probablement vérifier le rendu)

    # Application des valeurs de config si les args CLI sont absents
    if not args.start_date and config.get('start_date'):
        args.start_date = config['start_date']

    print("\n╔══════════════════════════════════════════════════╗")
    print("║         SEB METRICS — build dashboard            ║")
    print("╚══════════════════════════════════════════════════╝")

    if config:
        print(f"\n  Config : {CONFIG_PATH.name} ({len(config)} clé(s))")
    if args.start_date:
        print(f"  Filtre date actif : sessions ≥ {args.start_date}")

    cache = ParseCache(str(CACHE_FILE))
    print(f"  Cache : {len(cache)} séances connues")

    # ----- 1. Import Strava (si demandé) -----
    if args.strava:
        import_strava(args.strava, cache, force=args.rebuild)

    # ----- 1.5. Sync Strava (depuis inbox JSON) -----
    if args.strava_sync or args.update:
        try:
            stats = import_from_inbox(STRAVA_INBOX, CACHE_FILE)
            if stats.get('total', 0) > 0:
                print(f"\n▸ Sync Strava : +{stats['added']} ajoutées, {stats['updated']} màj, {stats['skipped']} skip ({stats['files']} fichier(s))")
                # Recharge le cache après modif externe
                cache = ParseCache(str(CACHE_FILE))
        except Exception as e:
            print(f"  ⚠ Sync Strava échoué : {e}")

    # ----- 2. Update incrémental depuis A_Ajouter -----
    new_count = 0
    if args.update:
        new_count = update_from_drop(cache)

    # ----- 3. Récupération de toutes les sessions -----
    sessions = cache.all_sessions()
    # Tri date desc (plus récent en premier)
    def parse_d(s):
        try:
            return datetime.strptime(s['d'] + ' ' + s.get('h', '00:00'), '%d/%m/%Y %H:%M')
        except Exception:
            return datetime.min
    sessions.sort(key=parse_d, reverse=True)

    # Filtre --start-date : on ignore tout ce qui est avant cette date (au build, pas au cache)
    if args.start_date:
        try:
            cutoff = datetime.strptime(args.start_date, '%Y-%m-%d')
            n_before = len(sessions)
            sessions = [s for s in sessions if parse_d(s) >= cutoff]
            n_filtered = n_before - len(sessions)
            if n_filtered > 0:
                print(f"\n▸ Filtre date : {n_filtered} séances antérieures à {args.start_date} ignorées")
        except ValueError:
            print(f"\n⚠ Format de --start-date invalide : '{args.start_date}'. Attendu : YYYY-MM-DD")

    if not sessions:
        print("\n⚠ Aucune séance disponible. Lance avec --strava /chemin pour importer ton historique.")
        return

    print(f"\n▸ Total : {len(sessions)} séances · {sum(s['km'] for s in sessions):.0f} km")

    # ----- 3.5. Plan d'entraînement -----
    plan = None
    goals = config.get('goals') or []
    main_goal = next((g for g in goals if g.get('type') == 'main' and g.get('status') == 'confirmed'), None)
    if main_goal and main_goal.get('date'):
        existing = load_plan()
        needs_regen = args.regen_plan or not existing
        if existing and not args.regen_plan:
            # Régénère si l'objectif a changé
            if existing.get('meta', {}).get('goal_date') != main_goal['date']:
                needs_regen = True

        if needs_regen:
            print(f"\n▸ Génération du plan pour {main_goal['name']} ({main_goal['date']})...")
            try:
                plan = generate_plan(
                    goal_name=main_goal['name'],
                    goal_date=main_goal['date'],
                    target_time=main_goal.get('target_time') or main_goal.get('strategy_time'),
                    strategy_time=main_goal.get('strategy_time'),
                    sessions=sessions,
                )
                attach_actuals(plan, sessions)
                adapt_plan(plan)
                save_plan(plan)
                print(f"  ✓ {len(plan['weeks'])} semaines · plan sauvé dans {PLAN_PATH}")
            except Exception as e:
                print(f"  ⚠ Plan non généré : {e}")
                plan = None
        else:
            plan = existing
            # Statuts + adaptation (idempotent)
            try:
                attach_actuals(plan, sessions)
                adapt_plan(plan)
                save_plan(plan)
                adapt_count = len(plan.get('adaptations', []))
                if adapt_count:
                    print(f"\n▸ Plan adapté · {adapt_count} ajustement(s) appliqué(s) :")
                    for a in plan['adaptations']:
                        print(f"    · {a['kind']}: {a.get('reason', '')}")
            except Exception as e:
                print(f"  ⚠ Adaptation plan échouée : {e}")

    # ----- 4. Construction profil + génération HTML -----
    profile = build_profile_from_args(args, config=config)
    print(f"\n▸ Génération HTML pour {profile['name']}...")
    build_html(
        sessions=sessions,
        profile=profile,
        templates_dir=str(TEMPLATES_DIR),
        output_path=str(OUTPUT_HTML),
        config=config,
        plan=plan,
    )
    size_kb = OUTPUT_HTML.stat().st_size / 1024
    print(f"  ✓ {OUTPUT_HTML} ({size_kb:.0f} Ko)")

    # ----- 5. Push GitHub (sauf --no-push ou --rebuild-html) -----
    if args.rebuild_html or args.no_push:
        print("\n  ℹ Push GitHub ignoré.")
    elif args.update or args.strava or new_count > 0:
        print(f"\n▸ Push GitHub...")
        push_dashboard(str(PROJECT_DIR), file_path=str(OUTPUT_HTML.relative_to(PROJECT_DIR)))

    print("\n✓ Terminé.\n")


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n⚠ Interrompu par l'utilisateur.")
        sys.exit(130)
