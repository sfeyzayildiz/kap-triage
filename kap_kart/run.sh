#!/usr/bin/env bash
# kap-kart launcher (macOS / Linux): checks Python, Ollama and the model, then opens the paste page.
# It never downloads a model by itself; it prints the command instead.
set -euo pipefail
cd "$(dirname "$0")"
MODEL="${OLLAMA_MODEL:-gemma4:e4b}"
PORT="${PORT:-8770}"

if ! command -v python3 >/dev/null 2>&1; then
  echo "Python 3 bulunamadı. https://www.python.org adresinden kurun."; exit 1
fi
if [ ! -d .venv ]; then
  echo "İlk çalıştırma: sanal ortam kuruluyor..."
  python3 -m venv .venv
  .venv/bin/pip install -q -r requirements.txt
fi
if ! command -v ollama >/dev/null 2>&1; then
  echo "Ollama bulunamadı. https://ollama.com adresinden kurun, sonra tekrar çalıştırın."; exit 1
fi
if ! ollama list >/dev/null 2>&1; then
  echo "Ollama çalışmıyor. Ollama uygulamasını açın (ya da 'ollama serve'), sonra tekrar çalıştırın."; exit 1
fi
if ! ollama list | awk '{print $1}' | grep -qx "$MODEL"; then
  echo "Model yüklü değil. Bir kez şu komutu çalıştırın (birkaç GB indirir):"
  echo "  ollama pull $MODEL"
  exit 1
fi
.venv/bin/python kap_kart.py --self-test
echo "Tarayıcıda açın: http://127.0.0.1:$PORT"
( sleep 1; command -v open >/dev/null 2>&1 && open "http://127.0.0.1:$PORT" || true ) &
exec .venv/bin/python kap_kart.py --serve --port "$PORT"
