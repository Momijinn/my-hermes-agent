# Agent Instructions

## Setup and operation

- Run commands from the repository root. Create runtime configuration with `cp .env.example .env`.
- 公開ファイル用のディレクトリを作成します: `mkdir -p ~/.hermes/public`
- Compose requires `.env` keys `HERMES_API_KEY` and `CLOUDFLARE_TUNNEL_TOKEN` at startup. `GATEWAY_TOKENS` is needed for authenticated Gateway use, and `OPENROUTER_API_KEY` is needed for the configured OpenRouter fallback. Slack integration additionally uses the three `SLACK_*` keys and optional `SLACK_ALLOWED_USERS`; keep all real secrets out of Git, logs, PRs, and generated artifacts.
- If an old dashboard deployment may exist, clean it before starting the current layout, in this order:

  ```sh
  docker compose --profile dashboard stop dashboard 2>/dev/null || true
  docker compose --profile dashboard rm -f dashboard 2>/dev/null || true
  docker rm -f hermes-dashboard 2>/dev/null || true
  docker compose up -d --build hermes gateway cloudflared
  ```

- Normal startup is `docker compose up -d --build hermes gateway cloudflared`; inspect with `docker compose ps` and `docker compose logs -f gateway cloudflared` (or `docker compose logs -f hermes`). Compose waits for Hermes health before Gateway, then Gateway health before `cloudflared`.
- Check local, LAN, and tunneled health with `curl -fsS http://127.0.0.1:9119/health`, `curl -fsS http://<docker-host-lan-ip>:9119/health`, and `curl -fsS https://<configured-hostname>/health`.
- Stop with `docker compose down`. Never use `docker compose down -v` or `rm -rf ~/.hermes`: the host-mounted `~/.hermes` contains shared persistent state, memory, credentials, and logs.

## Architecture

- `hermes/Dockerfile` pins `nousresearch/hermes-agent:v2026.6.5`, adds Node/npm, and seeds `hermes/config/config.yaml`. The Hermes entrypoint copies that config into the persistent `/opt/data` volume only when absent before running `hermes gateway run`.
- The Hermes image also contains RTK `v0.49.0`, installed from the official GitHub release with architecture-specific SHA-256 verification. Startup runs the official `rtk init --agent hermes` idempotently and treats the install as complete only when the marker and `/opt/data/plugins/rtk-rewrite/{__init__.py,plugin.yaml}` are both present and non-empty. It stores its tracking DB at `/opt/data/rtk/history.db`, disables telemetry, and continues fail-open if initialization fails. The persistent config is seeded only when absent so plugin enablement is not overwritten.
- Hermes is internal-only on `internal-net`; its API listens on container port 9119 and is not published to the host. Local model traffic uses `http://host.docker.internal:11234/v1`; the configured fallback is OpenRouter `openai/gpt-5.6-luna`.
- `gateway/main.py` is the FastAPI entrypoint, run by the gateway image as `uvicorn main:app --host 0.0.0.0 --port 9119`. It authenticates `Bearer` tokens, enforces context limits, and forwards `POST /v1/chat/completions` to Hermes without rewriting the payload. `GET /health` is unauthenticated.
- `GET /public/{path}` は `/opt/data/public` 上のファイルを認証なしで配信します。ファイルサイズ上限は10MBです。エージェントは公開ファイルを作成・更新する場合、`/opt/data/public/` に配置してください。
- `cloudflared` uses the Dashboard-managed, token-authenticated Cloudflare Tunnel to reach `http://gateway:9119`; Gateway port 9119 is also explicitly published for trusted host/LAN access and requires Gateway authentication. Streaming requests (`stream=true`) are intentionally rejected with HTTP 400.
- The dashboard runs inside Hermes with `HERMES_DASHBOARD_INSECURE=1` and is intentionally unauthenticated. The user explicitly approved direct host/LAN access, so Compose maps it as `8642:8642`; use only on a trusted network and never expose it through Cloudflare or another proxy.
- Only assign required hostnames/routes to the Cloudflare Tunnel, review Gateway and Cloudflare logs, and before internet exposure use strong tokens and consider Cloudflare Access, IP restrictions, and rate limits.

## Testing and CI

- Gateway tests: `python3 -m pytest gateway/test_main.py -q`. No test dependency/lockfile or repository install command is defined, so provide pytest and its dependencies separately when running tests.
- RTK smoke checks: `docker compose config --quiet`, `docker compose build hermes`, and `docker compose run --rm --no-deps hermes rtk --version`. Verify the running container with `docker compose exec hermes rtk --version`; do not put secrets in command output.
- Gateway defaults are `GATEWAY_MAX_CONTEXT_LINES=2000`, `GATEWAY_MAX_CONTEXT_CHARS=200000`, and a 180-second upstream timeout. The gateway maps oversized input to 413, malformed requests to 422, upstream failures to 502, and timeouts to 504.
- `.github/workflows/hermes-review.yml` only builds a PR diff, optionally calls the configured Gateway using `HERMES_GATEWAY_URL` and `HERMES_GATEWAY_TOKEN`, parses the response, and posts a PR comment via `gh`; it skips the Gateway call when either secret is absent. There is no CI build, test, lint, formatter, typecheck, or migration job.
- Treat PR diff content sent to Hermes as untrusted input; do not turn review output into automatically executable instructions.
