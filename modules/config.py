"""
seb-metrics — modules/config.py
========================================
Gestion de la configuration persistante du dashboard.

Fichier de config : ~/Documents/SebMetrics/data/config.json

Structure :
{
  "start_date": "2021-01-01",
  "profile": {
    "name": "Sébastien",
    "birthdate": "1992-05-22",
    "role": "Chef de Projets FFF",
    "hr_zones": {"z1_max": 135, "z2_max": 150, "z3_max": 166, "z4_max": 175},
    "goal_name": "Marathon de Cologne",
    "goal_date": "2026-10-04",
    "goal_time": "2h43'00\""
  }
}

Comportement :
  - Les arguments CLI passés à build.py SURCHARGENT la config (one-shot)
  - Avec --save-config, les args CLI courants sont écrits dans la config (permanent)
  - Si aucune config n'existe, on retourne un dict vide
"""

from __future__ import annotations
import json
import os
from pathlib import Path
from typing import Optional


try:
    from modules.paths import data_dir as _data_dir
    CONFIG_PATH = _data_dir() / 'config.json'
except Exception:
    CONFIG_PATH = Path.home() / 'Documents' / 'SebMetrics' / 'data' / 'config.json'


def load_config() -> dict:
    """Charge la config depuis le disque. Retourne dict vide si absente ou invalide."""
    if not CONFIG_PATH.exists():
        return {}
    try:
        with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
            data = json.load(f)
            return data if isinstance(data, dict) else {}
    except (json.JSONDecodeError, OSError):
        return {}


def save_config(config: dict) -> None:
    """Persiste la config sur disque (création du dossier si nécessaire)."""
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_PATH, 'w', encoding='utf-8') as f:
        json.dump(config, f, ensure_ascii=False, indent=2)


def merge_config_with_args(config: dict, args) -> dict:
    """
    Fusionne la config et les args CLI.

    Les args CLI ont la priorité quand ils sont fournis (non None).
    Retourne un dict avec : start_date, name, birthdate, z1_max, z2_max,
    z3_max, z4_max, goal, goal_date, goal_time.
    """
    profile_cfg = config.get('profile', {}) if isinstance(config.get('profile'), dict) else {}
    zones_cfg = profile_cfg.get('hr_zones', {}) if isinstance(profile_cfg.get('hr_zones'), dict) else {}

    return {
        'start_date': args.start_date or config.get('start_date'),
        'name':       args.name      or profile_cfg.get('name'),
        'birthdate':  args.birthdate or profile_cfg.get('birthdate'),
        'z1_max':     args.z1_max    if args.z1_max is not None else zones_cfg.get('z1_max'),
        'z2_max':     args.z2_max    if args.z2_max is not None else zones_cfg.get('z2_max'),
        'z3_max':     args.z3_max    if args.z3_max is not None else zones_cfg.get('z3_max'),
        'z4_max':     args.z4_max    if args.z4_max is not None else zones_cfg.get('z4_max'),
        'goal':       args.goal      or profile_cfg.get('goal_name'),
        'goal_date':  args.goal_date or profile_cfg.get('goal_date'),
        'goal_time':  args.goal_time or profile_cfg.get('goal_time'),
    }


def update_config_from_args(args) -> dict:
    """
    Charge la config existante, applique les overrides des args, et sauvegarde.
    Retourne la nouvelle config.
    """
    cfg = load_config()
    if not isinstance(cfg.get('profile'), dict):
        cfg['profile'] = {}
    if not isinstance(cfg['profile'].get('hr_zones'), dict):
        cfg['profile']['hr_zones'] = {}

    if args.start_date:    cfg['start_date'] = args.start_date
    if args.name:          cfg['profile']['name'] = args.name
    if args.birthdate:     cfg['profile']['birthdate'] = args.birthdate
    if args.goal:          cfg['profile']['goal_name'] = args.goal
    if args.goal_date:     cfg['profile']['goal_date'] = args.goal_date
    if args.goal_time:     cfg['profile']['goal_time'] = args.goal_time
    if args.z1_max is not None: cfg['profile']['hr_zones']['z1_max'] = args.z1_max
    if args.z2_max is not None: cfg['profile']['hr_zones']['z2_max'] = args.z2_max
    if args.z3_max is not None: cfg['profile']['hr_zones']['z3_max'] = args.z3_max
    if args.z4_max is not None: cfg['profile']['hr_zones']['z4_max'] = args.z4_max

    save_config(cfg)
    return cfg
