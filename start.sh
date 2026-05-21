#!/usr/bin/env bash
# ══════════════════════════════════════════════════════
# SIRGA v2 — Sistema Inteligente de Riesgos · Antioquia
# Uso: bash start.sh
# ══════════════════════════════════════════════════════
set -e
GREEN='\033[0;32m'; BLUE='\033[0;34m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; NC='\033[0m'

echo -e "${BLUE}"
echo "  ███████╗██╗██████╗  ██████╗  █████╗     ██╗   ██╗██████╗ "
echo "  ██╔════╝██║██╔══██╗██╔════╝ ██╔══██╗    ██║   ██║╚════██╗"
echo "  ███████╗██║██████╔╝██║  ███╗███████║    ██║   ██║ █████╔╝"
echo "  ╚════██║██║██╔══██╗██║   ██║██╔══██║    ╚██╗ ██╔╝██╔═══╝ "
echo "  ███████║██║██║  ██║╚██████╔╝██║  ██║     ╚████╔╝ ███████╗"
echo "  ╚══════╝╚═╝╚═╝  ╚═╝ ╚═════╝ ╚═╝  ╚═╝      ╚═══╝  ╚══════╝"
echo -e "${NC}"
echo -e "${GREEN}  Sistema Inteligente de Riesgos Ambientales · Antioquia, Colombia${NC}"
echo -e "${CYAN}  IRG (20 variables) · IA Multi-Modelo · Alertas inteligentes · Mapa RT${NC}"
echo ""

# Verificar Python
if ! command -v python3 &>/dev/null; then
    echo "❌ Python 3 requerido. Instalar en: https://python.org"; exit 1
fi
PY=$(python3 --version 2>&1); echo "  Python: $PY ✓"

# Instalar dependencias
echo ""
echo "  📦 Instalando dependencias…"
cd "$(dirname "$0")/backend"
pip install fastapi uvicorn pydantic aiohttp python-dotenv --quiet 2>/dev/null || \
pip install fastapi uvicorn pydantic aiohttp python-dotenv -q
echo "  ✅ Dependencias listas"

# Iniciar API
echo ""
echo "  🚀 Iniciando API en http://localhost:8000 …"
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload &
API_PID=$!
sleep 2

# Verificar que levantó
if curl -s http://localhost:8000/health > /dev/null 2>&1; then
    echo "  ✅ API activa"
else
    echo "  ⚠️  API tardando en iniciar — espera 5s más…"
    sleep 3
fi

cd ..

# Abrir frontend
echo ""
echo "  🌐 Abriendo dashboard…"
if command -v xdg-open &>/dev/null; then xdg-open frontend/index.html 2>/dev/null &
elif command -v open &>/dev/null; then open frontend/index.html 2>/dev/null &
else echo "  → Abre manualmente: frontend/index.html"; fi

echo ""
echo -e "${GREEN}  ══════════════════════════════════════════════════${NC}"
echo -e "${GREEN}  ✅  SIRGA v2 activo${NC}"
echo -e "${GREEN}  ══════════════════════════════════════════════════${NC}"
echo ""
echo "  📊  Dashboard:       abre frontend/index.html"
echo "  🔌  API REST:        http://localhost:8000"
echo "  📖  Documentación:   http://localhost:8000/docs"
echo ""
echo "  Endpoints nuevos:"
echo "  GET  /api/v1/irg/zona/guatape           → IRG (20 variables)"
echo "  GET  /api/v1/irg/dashboard/guatape      → IRG compacto"
echo "  GET  /api/v1/ia/modelos                 → modelos IA disponibles"
echo "  POST /api/v1/ia/analizar                → análisis IA (local/Claude/OpenAI)"
echo "  GET  /api/v1/ia/analizar-rapido/guatape → análisis rápido GET"
echo ""
echo "  Presiona Ctrl+C para apagar"
echo ""
trap "echo ''; echo '  Sistema apagado.'; kill $API_PID 2>/dev/null" EXIT
wait $API_PID
