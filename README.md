# Hermes Agent AI Assistant

Hermes Agent v2026.6.5 を Docker Compose で起動するための最小構成です。通常はローカル LLM を使用し、ローカルモデルが利用できない場合だけ OpenRouter にフォールバックします。

## 構成

- `hermes/Dockerfile`: `nousresearch/hermes-agent:2026.6.5` を固定して Node.js/npm を追加
- `docker-compose.yml`: Hermes OpenAI互換APIとDashboardを同じHermesコンテナで有効化し、Gateway、Cloudflare Tunnel、永続データ、環境変数を設定
- `hermes/config/config.yaml`: ローカルモデルと OpenRouter フォールバックの初期設定テンプレート
- `gateway/Dockerfile`: Python 3.12 slim-bookworm を digest 固定して Gateway をビルド
- `gateway/requirements.txt`: Gateway の Python 実行依存関係をバージョン固定
- `.env.example`: 環境変数のテンプレート
- `.env`: 実行時の環境変数。Git 管理対象外
- `~/.hermes`: コンテナ外に永続化する Hermes の状態、メモリ、ログなど

## 別PCでのセットアップと起動

1. 別PCに Docker Desktop をインストールして起動します。
2. このディレクトリで、サンプルから実行用の環境ファイルを作成します。

```sh
cp .env.example .env
```

3. `.env` に `OPENROUTER_API_KEY` を設定します。Slack連携を使う場合は、Slack Appの設定画面で発行した `SLACK_BOT_TOKEN`、`SLACK_APP_TOKEN`、`SLACK_SIGNING_SECRET` を設定し、`SLACK_ALLOWED_USERS` に許可するSlackユーザーIDをカンマ区切りで設定します。実際のトークンやキーはこの配布ZIPやGitに入れないでください。
4. Slack App側で必要なSocket Mode、Bot Token Scopes、Event Subscriptionsなどを有効にし、Hermes側のSlack設定にも同じAppの情報を登録します。利用するHermesのSlack連携機能が要求する設定を確認してください。
5. ローカルLLMを使う場合は、ホスト上で `http://localhost:11234/v1/chat/completions` を提供していることを確認します。Hermes コンテナからは `host.docker.internal:11234` で接続します。
6. イメージをビルドして起動します。

```sh
docker compose up -d --build
```

ログを確認するには次を実行します。

```sh
docker compose logs -f hermes
```

稼働中のコンテナ状態は次で確認できます。

```sh
docker compose ps
```

## ローカルDashboard

Dashboardは公式の `HERMES_DASHBOARD=1` で既存の `hermes` コンテナ内に有効化します。別Dashboardコンテナ、別profile、別volumeは使用しません。ローカル専用のため `HERMES_DASHBOARD_INSECURE=1` を設定し、認証なしで起動します。`0.0.0.0:8642` はコンテナ内だけでlistenし、ホストでは必ず `127.0.0.1:8642` に限定公開します。

この構成ではDashboardのBasic Auth 3項目は不要です。Composeが設定するため、`.env` に認証情報を追加しないでください。

`HERMES_DASHBOARD_INSECURE=1` は、localhostへ到達できるすべてのローカルプロセスからDashboardが無認証で見える危険な設定です。ホスト公開を `127.0.0.1:8642:8642` 以外へ変更したり、DashboardをCloudflare Tunnelや別のリバースプロキシで外部公開したりしないでください。

```sh
docker compose up -d --build hermes gateway cloudflared
```

ブラウザで `http://localhost:8642` を開きます。ログイン操作は不要です。DashboardはCloudflare Tunnelの対象ではなく、外部経路は従来どおり `gateway:9119` です。

以前の構成で `hermes-dashboard` コンテナや `dashboard` profile が残っている場合は、旧コンテナを停止・削除してから現行構成を起動します。共有データを削除する `docker compose down -v` や `rm -rf ~/.hermes` は実行しないでください。

```sh
docker compose --profile dashboard stop dashboard 2>/dev/null || true
docker compose --profile dashboard rm -f dashboard 2>/dev/null || true
docker rm -f hermes-dashboard 2>/dev/null || true
docker compose up -d --build hermes gateway cloudflared
```

停止するには次を実行します。

```sh
docker compose down
```

## 設定ファイルの場所

Hermes Agent は通常 `~/.hermes/config.yaml` を読み込みます。この構成では、ホストの `~/.hermes` をコンテナの `/opt/data` にマウントします。設定テンプレートは `hermes/Dockerfile` でイメージへコピーされ、コンテナ起動時に `/opt/data/config.yaml` へ配置されます。設定ファイルを個別にマウントしないため、設定ファイルのマウントによる `Device or resource busy` を避けられます。

`hermes/config/config.yaml` の `base_url` は Docker コンテナから macOS ホスト上のローカル LLM に接続するため `http://host.docker.internal:11234/v1` としています。Hermes が `/chat/completions` を付加するため、実際のリクエスト先は `http://host.docker.internal:11234/v1/chat/completions` です。

Hermes の OpenAI 互換 API はコンテナ内の 9119 番ポートで起動し、`internal-net` 上の Gateway から `http://hermes:9119` で到達できます。Hermes の 9119 番ポートはホストへ公開しません。Gateway は Cloudflare Tunnel の入口であり、ローカル疎通確認用にホストの `127.0.0.1:9119` へだけ公開します。

## 注意点

