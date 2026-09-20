# Hermes Agent AI Assistant

Hermes Agent v2026.6.5 を Docker Compose で起動するための最小構成です。OpenRouter の `deepseek/deepseek-v4-flash-0731` をデフォルトモデルとして使用し、利用できない場合は `openai/gpt-5.6-luna` にフォールバックします。

## 構成

- `hermes/Dockerfile`: `nousresearch/hermes-agent:2026.6.5` を固定して Node.js/npm を追加
- `docker-compose.yml`: Hermes OpenAI互換APIとDashboardを同じHermesコンテナで有効化し、Gateway、Cloudflare Tunnel、永続データ、環境変数を設定
- `hermes/config/config.yaml`: OpenRouterのデフォルトモデルとフォールバック、およびコメントアウトしたローカルモデル設定の初期テンプレート
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
5. ローカルLLMへ切り替える場合は、ホスト上で `http://localhost:11234/v1/chat/completions` を提供していることを確認し、`hermes/config/config.yaml` のコメントアウトされたローカルモデル設定を有効化します。Hermes コンテナからは `host.docker.internal:11234` で接続します。
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

Dashboardは公式の `HERMES_DASHBOARD=1` で既存の `hermes` コンテナ内に有効化します。別Dashboardコンテナ、別profile、別volumeは使用しません。ユーザー承認済みの直接アクセス用に `HERMES_DASHBOARD_INSECURE=1` を設定し、認証なしでホストの `8642` 番ポートへ公開します。

この構成ではDashboardのBasic Auth 3項目は不要です。Composeが設定するため、`.env` に認証情報を追加しないでください。

`HERMES_DASHBOARD_INSECURE=1` と `8642:8642` は、ホストやネットワークからDashboardが無認証で見える危険な設定です。信頼できるネットワークでのみ使用し、DashboardをCloudflare Tunnelや別のリバースプロキシで外部公開しないでください。

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

`hermes/config/config.yaml` では、OpenRouterを `model.provider` に指定し、`model.default` を `deepseek/deepseek-v4-flash-0731` に設定しています。ローカルモデルの `provider`、`default`、`base_url`、`api_mode` はコメントアウトで残してあり、必要な場合だけ有効化できます。ローカル設定を有効化した場合、`base_url` は Docker コンテナから macOS ホスト上のローカルLLMへ接続する `http://host.docker.internal:11234/v1` です。Hermes が `/chat/completions` を付加するため、実際のリクエスト先は `http://host.docker.internal:11234/v1/chat/completions` です。

Hermes の OpenAI 互換 API はコンテナ内の 9119 番ポートで起動し、`internal-net` 上の Gateway から `http://hermes:9119` で到達できます。Hermes の 9119 番ポートはホストへ公開しません。Gateway は `9119:9119` でホストとLANへ公開され、Cloudflare Tunnelからも到達できます。直接アクセスにはGatewayトークンが必要です。

## 注意点

- コンテナ内の `localhost` はコンテナ自身を指します。ローカル LLM が macOS ホスト上で動作している場合、Docker から到達できるホスト名に合わせて `base_url` を変更してください。Docker Desktop では通常 `host.docker.internal` が利用できます。
- デフォルトモデルは OpenRouter の `deepseek/deepseek-v4-flash-0731`、フォールバックモデルは `openai/gpt-5.6-luna` に設定しています。必要に応じて `model.default` または `fallback_providers[].model` を変更してください。
- Hermes、Gateway、Cloudflare Tunnel のコンテナは `TZ=Asia/Tokyo` で起動するため、コンテナ内の時刻は日本時間（JST）です。
- Dashboardは同一Hermesコンテナ内で `HERMES_DASHBOARD_INSECURE=1` を使う無認証構成です。ユーザー承認済みのためホストの `8642:8642` に公開しますが、信頼できるネットワークに限定してください。
- `HERMES_DASHBOARD_PUBLIC_URL`はローカルURLの`http://localhost:8642`に固定しています。DashboardはCloudflare Tunnelで外部公開しません。Gatewayは認証付きでLANからも到達できます。

## GitHub Actions 連携（外部公開用）

GitHub Actions からローカルの Hermes Agent へ PR 差分を送る場合は、次の構成を使用します。

```text
GitHub Actions -> Cloudflare Tunnel (HTTPS) -> FastAPI Gateway -> Hermes Agent
                                             public-net       internal-net
```

FastAPI Gateway は `Authorization: Bearer` トークンとリクエストの形式を検証し、受信したOpenAI Chat Completions JSONを、主要フィールドと追加フィールドを保持したまま Docker 内部ネットワーク上の Hermes (`http://hermes:9119/v1/chat/completions`) へ転送します。Gatewayはレビュー用のcontextやsystem messageを生成しません。Hermes の 9119 番ポートはホストへ公開されませんが、Gatewayの9119番ポートはホストとLANへ公開されます。

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

### 公開ファイルの配信 (/public)

`~/.hermes/public` ディレクトリにファイルを置くと、認証なしで `http://<host>:9119/public/<filename>` からアクセスできます。例えば、`logo.png` を置くと `http://localhost:9119/public/logo.png` でアクセスできます。

ファイルサイズの上限は10MBです。directory traversal 対策済みのため、公開ディレクトリ外のファイルにはアクセスできません。

`docker compose up -d --build hermes gateway cloudflared` を実行すると、`~/.hermes/public` は自動的にvolume mountされます。追加の設定は不要です。

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
# LAN上の別PCからは、DockerホストのLANアドレスを指定する
curl -fsS http://<docker-host-lan-ip>:9119/health
# Cloudflare Dashboardで設定した環境固有のURLでも確認する
curl -fsS https://<your-configured-hostname>/health
```

### セキュリティ上の注意

- Hermes の 9119 番ポートは `ports` でホストへ公開しないでください。Gatewayの9119番ポートはLANへ公開されるため、Gatewayトークンを必ず設定し、信頼できるネットワークに限定してください。Gateway と Hermes は `internal-net` でも通信します。
- Gateway トークン、Cloudflare 認証情報、GitHub Secrets はログ、PR、Git リポジトリへ出力しないでください。
- Cloudflare 側では必要なホスト名だけを Tunnel に割り当て、不要な公開ルートを作らないでください。
- `GATEWAY_MAX_CONTEXT_LINES` と `GATEWAY_MAX_CONTEXT_CHARS` で入力サイズを制限し、Gateway と Cloudflare のログを定期的に確認してください。
- Gateway の Python ベースイメージと実行依存関係、Cloudflare Tunnel イメージは、再現性のためタグと digest を固定しています。更新時は対象リリースと digest を検証してから変更してください。
- `pull_request` から送信される差分には未信頼のコードが含まれるため、レビュー結果を自動実行可能な入力として扱わないでください。
- Gateway をインターネットへ公開する前に、強いトークンを生成し、必要に応じて Cloudflare Access、IP 制限、レート制限を追加してください。
