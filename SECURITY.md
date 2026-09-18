# Security policy

Please do not report secrets, API keys, or exploitable details in a public
issue. Send security reports privately to the repository maintainers first.

When self-hosting:

- keep the backend behind HTTPS and an authentication/rate-limit layer;
- never expose provider keys to the browser;
- use a persistent PostgreSQL checkpointer instead of in-memory state when persistence is needed;
- rotate any key that appears in logs, screenshots, commits, or crash reports.

This project is a self-hosted reference application and does not provide a
managed security boundary by itself.