- コンテナ内の `localhost` はコンテナ自身を指します。ローカル LLM が macOS ホスト上で動作している場合、Docker から到達できるホスト名に合わせて `base_url` を変更してください。Docker Desktop では通常 `host.docker.internal` が利用できます。
- OpenRouter のフォールバックモデルは `openai/gpt-5.6-luna` に設定しています。必要に応じて `fallback_providers[].model` を変更してください。
- Dashboardは同一Hermesコンテナ内で `HERMES_DASHBOARD_INSECURE=1` を使うローカル専用構成です。無認証であるため、ホスト公開を `127.0.0.1:8642:8642` から変更しないでください。
- `HERMES_DASHBOARD_PUBLIC_URL`はローカルURLの`http://localhost:8642`に固定しています。DashboardはCloudflare Tunnelで外部公開しません。

## GitHub Actions 連携（外部公開用）

GitHub Actions からローカルの Hermes Agent へ PR 差分を送る場合は、次の構成を使用します。

```text
GitHub Actions -> Cloudflare Tunnel (HTTPS) -> FastAPI Gateway -> Hermes Agent
                                             public-net       internal-net
```

FastAPI Gateway は `Authorization: Bearer` トークンとリクエストの形式を検証し、受信したOpenAI Chat Completions JSONを、主要フィールドと追加フィールドを保持したまま Docker 内部ネットワーク上の Hermes (`http://hermes:9119/v1/chat/completions`) へ転送します。Gatewayはレビュー用のcontextやsystem messageを生成しません。Hermes の 9119 番ポートはホストへ公開されません。

### Chat Completions API

`POST /v1/chat/completions` はBearer認証を使用し、OpenAI Chat Completions互換のJSONを受け付けます。`messages` は必須です。`model`、`temperature`、`max_tokens`、`stream` などのフィールドを指定でき、未知のフィールドも可能な限りHermesへ転送します。

```json
{
  "model": "",
  "messages": [
    {"role": "system", "content": "レビュー指示"},
    {"role": "user", "content": "PR情報と差分を含むレビュー用context全文"}
  ],
  "temperature": 0.3,
  "max_tokens": 4096,
  "stream": false
}
```

初期対応は `stream=false` のみです。`stream=true` はHTTP 400で拒否します。GatewayはHermesのOpenAI互換レスポンスを加工せず返します。入力サイズ上限（`GATEWAY_MAX_CONTEXT_LINES`、既定値2000、`GATEWAY_MAX_CONTEXT_CHARS`、既定値200000）を超過するとHTTP 413、形式不正はHTTP 422、Hermesの接続・応答障害はHTTP 502、タイムアウトはHTTP 504です。エラーはOpenAI形式のJSONを返します。

以前の `POST /review` と専用payload形式は廃止しました。既存の呼び出し元は `/v1/chat/completions` と標準の `messages` payloadへ移行してください。旧形式との互換性はありません。

### Cloudflare Tunnel の設定

1. Cloudflare Dashboard で Tunnel を作成し、対象環境の hostname をその Tunnel に割り当てます。Public hostname の Service は `http://gateway:9119` にします。
2. Tunnel の token を発行し、`.env` の `CLOUDFLARE_TUNNEL_TOKEN` に設定します。`credentials.json`、Tunnel ID、hostname をリポジトリへ配置する必要はありません。
3. `cloudflared` は `CLOUDFLARE_TUNNEL_TOKEN` で起動し、Tunnel の ingress は Cloudflare Dashboard で管理します。リポジトリ内の設定ファイルや credentials は不要です。

### GitHub Secrets

対象リポジトリの Settings > Secrets and variables > Actions に次を登録します。

- `HERMES_GATEWAY_URL`: Cloudflare Dashboard で設定した Cloudflare Tunnel の HTTPS URL
- `HERMES_GATEWAY_TOKEN`: Gateway の `GATEWAY_TOKENS` に登録した強いランダムトークン

`.env` には次を設定します。

```dotenv
GATEWAY_TOKENS=強いランダムトークン
HERMES_API_KEY=別の強いランダムトークン
CLOUDFLARE_TUNNEL_TOKEN=Cloudflareが発行したトークン
```

### サービスの起動

必要な設定と認証情報を配置した後、プロジェクトルートで実行します。

```sh
docker compose up -d --build hermes gateway cloudflared
docker compose ps
docker compose logs -f gateway cloudflared
```

Gateway のヘルスチェックは Tunnel の URL で確認できます。

```sh
curl -fsS http://127.0.0.1:9119/health
# Cloudflare Dashboardで設定した環境固有のURLでも確認する
curl -fsS https://<your-configured-hostname>/health
```

### セキュリティ上の注意

- Hermes の 9119 番ポートを `ports` でホストへ公開しないでください。Gateway と Hermes は `internal-net` でのみ通信します。
- Gateway トークン、Cloudflare 認証情報、GitHub Secrets はログ、PR、Git リポジトリへ出力しないでください。
- Cloudflare 側では必要なホスト名だけを Tunnel に割り当て、不要な公開ルートを作らないでください。
- `GATEWAY_MAX_CONTEXT_LINES` と `GATEWAY_MAX_CONTEXT_CHARS` で入力サイズを制限し、Gateway と Cloudflare のログを定期的に確認してください。
- Gateway の Python ベースイメージと実行依存関係、Cloudflare Tunnel イメージは、再現性のためタグと digest を固定しています。更新時は対象リリースと digest を検証してから変更してください。
- `pull_request` から送信される差分には未信頼のコードが含まれるため、レビュー結果を自動実行可能な入力として扱わないでください。
- Gateway をインターネットへ公開する前に、強いトークンを生成し、必要に応じて Cloudflare Access、IP 制限、レート制限を追加してください。
