# KAP disclosure triage: the app (panel, agent, morning list, evaluations) in one image.
# Data, the Matriks token and the models stay outside the image:
#   - data/ is mounted from the host (licensed Matriks data is never baked into an image),
#   - .env is passed at run time,
#   - Ollama runs on the host (on a Mac, Docker cannot use the GPU); OLLAMA_HOST points to it,
#   - embedding / reranker weights are cached in a named volume after the first run.
# See docs/docker.md.
FROM node:22-bookworm-slim AS smtp
WORKDIR /smtp
COPY mcp/smtp/package*.json ./
RUN npm ci --ignore-scripts

FROM python:3.12-slim-bookworm
COPY --from=smtp /usr/local/bin/node /usr/local/bin/node
COPY --from=smtp /smtp /app/mcp/smtp

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PANEL_HOST=0.0.0.0 \
    OLLAMA_HOST=http://host.docker.internal:11434

WORKDIR /app

# CPU build of torch first (the default Linux wheel pulls several GB of CUDA libraries)
RUN pip install torch==2.15.0 --index-url https://download.pytorch.org/whl/cpu
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY pyproject.toml main.py ./
COPY kap_triage/ kap_triage/
COPY docs/ docs/
# public frozen evidence JSONL files (no licensed data; used by verify-results and layer-attribution)
COPY evidence/set_c.jsonl \
     evidence/regex_set_c.jsonl \
     evidence/set_d.jsonl \
     evidence/injection_set_c.jsonl \
     evidence/rag_set_d.jsonl \
     evidence/
COPY README.md LICENSE ./
# sample/: the kap-kart examples and the folder `main.py panel --sample` builds into (sample/data/ is not copied)
COPY sample/ sample/
# editable, so the package and sample/ are found from /app, the same as in a git clone
RUN pip install --no-deps -e .

RUN useradd --create-home app && mkdir -p /app/data && chown -R app /app
USER app

EXPOSE 8765
CMD ["python", "main.py", "panel"]
