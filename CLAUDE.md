# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this app does

Flask web app that acts as a front-end bridge to an AS/400 ERP system (via its HTTP REST API). It provides two main workflows:

1. **Pedidos** – browse suppliers/articles/stocks and submit purchase orders to AS/400.
2. **Asientos contables** – compose double-entry accounting records and post them to the AS/400 accounting module (IAERP). Supports AI suggestions (multi-provider), CSV/Excel/Norma 43 import, and a learning library of example entries.

Multi-company (`empresas.json`) and multi-user (`users.json`) with file-based JSON storage for everything (no database).

## Commands

### Local development

```bash
bash scripts/dev.sh          # creates venv, installs deps, copies .env if missing, starts flask dev server
python app.py                # run directly after activating venv
```

App runs at `http://127.0.0.1:5100`.

### Tests

```bash
python -m pytest tests/                          # run all tests
python -m pytest tests/test_csv_asiento.py       # single test file
python -m unittest tests.test_asiento_validaciones  # unittest style
```

### Docker (production)

```bash
docker-compose up --build    # build and start
docker-compose up -d         # detached
```

### User management

```bash
python scripts/manage-users.py --help
python scripts/importar_ejemplos_xlsx.py asi_mod.xlsx   # import AI examples from xlsx
```

## Architecture

### Request flow

```
Browser → Flask routes (app.py)
              ↓
         empresa_session.py  ← which empresa is active in this session
              ↓
         as400_api.py        ← HTTP calls to AS/400 REST endpoints
         (or cuentas_cache.py for chart-of-accounts reads)
              ↓
         historial_store.py  ← persists every operation + idempotency key
```

### Key modules

| File | Role |
|------|------|
| `app.py` | All Flask routes; business logic for validation, idempotency, retry |
| `config.py` | `Config` class loaded from `.env` via `python-dotenv` |
| `as400_api.py` | HTTP client for orders (`pedidos` service) and accounting (`contabilidad` service); tracks per-service status |
| `as400_api_cuentas.py` | Normalizes raw account records returned by AS/400 |
| `empresas_store.py` | Reads `empresas.json`; resolves per-company base URLs and endpoint paths; falls back to `AS400_API_BASE_URL` env var if the file is empty |
| `users_store.py` | Reads `users.json`; falls back to `APP_LOGIN_USER`/`APP_LOGIN_PASSWORD` env vars |
| `auth.py` | Flask `@login_required` / `@admin_required` decorators and session helpers |
| `empresa_session.py` | Stores the active empresa in Flask session; validates user access |
| `historial_store.py` | Append-only JSON log of all operations; implements idempotency via `fcntl` file locking |
| `cuentas_cache.py` | In-process per-empresa cache of the chart of accounts fetched from AS/400 |
| `cuenta_tipos.py` | Classifies account codes into semantic types (`cliente`, `iva_soportado`, etc.) and enriches them for AI use |
| `ai_asiento.py` | AI accounting-entry suggestion; supports OpenAI, Groq, Gemini, Anthropic, and Ollama providers; uses few-shot examples from `asientos_ejemplos_store.py` |
| `csv_asiento.py` | Parses CSV, Excel, TSV, and Norma 43 bank-statement files into asiento line candidates |
| `norma43_asiento.py` | Norma 43 (`.n43`/`.43`) bank-statement format parser |
| `asientos_ejemplos_store.py` | CRUD for the per-empresa AI example library (`asientos_ejemplos.json`) |
| `historial_store.py` | Also implements idempotency: `crear_o_recuperar_operacion` returns `"nuevo"` / `"existente"` / `"conflicto"` |

### Empresa configuration

Empresas are defined in `empresas.json` (see `empresas.json.example`). Each empresa can override:
- `base_url` – pedidos service URL
- `contabilidad_base_url` – IAERP accounting URL (falls back to `AS400_CONTABILIDAD_BASE_URL` env var, then `base_url`)
- `endpoints` – map of operation names to paths (defaults in `empresas_store.DEFAULT_ENDPOINTS`)
- `api_user` / `api_password` – per-empresa credentials (fall back to `AS400_API_USER`/`AS400_API_PASSWORD`)

### Idempotency

Every pedido/asiento confirmation generates an `idempotency_key` (UUID). `historial_store.crear_o_recuperar_operacion` checks the key before calling AS/400; duplicate submissions return the cached result instead of creating a second operation. The client sends the key via `Idempotency-Key` header or JSON body field.

### AI providers

Configured via `AI_ASIENTO_PROVIDER` env var: `openai` | `groq` | `google` | `claude` | `ollama`. All providers are called via the OpenAI-compatible chat endpoint (except Anthropic, which uses its own SDK). The provider-specific keys (`OPENAI_API_KEY`, `GROQ_API_KEY`, `GEMINI_API_KEY`, `ANTHROPIC_API_KEY`) can also be set via the generic `AI_ASIENTO_API_KEY`.

### Data files

All JSON data files live in the working directory (configurable via env vars):

| File | Default env var |
|------|----------------|
| `users.json` | `APP_USERS_FILE` |
| `empresas.json` | `APP_EMPRESAS_FILE` |
| `asientos_ejemplos.json` | `APP_ASIENTOS_EJEMPLOS_FILE` |
| `historial_operaciones.json` | `APP_HISTORIAL_FILE` |

The Docker compose mounts `users.json` and `empresas.json` as volumes so they persist across container rebuilds. `historial_operaciones.json` and `asientos_ejemplos.json` are **not** mounted by default — add them to `docker-compose.yml` if persistence is needed.
