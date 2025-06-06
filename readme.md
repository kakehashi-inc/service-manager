# Universal Service Manager

汎用サービス管理ツールです。Linux（Ubuntu/RHEL）、macOS、WSL環境でカスタムサービス・プロセスの管理を行うことができます。

## 機能

- **サービス制御**: start（開始）、stop（停止）、restart（再起動）、status（状態確認）
- **一括操作**: `--all`オプションで全サービスの一括制御
- **サービス管理**: list（一覧表示）、add（追加）、modify（変更）、delete（削除）
- **ログ管理**: サービスごとのログファイル自動生成・管理
- **インタラクティブ設定**: CLI上でサービス設定の作成・編集

## インストール・セットアップ

### 必要な環境

- Python 3.6以上
- Linux、macOS、または WSL環境

### 使用方法

```bash
# スクリプトを実行可能にする
chmod +x service-manage.py

# または、Pythonで直接実行
python3 service-manage.py
```

## コマンド一覧

### サービス制御

#### 単体サービス操作

```bash
# サービス開始
./service-manage.py start <service_name>

# サービス停止
./service-manage.py stop <service_name>

# サービス再起動
./service-manage.py restart <service_name>

# サービス状態確認（ログの末尾5行も表示）
./service-manage.py status <service_name>
```

#### 全サービス一括操作

```bash
# 全サービス開始
./service-manage.py start --all

# 全サービス停止
./service-manage.py stop --all

# 全サービス再起動
./service-manage.py restart --all

# 全サービス状態確認
./service-manage.py status --all
```

### サービス管理

```bash
# サービス一覧表示
./service-manage.py list

# 新規サービス追加（インタラクティブ）
./service-manage.py add <service_name>

# サービス設定変更（インタラクティブ）
./service-manage.py modify <service_name>

# サービス削除
./service-manage.py delete <service_name>
```

### オプション

```bash
# 設定ファイルを指定（デフォルト: config.json）
./service-manage.py --config custom-config.json <command>

# ヘルプ表示
./service-manage.py -h
./service-manage.py <command> -h
```

## 設定ファイル（config.json）

サービス設定はJSON形式で管理されます：

```json
{
  "log_retention_days": 7,
  "directories": {
    "logs": "logs",
    "pids": "pids"
  },
  "services": {
    "my-service": {
      "command": "python3",
      "args": ["app.py", "--port", "8080"],
      "cwd": "/path/to/working/directory",
      "env": {
        "NODE_ENV": "production",
        "API_KEY": "your-api-key"
      }
    },
    "web-server": {
      "command": "npm",
      "args": ["start"],
      "cwd": "/path/to/web/app",
      "env": {
        "PORT": "3000"
      }
    }
  }
}
```

### 設定項目

#### グローバル設定

| 項目 | 説明 | デフォルト値 |
|------|------|------------|
| `log_retention_days` | 保持するログファイル数 | 7 |
| `directories.logs` | ログディレクトリのパス | "logs" |
| `directories.pids` | PIDディレクトリのパス | "pids" |

#### サービス設定

| 項目 | 説明 | 必須 |
|------|------|------|
| `command` | 実行するコマンド | ✓ |
| `args` | コマンドライン引数のリスト | |
| `cwd` | 作業ディレクトリ | |
| `env` | 環境変数の辞書 | |

## ログ管理

- ログファイルは`logs/`ディレクトリに自動生成されます
- ファイル名: `<service_name>-YYYY-MM-DD.log`（日付ごとに分割）
- サービス開始時に日時とともにログエントリが追加されます
- 同一日での複数回起動は同じファイルに追記されます
- 古いログファイルは自動削除されます（デフォルト: 7ファイル分を保持）

### ログ保持期間の設定

config.jsonで保持するログファイル数を設定できます：

```json
{
  "log_retention_days": 10,
  "directories": {
    "logs": "logs",
    "pids": "pids"
  },
  "services": {
    ...
  }
}
```

## 使用例

### 1. 新しいサービスを追加

```bash
./service-manage.py add my-web-server
```

インタラクティブで以下を設定：

```
Command []: node
Arguments (enter empty line to finish):
  Arg: server.js
  Arg: --port
  Arg: 3000
  Arg:
Working directory [.]: /home/user/web-app
Add environment variables? (y/N): y
Environment variables (format: KEY=VALUE, empty line to finish):
  Env var: NODE_ENV=production
  Env var: PORT=3000
  Env var:
```

### 2. サービスを開始して状態確認

```bash
# サービス開始
./service-manage.py start my-web-server

# 状態確認
./service-manage.py status my-web-server
```

### 3. 全サービスの管理

```bash
# 全サービス一覧
./service-manage.py list

# 全サービス開始
./service-manage.py start --all

# 全サービス状態確認
./service-manage.py status --all
```

## プロセス管理の仕組み

- プロセス検索は`ps`コマンドでコマンドライン内容を照合
- プロセスグループ単位での終了処理（SIGTERM → SIGKILL）
- プラットフォーム別の適切なシグナル処理
- 子プロセスも含めた確実な停止処理

## mcpサーバーのサンプルコマンド

mcp-server-filesystem

```bash
npx -y @modelcontextprotocol/server-filesystem /foo/bar/project
```

stdio -> SSE

```bash
npx -y supergateway \
    --stdio "npx -y @modelcontextprotocol/server-filesystem /foo/bar/project" \
    --port 8000 --baseUrl http://localhost:8000 \
    --ssePath /sse --messagePath /message
```

SSE -> stdio

```bash
npx -y supergateway --sse http://localhost:8000/sse
```
