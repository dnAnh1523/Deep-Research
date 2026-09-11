# Deployment guide

## Docker Compose baseline

```bash
copy .env.example .env
copy config/providers.example.json config/providers.json
# edit .env and config/providers.json; remove unused provider entries
docker compose up --build
```

The frontend is exposed at `http://localhost:3000`, the API at
`http://localhost:8000`, and PostgreSQL is internal to the Compose network.
The example uses a persistent PostgreSQL volume for LangGraph checkpoints.

Local Ollama is not bundled into the Compose file. Point a provider entry at a
reachable Ollama host, or run Ollama on the host with the appropriate network
address for the container runtime.

## Production checklist

- Use a managed secret store for `.env` values.
- Set `ENV=prod` and `DATABASE_URL`.
- Replace the development CORS origins with the real frontend origin.
- Put the API and frontend behind HTTPS and an auth/rate-limit layer.
- Configure a provider with verified tool calling and a model context budget
  suitable for the research workload.
- Add backups and retention for PostgreSQL.
- Monitor provider failures, latency, token usage, and unknown-cost calls.
