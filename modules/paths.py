"""
seb-metrics — modules/paths.py
========================================
Résolution centralisée du dossier de données.

Priorité :
  1. Variable d'environnement SEB_DATA_DIR (utilisée par le CI GitHub Actions,
     qui pointe sur ./data à la racine du repo)
  2. ~/Documents/SebMetrics/data (installation Mac classique)
"""
from __future__ import annotations
import os
from pathlib import Path


def data_dir() -> Path:
    env = os.environ.get('SEB_DATA_DIR')
    if env:
        return Path(env).expanduser().resolve()
    return Path.home() / 'Documents' / 'SebMetrics' / 'data'
