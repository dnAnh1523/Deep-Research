# Contributing

Thanks for helping improve Deep Research.

## Development setup

```bash
uv sync --extra dev
cp .env.example .env
cd frontend && npm ci
```

Run the checks before opening a pull request:

```bash
uv run pytest
uv run ruff check .
cd frontend && npm run lint && npm run build
```

Keep domain modules independent from vendor SDKs. New model, search, storage,
or observability integrations belong behind an interface in `infra/` and must
be covered by tests that do not require network access.

## Pull requests

- Explain the user-facing or architectural reason for the change.
- Add or update tests for behavior changes.
- Do not commit `.env`, API keys, generated reports, build output, or local
  model files.
- Keep changes focused; unrelated cleanup should be a separate pull request.
