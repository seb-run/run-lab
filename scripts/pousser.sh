#!/usr/bin/env bash
#
# seb-metrics — scripts/pousser.sh
# ========================================
# Publie les modifications du dashboard : commit, rebase sur le distant, push.
#
# Existe parce que les commandes collées à la main ont échoué trois fois de
# suite — un commentaire en fin de ligne pris pour un argument, des fichiers
# modifiés en cours de route, le HTML généré qui bloquait le rebase. Une seule
# commande à lancer, plus de piège :
#
#     bash scripts/pousser.sh
#     bash scripts/pousser.sh "mon message de commit"
#
set -u

cd "$(dirname "$0")/.." || exit 1

MESSAGE="${1:-fix: interface quatre onglets, fuseau des .fit, debordements mobiles}"

echo
echo "▸ Dépôt : $(pwd)"
echo

# ---------------------------------------------------------------- 1. ménage
# Le HTML est régénéré par le CI à chaque build : le commiter n'apporte rien
# et ses 3 Mo bloquent le rebase pour rien.
if ! git diff --quiet -- output/index.html 2>/dev/null; then
  git checkout -- output/index.html
  echo "  output/index.html écarté (régénéré à chaque build)"
fi

# ------------------------------------------------------------- 2. inventaire
echo
echo "▸ Ce qui va être publié"

# `git add` refuse la totalité de la liste si un seul chemin n'existe pas :
# on ne lui passe donc que ce qui est réellement présent.
CHEMINS=()
for c in modules scripts templates build.py sw.js manifest.webmanifest \
         .gitignore ETAT_PROJET.md SETUP_AUTONOME.md README.md; do
  [ -e "$c" ] && CHEMINS+=("$c")
done
[ ${#CHEMINS[@]} -gt 0 ] && git add -- "${CHEMINS[@]}"

if git diff --cached --quiet; then
  echo "  (rien de nouveau à committer)"
else
  git diff --cached --name-status | sed 's/^/  /'
fi

# ------------------------------------------------- 2bis. garde-fou à secrets
# Le dépôt est public et SETUP_AUTONOME.md invite à coller ses propres
# identifiants Strava pour lancer les commandes. Remplis puis publiés, ils
# seraient lisibles par tout le monde — et resteraient dans l'historique même
# après correction. On refuse de committer ce qui ressemble à un secret.
echo
if ! python3 scripts/verif_secrets.py; then
  echo "  Rien n'a été commité. Pour voir le détail :  git diff --cached"
  git reset -q
  exit 1
fi

# ----------------------------------------------------------------- 3. commit
if ! git diff --cached --quiet; then
  echo
  if git commit -q -m "$MESSAGE"; then
    echo "▸ Commit créé : $(git log -1 --format='%h %s')"
  else
    echo "✗ Le commit a échoué."
    exit 1
  fi
fi

# ------------------------------------------------- 4. reste-t-il des traînards ?
# Un fichier suivi encore modifié ferait échouer le rebase.
if ! git diff --quiet; then
  echo
  echo "✗ Des fichiers suivis restent modifiés, le rebase ne passera pas :"
  git diff --name-only | sed 's/^/    /'
  echo
  echo "  Soit tu les ajoutes au commit, soit tu les annules :"
  echo "    git checkout -- <fichier>"
  exit 1
fi

# ----------------------------------------------------------------- 5. rebase
echo
echo "▸ Récupération du distant"
if ! git pull --rebase; then
  echo
  echo "✗ Le rebase s'est arrêté — probablement un conflit."
  echo "  Regarde les fichiers marqués, puis :"
  echo "    git add <fichier resolu>"
  echo "    git rebase --continue"
  echo "  Ou pour tout annuler :  git rebase --abort"
  exit 1
fi

# ------------------------------------------------------------------- 6. push
echo
echo "▸ Envoi"
if ! git push; then
  echo
  echo "✗ Le push a été refusé. Relance simplement ce script :"
  echo "    bash scripts/pousser.sh"
  exit 1
fi

echo
echo "✓ Publié. Le workflow se déclenche sur templates/ et modules/ :"
echo "  reconstruction puis déploiement, compte deux à trois minutes."
echo "  Suivi : https://github.com/seb-run/run-lab/actions"
echo
