#!/bin/bash
# =============================================================================
# SEB METRICS — INSTALL.command (macOS)
# Double-clique ce fichier pour installer le dashboard.
# =============================================================================

# Toujours s'exécuter depuis le dossier du projet
cd "$(dirname "$0")" || exit 1
PROJECT_DIR="$(pwd)"

# Couleurs terminal
GREEN='\033[0;32m'; BLUE='\033[0;34m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; NC='\033[0m'; BOLD='\033[1m'

clear
echo ""
echo -e "${BLUE}${BOLD}╔══════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}${BOLD}║         SEB METRICS — Installation               ║${NC}"
echo -e "${BLUE}${BOLD}╚══════════════════════════════════════════════════╝${NC}"
echo ""

# ----------------------------------------------------------------------
# 1. Vérif Python 3
# ----------------------------------------------------------------------
echo -e "${BLUE}▸ Vérification de Python 3...${NC}"
if ! command -v python3 &> /dev/null; then
    echo -e "${RED}✗ Python 3 introuvable.${NC}"
    echo "  Installe Python 3 depuis https://www.python.org/downloads/"
    echo "  ou via Homebrew : brew install python3"
    read -p "Appuie sur Entrée pour quitter..."
    exit 1
fi
PY_VERSION=$(python3 --version 2>&1 | cut -d' ' -f2)
echo -e "${GREEN}✓ Python ${PY_VERSION} détecté${NC}"

# ----------------------------------------------------------------------
# 2. Création du virtualenv
# ----------------------------------------------------------------------
echo ""
echo -e "${BLUE}▸ Création de l'environnement virtuel (.venv)...${NC}"
if [ -d ".venv" ]; then
    echo -e "${YELLOW}  .venv existe déjà — on conserve.${NC}"
else
    python3 -m venv .venv
    if [ $? -ne 0 ]; then
        echo -e "${RED}✗ Échec création venv${NC}"
        read -p "Appuie sur Entrée pour quitter..."
        exit 1
    fi
    echo -e "${GREEN}✓ venv créé${NC}"
fi

# ----------------------------------------------------------------------
# 3. Installation des dépendances
# ----------------------------------------------------------------------
echo ""
echo -e "${BLUE}▸ Installation des dépendances Python...${NC}"
source .venv/bin/activate
pip install --quiet --upgrade pip
pip install --quiet fitdecode jinja2
if [ $? -ne 0 ]; then
    echo -e "${RED}✗ Échec installation dépendances${NC}"
    read -p "Appuie sur Entrée pour quitter..."
    exit 1
fi
echo -e "${GREEN}✓ fitdecode + jinja2 installés${NC}"

# ----------------------------------------------------------------------
# 4. Création de la structure de dossiers utilisateur
# ----------------------------------------------------------------------
echo ""
echo -e "${BLUE}▸ Création de la structure utilisateur...${NC}"
USER_ROOT="$HOME/Documents/SebMetrics"
mkdir -p "$USER_ROOT/A_Ajouter"
mkdir -p "$USER_ROOT/Archives"
mkdir -p "$USER_ROOT/data"
echo -e "${GREEN}✓ ${USER_ROOT}/${NC}"
echo -e "${GREEN}  ├── A_Ajouter/   (drop tes .fit ici)${NC}"
echo -e "${GREEN}  ├── Archives/    (.fit déjà traités)${NC}"
echo -e "${GREEN}  └── data/        (cache parsing + sensations)${NC}"

# Sauvegarde du chemin projet pour update.command
echo "$PROJECT_DIR" > "$USER_ROOT/data/.project_path"

# ----------------------------------------------------------------------
# 5. Configuration GitHub (optionnelle)
# ----------------------------------------------------------------------
echo ""
echo -e "${BLUE}▸ Configuration GitHub...${NC}"
if [ -d ".git" ]; then
    REMOTE=$(git remote get-url origin 2>/dev/null)
    if [ -n "$REMOTE" ]; then
        echo -e "${GREEN}✓ Remote git détecté : ${REMOTE}${NC}"
    else
        echo -e "${YELLOW}  Pas de remote configuré.${NC}"
        echo -n "  URL du repo GitHub (vide pour passer) : "
        read GH_URL
        if [ -n "$GH_URL" ]; then
            git remote add origin "$GH_URL"
            echo -e "${GREEN}✓ Remote ajouté${NC}"
        fi
    fi
else
    echo -e "${YELLOW}  Pas de repo git initialisé. Init...${NC}"
    git init -q
    git branch -M main 2>/dev/null
    echo -n "  URL du repo GitHub (vide pour passer) : "
    read GH_URL
    if [ -n "$GH_URL" ]; then
        git remote add origin "$GH_URL"
        echo -e "${GREEN}✓ Repo initialisé + remote ajouté${NC}"
    else
        echo -e "${YELLOW}  Tu pourras configurer le push GitHub plus tard.${NC}"
    fi
fi

# ----------------------------------------------------------------------
# 6. Création de update.command sur le Bureau
# ----------------------------------------------------------------------
echo ""
echo -e "${BLUE}▸ Création de update.command sur le Bureau...${NC}"
DESKTOP_CMD="$HOME/Desktop/update_sebmetrics.command"

cat > "$DESKTOP_CMD" << 'UPDATE_EOF'
#!/bin/bash
# SEB METRICS — Update (généré par INSTALL.command)
PROJECT_PATH=$(cat "$HOME/Documents/SebMetrics/data/.project_path" 2>/dev/null)
if [ -z "$PROJECT_PATH" ] || [ ! -d "$PROJECT_PATH" ]; then
    echo "✗ Chemin projet introuvable. Relance INSTALL.command depuis le dossier du projet."
    read -p "Entrée pour quitter..."
    exit 1
fi
cd "$PROJECT_PATH" || exit 1
source .venv/bin/activate
python3 build.py --update
read -p "Appuie sur Entrée pour fermer..."
UPDATE_EOF

chmod +x "$DESKTOP_CMD"
echo -e "${GREEN}✓ update_sebmetrics.command créé sur le Bureau${NC}"

# ----------------------------------------------------------------------
# Fin
# ----------------------------------------------------------------------
echo ""
echo -e "${GREEN}${BOLD}╔══════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}${BOLD}║              ✓  INSTALLATION OK                  ║${NC}"
echo -e "${GREEN}${BOLD}╚══════════════════════════════════════════════════╝${NC}"
echo ""
echo -e "${BOLD}Workflow quotidien :${NC}"
echo -e "  1. Drop tes ${BLUE}.fit${NC} dans ${BLUE}~/Documents/SebMetrics/A_Ajouter/${NC}"
echo -e "  2. Double-clique ${BLUE}update_sebmetrics.command${NC} sur ton Bureau"
echo -e "  3. Le dashboard se régénère + push GitHub auto"
echo ""
echo -e "${YELLOW}Première utilisation ?${NC}"
echo -e "  Pour importer ton historique Strava complet, lance :"
echo -e "  ${BLUE}cd \"$PROJECT_DIR\" && source .venv/bin/activate && python3 build.py --strava /chemin/vers/strava${NC}"
echo ""
read -p "Appuie sur Entrée pour fermer..."
