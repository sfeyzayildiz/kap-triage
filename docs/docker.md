# Running with Docker

One command starts the panel (chat, guided form, morning lists, themes, reliability page) in a container, so the project does not depend on one Mac's Python setup.

```
docker compose up --build        # first build takes several minutes (torch CPU, sentence-transformers)
# open http://127.0.0.1:8765
```

## What stays outside the image, and why
| Part | Where | Why |
|---|---|---|
| `data/` (DuckDB, morning lists, logs) | mounted from the host (`./data:/app/data`) | Matriks data is licensed: it is never baked into an image or pushed to a registry. |
| `.env` (`KAP_TOKEN`) | passed at run time, optional | Only collection needs the token; the panel does not. |
| Ollama + `gemma4:e4b` | runs on the host; the container calls `OLLAMA_HOST=http://host.docker.internal:11434` | On a Mac, Docker cannot use the GPU; a model inside the container would be many times slower. On a Linux GPU server, Ollama (or vLLM) would run as a second service next to the app. |
| Embedding and reranker weights | named volume `model-cache` | Downloaded once on the first search, kept across rebuilds. |

The port is published on `127.0.0.1` only, like the Mac setup: the panel is never reachable from the network. Inside the container it binds `0.0.0.0` (`PANEL_HOST`), which is required for the port mapping; the Origin / Referer checks accept `127.0.0.1` and `localhost` only.

## Other commands in the same image
```
docker compose run --rm panel python scripts/run_self_tests.py --skip daily_collect
docker compose run --rm panel python scripts/morning.py --date 2026-09-17 --from-pipeline data/morning_2026-09-17.jsonl
docker compose run --rm panel python scripts/agent.py "Bugün neye bakmalıyım?"
```

## Not in Docker (on purpose)
- **Nightly collection** stays on the Mac (launchd, `~/projects/kap-deploy`): Matriks allows one pull per day, and `pull_guard` counts pulls per machine. Running collection from a container as well would risk a second pull.
- **Collection window:** do not use the panel between 23:40 and 23:50, the same rule as on the Mac (the nightly job writes to the same DuckDB file).

## How a company would run it
The same image on an internal server or a private cloud (Turkish banks and brokers usually keep data on premises): the app container, an Ollama or vLLM container on a GPU node, the database on a managed volume, a reverse proxy with single sign-on in front of the panel, and the nightly collection as a scheduled job. None of that is needed for this prototype; the image is the first step towards it.
