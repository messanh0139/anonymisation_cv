#!/bin/bash
# ─────────────────────────────────────────────────────────────────
#  lancer.sh — Pipeline anonymisation CVs
#
#  Usage : ./lancer.sh [commande]
#
#  Commandes :
#    start       → Démarrer le serveur FastAPI
#    stop        → Arrêter le serveur
#    process     → Extraire + anonymiser les CVs Drive
#    generate    → Générer les PDFs LaTeX
#    all         → process + generate  (défaut si serveur déjà actif)
#    reset       → Supprimer les PDFs Drive puis régénérer
#    run         → Démarrer le serveur + pipeline complet
#    status      → Vérifier l'état du serveur
#
#  Sans argument → "run" (démarrage + pipeline complet)
# ─────────────────────────────────────────────────────────────────

set -e
cd "$(dirname "$0")"

API="http://localhost:8000"
PYTHON=".venv/bin/python3"
LOG="/tmp/uvicorn_anonymi.log"

GREEN='\033[0;32m'; YELLOW='\033[1;33m'; RED='\033[0;31m'; CYAN='\033[0;36m'; NC='\033[0m'
ok()   { echo -e "${GREEN}✅  $*${NC}"; }
warn() { echo -e "${YELLOW}⚠️   $*${NC}"; }
err()  { echo -e "${RED}❌  $*${NC}"; exit 1; }
info() { echo -e "${CYAN}▶   $*${NC}"; }

# ── Démarrer le serveur ───────────────────────────────────────────
start_server() {
    if curl -s "$API/" > /dev/null 2>&1; then
        ok "Serveur déjà actif sur $API"
        return
    fi
    info "Démarrage du serveur FastAPI..."
    fuser -k 8000/tcp 2>/dev/null || true
    sleep 1
    .venv/bin/uvicorn app.main_cloud:app --host 0.0.0.0 --port 8000 > "$LOG" 2>&1 &
    sleep 4
    if ! curl -s "$API/" > /dev/null 2>&1; then
        err "Le serveur n'a pas démarré. Logs : $LOG"
    fi
    ok "Serveur démarré (PID $!)"
}

# ── Vérifier que le serveur tourne ───────────────────────────────
check_server() {
    curl -s "$API/" > /dev/null 2>&1 || err "Serveur non disponible sur $API — lancez : ./lancer.sh start"
}

# ── Arrêter le serveur ────────────────────────────────────────────
stop_server() {
    info "Arrêt du serveur..."
    fuser -k 8000/tcp 2>/dev/null && ok "Serveur arrêté" || warn "Aucun serveur actif"
}

# ── Supprimer les PDFs Drive ──────────────────────────────────────
delete_pdfs() {
    warn "Suppression des PDFs existants sur Drive..."
    $PYTHON - <<'PYEOF'
import sys, io
sys.path.insert(0, '.')
from app.drive_client import get_drive_service, list_files_in_folder
FOLDER = "17pjUuPMlKHjhmq80KBT69-nEHOlqXzNI"
svc = get_drive_service()
pdfs = [f for f in list_files_in_folder(svc, FOLDER) if f['name'].endswith('.pdf')]
for f in pdfs:
    svc.files().delete(fileId=f['id']).execute()
    print(f"  🗑  {f['name']}")
print(f"Supprimés : {len(pdfs)} fichier(s)")
PYEOF
}

# ─────────────────────────────────────────────────────────────────
CMD="${1:-run}"

echo ""
echo "══════════════════════════════════════════════"
echo "   Pipeline anonymi_cv  —  $(date '+%d/%m/%Y %H:%M')"
echo "══════════════════════════════════════════════"
echo ""

case "$CMD" in

    start)
        start_server
        ;;

    stop)
        stop_server
        ;;

    status)
        check_server && ok "Serveur actif sur $API"
        ;;

    process)
        check_server
        info "Extraction + anonymisation des CVs Drive..."
        curl -s -X POST "$API/process" | python3 -m json.tool
        ok "Traitement terminé"
        ;;

    generate)
        check_server
        delete_pdfs
        echo ""
        info "Génération des PDFs LaTeX..."
        curl -s -X POST "$API/generate-pdfs" | python3 -m json.tool
        ok "PDFs générés"
        ;;

    all)
        check_server
        info "Étape 1/2 — Extraction + anonymisation..."
        curl -s -X POST "$API/process" | python3 -m json.tool
        echo ""
        delete_pdfs
        echo ""
        info "Étape 2/2 — Génération des PDFs..."
        curl -s -X POST "$API/generate-pdfs" | python3 -m json.tool
        ok "Pipeline complet terminé"
        ;;

    reset)
        check_server
        delete_pdfs
        echo ""
        info "Régénération des PDFs..."
        curl -s -X POST "$API/generate-pdfs" | python3 -m json.tool
        ok "Reset terminé"
        ;;

    run)
        start_server
        echo ""
        info "Étape 1/2 — Extraction + anonymisation..."
        curl -s -X POST "$API/process" | python3 -m json.tool
        echo ""
        delete_pdfs
        echo ""
        info "Étape 2/2 — Génération des PDFs..."
        curl -s -X POST "$API/generate-pdfs" | python3 -m json.tool
        echo ""
        echo "══════════════════════════════════════════════"
        ok "Terminé — PDFs disponibles sur Drive (cv_traiter)"
        echo "══════════════════════════════════════════════"
        ;;

    *)
        echo "Usage : $0 [start|stop|status|process|generate|all|reset|run]"
        exit 1
        ;;
esac
echo ""
