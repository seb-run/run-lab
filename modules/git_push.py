"""
seb-metrics — modules/git_push.py
========================================
Auto-commit + push GitHub depuis Python.

Suppose que :
  - le projet est initialisé en git
  - un remote `origin` est configuré
  - l'authentification est gérée (SSH key ou credential helper macOS)

Workflow :
  1. Copie output/index.html vers ./index.html (racine) pour GitHub Pages
  2. Stage les deux fichiers
  3. Commit + push

Si l'auth manque, on affiche un message explicite et on n'échoue pas brutalement.
"""

from __future__ import annotations
import subprocess
import shutil
import os
from datetime import datetime


def _run(cmd: list[str], cwd: str) -> tuple[int, str, str]:
    """Exécute une commande shell, retourne (code, stdout, stderr)."""
    p = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    return p.returncode, p.stdout.strip(), p.stderr.strip()


def push_dashboard(project_dir: str, file_path: str = "output/index.html") -> bool:
    """
    Commit + push du dashboard sur GitHub.

    Args:
      project_dir : racine du repo git
      file_path   : chemin relatif du fichier généré (output/index.html par défaut)

    Returns:
      True si push OK, False sinon (avec message d'erreur affiché).
    """
    # Vérif que c'est un repo git
    if not os.path.isdir(os.path.join(project_dir, '.git')):
        print("  ⚠ Pas de repo git initialisé — push ignoré.")
        return False

    # Vérif remote
    rc, remote, _ = _run(['git', 'remote', 'get-url', 'origin'], project_dir)
    if rc != 0 or not remote:
        print("  ⚠ Aucun remote 'origin' configuré — push ignoré.")
        print("    Configure avec : git remote add origin <url>")
        return False

    # 1. Copie output/index.html vers ./index.html (racine) pour GitHub Pages
    src = os.path.join(project_dir, file_path)
    dst = os.path.join(project_dir, 'index.html')
    if os.path.exists(src):
        shutil.copyfile(src, dst)
        print(f"  ✓ Copie de {file_path} → index.html (racine)")
    else:
        print(f"  ⚠ Fichier source introuvable : {src}")
        return False

    # 2. Stage des deux fichiers
    _run(['git', 'add', file_path, 'index.html'], project_dir)

    # 3. Vérif qu'il y a bien des changements stagés
    rc, _, _ = _run(['git', 'diff', '--cached', '--quiet'], project_dir)
    if rc == 0:
        print("  ℹ Pas de changement à committer.")
        return True

    # 4. Commit
    msg = f"update dashboard {datetime.now().strftime('%Y-%m-%d %H:%M')}"
    rc, _, err = _run(['git', 'commit', '-m', msg], project_dir)
    if rc != 0:
        print(f"  ✗ Échec du commit : {err}")
        return False
    print(f"  ✓ Commit : {msg}")

    # 5. Push
    # Détection branche courante
    rc, branch, _ = _run(['git', 'rev-parse', '--abbrev-ref', 'HEAD'], project_dir)
    if not branch:
        branch = 'main'

    rc, out, err = _run(['git', 'push', 'origin', branch], project_dir)
    if rc != 0:
        print(f"  ✗ Échec du push : {err}")
        print(f"    Remote : {remote}")
        print(f"    Vérifie ton authentification SSH ou ton credential helper.")
        return False

    print(f"  ✓ Push OK → {remote} ({branch})")
    return True
