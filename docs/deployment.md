# Self-Hosting & Docker Guide

## Docker Compose

```bash
copy .env.example .env
copy config/providers.example.json config/providers.json
# edit .env and config/providers.json; fill provider keys/endpoints
docker compose up --build
```

The frontend is exposed at `http://localhost:3000`, the API at `http://localhost:8000`, and PostgreSQL is internal to the Compose network for persisting LangGraph checkpoints.

Local Ollama is not bundled into the Compose file. Point a provider entry at a reachable Ollama host, or run Ollama on the host with the appropriate network address for the container runtime (`host.docker.internal`).
