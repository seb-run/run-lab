#!/usr/bin/env python3
"""
seb-metrics — scripts/verif_secrets.py
========================================
Refuse de laisser partir un secret dans un dépôt public.

`SETUP_AUTONOME.md` invite à remplacer les placeholders par ses propres
identifiants Strava pour lancer les commandes. Une fois remplis, ces
identifiants sont dans un fichier suivi par git : le commit suivant les
publierait, et ils resteraient lisibles dans l'historique même après
correction — seule leur révocation les neutraliserait vraiment.

Ce contrôle lit ce qui est sur le point d'être commité (`git diff --cached`)
et s'arrête au premier motif suspect.

    python3 scripts/verif_secrets.py          # contrôle l'index
    python3 scripts/verif_secrets.py --tout   # contrôle les fichiers suivis

Sortie 0 si tout va bien, 1 s'il faut regarder.
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys

# Chaque motif décrit une forme de secret et porte son nom, pour que le
# message dise quoi révoquer et pas seulement « quelque chose ».
MOTIFS: list[tuple[str, re.Pattern[str]]] = [
    ("secret client Strava", re.compile(r'client_secret\s*=\s*[A-Za-z0-9]{16,}')),
    ("jeton Strava",         re.compile(r'refresh_token\s*=\s*[A-Za-z0-9]{16,}')),
    ("clé API Anthropic",    re.compile(r'sk-ant-[A-Za-z0-9_\-]{16,}')),
    ("jeton GitHub",         re.compile(r'gh[pousr]_[A-Za-z0-9]{20,}')),
    ("jeton GitHub",         re.compile(r'github_pat_[A-Za-z0-9_]{20,}')),
    ("clé API intervals.icu",
     re.compile(r'INTERVALS_API_KEY\s*[:=]\s*["\']?[A-Za-z0-9]{16,}')),
    ("code OAuth",           re.compile(r'\bcode\s*=\s*[a-f0-9]{32,}')),
]

# Ce qui ressemble à un secret sans en être un : placeholders, références aux
# secrets du CI, valeurs masquées.
INNOCENTS = re.compile(
    r'TON_|VOTRE_|YOUR_|XXX|\.\.\.|<[^>]+>|\$\{\{|\bsecrets\.|'
    r'os\.environ|getenv|EXEMPLE|EXAMPLE|placeholder|\*{4,}',
    re.IGNORECASE)


def lignes_a_verifier(tout: bool) -> list[tuple[str, str]]:
    """Retourne les (fichier, ligne) à contrôler."""
    if tout:
        fichiers = subprocess.run(['git', 'ls-files'], capture_output=True,
                                  text=True).stdout.split()
        out = []
        for f in fichiers:
            try:
                with open(f, encoding='utf-8', errors='ignore') as fh:
                    out += [(f, l) for l in fh]
            except OSError:
                pass
        return out

    diff = subprocess.run(['git', 'diff', '--cached', '-U0'],
                          capture_output=True, text=True).stdout
    fichier = '?'
    out = []
    for ligne in diff.splitlines():
        if ligne.startswith('+++ b/'):
            fichier = ligne[6:]
        elif ligne.startswith('+') and not ligne.startswith('+++'):
            out.append((fichier, ligne[1:]))
    return out


def chercher(lignes: list[tuple[str, str]]) -> list[tuple[str, str, str]]:
    trouves = []
    for fichier, ligne in lignes:
        if INNOCENTS.search(ligne):
            continue
        for nom, motif in MOTIFS:
            m = motif.search(ligne)
            if m:
                extrait = m.group(0)
                if len(extrait) > 28:
                    extrait = extrait[:22] + '…' + extrait[-4:]
                trouves.append((fichier, nom, extrait))
                break
    return trouves


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--tout', action='store_true',
                    help="contrôle tous les fichiers suivis, pas seulement l'index")
    args = ap.parse_args()

    trouves = chercher(lignes_a_verifier(args.tout))
    if not trouves:
        return 0

    print("✗ ARRÊT : ce qui suit ressemble à un secret.")
    print()
    for fichier, nom, extrait in trouves:
        print(f"    {fichier} — {nom} : {extrait}")
    print()
    print("  Le dépôt est public. Un secret poussé reste dans l'historique")
    print("  même après correction : il faut alors le révoquer.")
    print()
    print("  Remets des valeurs neutres (TON_CLIENT_SECRET…) puis relance.")
    return 1


if __name__ == '__main__':
    raise SystemExit(main())
