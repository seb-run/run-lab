"""
seb-metrics — modules/cache.py
========================================
Cache de parsing FIT : évite de reparser des fichiers déjà traités.

Stratégie :
  - Hash MD5 du fichier .fit comme clé
  - Stockage JSON : { md5 : session_dict }
  - Si le hash existe → on réutilise la session parsée
  - Si --rebuild → on ignore le cache et on reparse tout
"""

from __future__ import annotations
import os
import json
import hashlib
from typing import Optional


def file_md5(path: str, chunk_size: int = 65536) -> str:
    """Calcule le MD5 d'un fichier en streaming (peu de RAM)."""
    h = hashlib.md5()
    with open(path, 'rb') as f:
        while chunk := f.read(chunk_size):
            h.update(chunk)
    return h.hexdigest()


class ParseCache:
    """
    Cache simple { md5 : session_dict }.
    Persisté en JSON dans `cache_path`.
    """

    def __init__(self, cache_path: str):
        self.cache_path = cache_path
        self._data: dict[str, dict] = {}
        self._dirty = False
        self._load()

    def _load(self) -> None:
        if os.path.exists(self.cache_path):
            try:
                with open(self.cache_path, 'r', encoding='utf-8') as f:
                    self._data = json.load(f)
            except (json.JSONDecodeError, OSError):
                self._data = {}

    def save(self) -> None:
        if not self._dirty:
            return
        os.makedirs(os.path.dirname(self.cache_path) or '.', exist_ok=True)
        with open(self.cache_path, 'w', encoding='utf-8') as f:
            json.dump(self._data, f, ensure_ascii=False, default=str)
        self._dirty = False

    def get(self, md5: str) -> Optional[dict]:
        return self._data.get(md5)

    def set(self, md5: str, session: dict) -> None:
        self._data[md5] = session
        self._dirty = True

    def __len__(self) -> int:
        return len(self._data)

    def all_sessions(self) -> list[dict]:
        """Retourne toutes les sessions cachées (utile pour un rebuild HTML sans reparser)."""
        return list(self._data.values())


def parse_with_cache(fit_path: str, cache: ParseCache, parser_fn, force: bool = False) -> Optional[dict]:
    """
    Parse un fichier .fit via le cache. Réutilise si le MD5 est déjà connu.

    Args:
      fit_path  : chemin du fichier .fit
      cache     : instance ParseCache
      parser_fn : fonction(path) → dict | None (typiquement parser_fit.parse_fit_file)
      force     : si True, ignore le cache et reparse
    """
    md5 = file_md5(fit_path)
    if not force:
        cached = cache.get(md5)
        if cached:
            return cached

    session = parser_fn(fit_path)
    if session is not None:
        # On ajoute le md5 dans la session elle-même pour debug
        session['_md5'] = md5
        cache.set(md5, session)
    return session
