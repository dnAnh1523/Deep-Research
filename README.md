# Deep Research Agent

An open-source deep-research workbench built around LangGraph. It turns a
research question into a reviewable plan, runs parallel web research, verifies
sources, and streams a cited Markdown report back to a React interface.

The application does not lock users to one model vendor. Bring your own keys
and choose OpenAI, Anthropic, Groq, Cerebras, OpenRouter, Ollama Cloud, local
Ollama, vLLM, LM Studio, or any gateway that implements OpenAI Chat
Completions. Provider selection lives in a local JSON file, never in the
frontend bundle.

## Demo

The repository is designed for a short screen recording showing:

1. entering a research question;
2. reviewing and expanding the generated plan;
3. starting the parallel research stream;
4. watching progress and web sources appear;
5. reading the final report and citation popovers.

See [`docs/demo.md`](docs/demo.md) for the recording script and recommended
GIF/video export settings. Add the published video URL to this section when a
release demo is recorded; the source repository intentionally does not contain
a fabricated or provider-key-dependent recording.

## Architecture

```text
React/Vite UI
       │ REST + Server-Sent Events
FastAPI HTTP adapter
       │
Composition root → provider router / search client / checkpointer
       │
LangGraph: session → intent → brief → supervisor ⇄ researchers
       │                         → compression → citation verification → report
       │
PostgreSQL checkpointer (production) or InMemorySaver (development)
```

Domain nodes depend on the small protocols in `infra/interfaces.py`. Vendor
HTTP and lifecycle code stays at the infrastructure boundary, so a new model
gateway does not require changes to the research pipeline.

## Quick start

### 1. Backend

Requirements: Python 3.12 or 3.13 and [uv](https://docs.astral.sh/uv/).

```bash
uv sync --extra dev
copy .env.example .env       # Windows
# cp .env.example .env       # macOS/Linux
copy config/providers.example.json config/providers.json
```

Edit `config/providers.json` and set the `api_key_env` values in `.env`. At
least one configured LLM and `TAVILY_API_KEY` are needed for a real research
run. You may omit Tavily while working on the UI or using the mocked tests.

Start the API:

```bash
uv run uvicorn api.app:app --host 127.0.0.1 --port 8000 --reload
```

### 2. Frontend

```bash
cd frontend
npm ci
npm run dev
```

Open <http://localhost:3000>. Vite proxies `/research`, `/api`, and `/health`
to the backend at port 8000.

### 3. Full-stack helper

From the repository root:

```bash
uv run python run_fullstack.py
```

The helper starts FastAPI and Vite together. It does not install dependencies
or expose the service to the public internet.

## Provider configuration

The recommended configuration is `config/providers.json`, which is ignored by
Git because it may contain private endpoint metadata. Start from
`config/providers.example.json`:

```json
{
  "primary": [
    {
      "provider": "my-gateway",
      "protocol": "openai-compatible",
      "model": "my-model-id",
      "base_url": "https://gateway.example.com/v1",
      "api_key_env": "MY_GATEWAY_API_KEY",
      "supports_tools": true
    }
  ],
  "fallback": null
}
```

Use `protocol: "anthropic"` for the native Anthropic Messages API. Use
`protocol: "openai-compatible"` for OpenAI, Groq, Cerebras, OpenRouter, Ollama
Cloud/local, vLLM, LM Studio, and compatible self-hosted gateways. The
router's cooldown key is `(provider, model)`, and fallback is optional.

The `supports_tools` flag is deliberately explicit: this pipeline needs tool
calling for research delegation. Verify a model's tool/function-calling
behavior before enabling it in a production configuration.

## Production deployment

For a self-hosted deployment, set:

- `ENV=prod`;
- `DATABASE_URL` to PostgreSQL (Supabase is supported too);
- a real `CORS_ORIGINS` allowlist;
- provider keys only in the deployment secret store;
- HTTPS, authentication, and rate limiting in the reverse proxy or platform.

The repository includes a `Dockerfile`, `docker-compose.yml`, and CI workflow
for the baseline deployment. Local Ollama is intentionally an external
service because GPU/runtime setup differs by host. See
[`docs/deployment.md`](docs/deployment.md).

## API

| Method | Endpoint | Purpose |
| --- | --- | --- |
| GET | `/health` | Liveness check |
| GET | `/ready` | Configuration/readiness check |
| POST | `/research/plan` | Generate a reviewable plan |
| POST | `/research` | Run the graph and return the completed response |
| POST | `/research/stream` | Stream graph updates over SSE |
| GET | `/api/latest-report` | Compatibility endpoint for a locally generated report |

Provider credentials are server-side only. The browser receives research
events and reports, never API keys.

## Development checks

```bash
uv run pytest -q
uv run ruff check .
cd frontend
npm run lint
npm run build
```

Tests use fakes and HTTP mocks; they do not need provider or search-network
access.

## Publish to GitHub

After reviewing the asset licenses and adding your remote repository:

```bash
git init -b main
git add .
git commit -m "Prepare open-source release"
git remote add origin https://github.com/<owner>/<repository>.git
git push -u origin main
```

Run `git diff --cached` before the first commit and confirm that `.env`, local
provider config, generated reports, `node_modules`, and build artefacts are not
included.

## Repository layout

```text
api/                  FastAPI adapter and SSE endpoints
clarify/ ...          LangGraph domain nodes grouped by feature
infra/                Protocols, adapters, settings, router, persistence
state/                Typed graph state
frontend/             Vite + React workbench
config/               Safe provider configuration template
docs/                 Architecture, deployment, demo, and maintainer notes
tests/                Network-free unit/integration tests
```

## Responsible use

Research output can be incomplete, stale, or wrong. Always inspect the cited
sources before relying on a report. Respect provider terms, website robots
policies, copyright, and applicable law. This is a self-hosted reference
application, not a managed security boundary.

## License

MIT. See [`LICENSE`](LICENSE). Third-party icon attribution is recorded in
[`NOTICE.md`](NOTICE.md); verify the original asset licenses before publishing
a release.
