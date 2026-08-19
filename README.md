# rapi

[English](README.en.md)

テスト用の **REST API モック** を作る CLI です。

エンドポイント・メソッド・レスポンス（条件分岐やプレースホルダー付き）を
`rapi host` で定義し、`rapi start` で待ち受けます。
クライアントからは普通の HTTP（GET / POST / QUERY など）で叩けます。


> **方針メモ**  
> 当面は CLI（`host` → `start`）を主経路とし、手元のテスト用モックを素早く立てることを優先します。  
> 今後の改修では、既存の OpenAPI を **きちんと取り込んで使える主経路** としても育てていきます（example・基本的な path/method/parameter などから順に）。  
> 独自の条件分岐や一覧生成は、必要に応じて `x-rapi-*` や CLI オプションで補完する二階建てのイメージです。
> 詳細ドキュメントは落ち着いたタイミングで GitHub Wiki にもまとめる予定です（後回し）。

## なにができるか

- REST エンドポイントをモック（パス + メソッド単位）
- JSON レスポンス（ファイル指定可）
- クエリ / ボディのバリデーション
- 条件付きレスポンス（特定 ID だけ 400 など）
- レスポンスへのリクエスト値の埋め込み（`{INPUT.body.id}`）
- バックグラウンド起動・停止・状態確認

## インストール

```bash
unzip rapi-tool.zip
cd rapi-tool
sh install.sh
# デフォルトで ~/.local/bin/rapi を作成
# requirements.txt（PyYAML 等）も可能な範囲で pip install します

# 依存だけ別途入れる場合
pip install -r requirements.txt

# PATH に通す（未設定の場合）
export PATH="$HOME/.local/bin:$PATH"
```

別の場所に入れる場合:

```bash
sh install.sh /usr/local/bin    # 要権限
# または
sh install.sh ~/bin
```

インストール後は **python を付けずに** 使えます:

```bash
rapi --help
rapi host /sample get -r '{"ok":true}'
rapi start
rapi status
rapi stop
```

## サブコマンド

| コマンド | 説明 |
|---------|------|
| `rapi host` | REST 定義を登録（ポートは指定しない。`--group` でグループ分け、省略時 `default`） |
| `rapi start` | サーバー起動（`--port` / `--group`。グループごとに別プロセス） |
| `rapi stop` | 停止（`--force` で PID に即 SIGKILL） |
| `rapi restart` | 再起動 |
| `rapi status` | 起動状態と定義一覧 |
| `rapi delete` | 定義削除（起動中なら停止） |
| `rapi save` | 定義を JSON に書き出し |
| `rapi load` | JSON から定義を読み込み |



## サーバー停止

```bash
rapi stop --group default
rapi stop --group default --force   # 記録された PID に即 SIGKILL
```

PID が取れないときは **プロセスは触りません**。古い pid/port ファイルを消したうえで、確認用コマンドを表示します。

```bash
ss -ltnp | grep 8000
lsof -i :8000
# kill <PID>   または   kill -9 <PID>
```

ポート番号だけで無関係なプロセスを落とすことはしません。

## グループ（`--group`）

定義・プロセスを名前で分けます。省略時はすべて `default` です。

```bash
rapi host /a get -r '{"ok":true}' --group api-a
rapi host /b get -r '{"ok":true}' --group api-b

rapi start --group api-a --port 8001
rapi start --group api-b --port 8002

rapi status
rapi stop --group api-a
```

状態ファイルは `~/.rapi/groups/<group>/` 配下（pid / port / log）に分かれます。

## 基本の流れ

```bash
# 定義（ポートはここでは指定しない）
rapi host /sample get -r '{"ok":true,"q":"{INPUT.query.id}"}'

rapi host /sample post \
  -r '{"ok":true,"id":"{INPUT.body.id}"}' \
  --when 'body.id=004' \
  --rule-status 400 \
  --rule-response '{"error":"invalid id","received":"{INPUT.body.id}"}'

# 起動（ポートは start 時に指定）
rapi start --port 8000

# 呼び出し
curl 'http://127.0.0.1:8000/sample?id=123'
curl -X POST -d '{"id":"004"}' http://127.0.0.1:8000/sample

rapi status
rapi stop
```

起動時の PID とポートはグループごとに `~/.rapi/groups/<group>/rapi.log` に記録されます。

パスパラメータやクエリの応用例は、[パス + クエリの組み合わせ例](#パス--クエリの組み合わせ例) を参照してください。


## パスパラメータ

`{name}` 形式のパスを定義できます。

```bash
rapi host '/users/{id}' get -r '{"id":"{INPUT.path.id}"}'
rapi start --port 8000
curl http://127.0.0.1:8000/users/42
# → {"id":"42"}
```

| 記法 | 意味 |
|------|------|
| `{INPUT.path}` | 実際のパス全体（`/users/42`） |
| `{INPUT.path.id}` | パスパラメータ `id` |
| `--when 'path.id=000'` | 条件にも利用可 |



## 遅延レスポンス（タイムアウト検証）

```bash
# デフォルト応答を 1500ms 遅らせる
rapi host /slow get -r '{"ok":true}' --delay 1500

# 条件にマッチしたときだけ遅延
rapi host /api post -r '{"ok":true}' \
  --when 'body.id=timeout' \
  --rule-status 200 \
  --rule-response '{"ok":true}' \
  --rule-delay 3000

rapi start --port 8000
curl http://127.0.0.1:8000/slow   # 約 1.5 秒後に応答
```

| オプション | 意味 |
|-----------|------|
| `--delay MS` | デフォルトレスポンスの遅延（ミリ秒） |
| `--rule-delay MS` | 対応する `--when` の遅延（書いた順に対応） |

## パス + クエリの組み合わせ例

### 一覧（クエリ）

```bash
rapi host /items get \
  --param 'limit=~^\d+$' \
  --param offset \
  -r '{"limit":"{INPUT.query.limit}","offset":"{INPUT.query.offset}"}'

rapi start --port 8000
curl 'http://127.0.0.1:8000/items?limit=10&offset=0'
```

### 詳細（パスパラメータ）

```bash
rapi host '/items/{id}' get \
  -r '{"id":"{INPUT.path.id}"}'

curl http://127.0.0.1:8000/items/42
# → {"id":"42"}
```

### パス + クエリ

```bash
rapi host '/users/{userId}/orders' get \
  --param 'status=open' \
  -r '{"userId":"{INPUT.path.userId}","status":"{INPUT.query.status}"}'

curl 'http://127.0.0.1:8000/users/u1/orders?status=open'
```

### パス条件でエラー分岐

```bash
rapi host '/users/{id}' get \
  -r '{"id":"{INPUT.path.id}","ok":true}' \
  --when 'path.id=000' \
  --rule-status 404 \
  --rule-response '{"error":"not found","id":"{INPUT.path.id}"}'

curl http://127.0.0.1:8000/users/000
# → 404
curl http://127.0.0.1:8000/users/001
# → 200
```

### 複数クエリ + strict

```bash
rapi host /search get \
  --param q \
  --param 'page=~^\d+$' \
  --strict \
  -r '{"q":"{INPUT.query.q}","page":"{INPUT.query.page}"}'

# OK
curl 'http://127.0.0.1:8000/search?q=test&page=1'
# NG（余分なクエリ）
curl 'http://127.0.0.1:8000/search?q=test&page=1&extra=1'
```

## プレースホルダー

| 記法 | 意味 |
|------|------|
| `{INPUT.method}` | HTTP メソッド |
| `{INPUT.path}` | パス全体 |
| `{INPUT.path.id}` | パスパラメータ |
| `{INPUT.query.aaa}` | クエリ |
| `{INPUT.body}` | ボディ全体 |
| `{INPUT.body.id}` | JSON の id |
| `{INPUT.header.X-Request-Id}` | ヘッダー |

`"Test{INPUT.body.id}"` + id=004 → `"Test004"`

## 条件付きレスポンス

- `--when` を上から評価し、**最初にマッチした rule** を使用
- 1つの `--when` 内はカンマ区切りで **AND**
- どの rule にもマッチしなければ default レスポンス

### `=` と `=~` の違い

| 書き方 | 意味 |
|--------|------|
| `body.id=004` | **完全一致**（値がちょうど `004`） |
| `body.id=~^9` | **正規表現**（`~` の後ろを正規表現として扱う） |

`~` はリクエストの値ではなく、rapi 側の「正規表現モード」を表す記号です。

| 例 | マッチする値の例 |
|----|------------------|
| `body.id=004` | `"004"` のみ |
| `body.id=~^9` | `"9"`, `"999"`, `"90"` など 9 で始まるもの |
| `body.id=~^\d{3}$` | 数字ちょうど 3 桁 |

シェルでは `^` などのため、`--when` の値は **シングルクォート**推奨です。

### 定義例

```bash
rapi host /api/item post \
  -r '{"ok":true,"id":"{INPUT.body.id}"}' \
  --when 'body.id=004' --rule-status 400 \
  --rule-response '{"error":"bad id","received":"{INPUT.body.id}"}' \
  --when 'body.id=~^9' --rule-status 503 \
  --rule-response '{"error":"unavailable"}'

rapi start --port 8000
```

### 条件付きサンプル）通常（200）

```bash
curl -X POST -d '{"id":"001"}' http://127.0.0.1:8000/api/item
```

### 条件付きサンプル）id=004 → 400

```bash
curl -X POST -d '{"id":"004"}' http://127.0.0.1:8000/api/item
```

### 条件付きサンプル）id が 9 始まり → 503

```bash
curl -X POST -d '{"id":"999"}' http://127.0.0.1:8000/api/item
```


## リクエストボディの検証（`--body` / `--body-file`）

受信したリクエストボディが期待どおりかチェックします。合わなければ **400** を返します。

| オプション | 意味 |
|-----------|------|
| `-b` / `--body` | 期待ボディを文字列で指定 |
| `--body-file` | 期待ボディをファイルから読む |

- ファイル／文字列が `~` で始まる → **正規表現**（部分一致）
- それ以外 → **一致判定**
  - 前後の空白・末尾改行は無視
  - 両方とも JSON としてパースできる場合は、中身（キー順やスペースの違いを無視）で比較

### サンプル）完全一致（ファイル）

`expected.json` の内容とリクエストボディが一致するときだけ 200:

```bash
cat > expected.json << 'EOF'
{"name":"taro","age":30}
EOF

rapi host /users post   -r '{"ok":true}'   --body-file expected.json

rapi start --port 8000

# OK
curl -X POST -H 'Content-Type: application/json'   -d '{"name":"taro","age":30}'   http://127.0.0.1:8000/users

# NG（400）
curl -X POST -H 'Content-Type: application/json'   -d '{"name":"jiro"}'   http://127.0.0.1:8000/users
```

### サンプル）正規表現（ファイル）

ファイル先頭を `~` にすると正規表現モード:

```bash
cat > expected_re.txt << 'EOF'
~"name"\s*:\s*".+"
EOF

rapi host /users post   -r '{"ok":true}'   --body-file expected_re.txt
```

### サンプル）コマンドラインで指定

```bash
# 完全一致
rapi host /users post -r '{"ok":true}' --body '{"name":"taro"}'

# 正規表現（name キーが含まれる）
rapi host /users post -r '{"ok":true}' --body '~"name"'
```

### レスポンスをファイルから（参考）

返すボディ側は `-f` / `--response-file` です（`--body-file` とは別）:

```bash
cat > response.json << 'EOF'
{"ok":true,"id":"{INPUT.body.id}"}
EOF

rapi host /users post -f response.json
```


## 条件付きレスポンスのボディをファイルから（`--rule-response-file`）

`--when` に対応するエラー／分岐用レスポンスを、文字列ではなくファイルから読めます。

| オプション | 意味 |
|-----------|------|
| `--rule-response` | rule のレスポンスボディを文字列で指定 |
| `--rule-response-file` | 同上をファイルから読む |
| `--rule-status` | その rule の HTTP ステータス |

`--when` / `--rule-status` / `--rule-response`（または `--rule-response-file`）は **書いた順に対応** します。

### サンプル

```bash
# 通常レスポンス
cat > ok.json << 'EOF'
{"ok":true,"id":"{INPUT.body.id}"}
EOF

# id=004 のとき
cat > err004.json << 'EOF'
{"error":"bad id","received":"{INPUT.body.id}"}
EOF

# id が 9 始まりのとき
cat > err9.json << 'EOF'
{"error":"unavailable"}
EOF

rapi host /api/item post \
  -f ok.json \
  --when 'body.id=004' \
    --rule-status 400 \
    --rule-response-file err004.json \
  --when 'body.id=~^9' \
    --rule-status 503 \
    --rule-response-file err9.json

rapi start --port 8000
```

### 条件付きサンプル）通常（200）

```bash
curl -X POST -d '{"id":"001"}' http://127.0.0.1:8000/api/item
```

### 条件付きサンプル）id=004 → 400

```bash
curl -X POST -d '{"id":"004"}' http://127.0.0.1:8000/api/item
```

### 条件付きサンプル）id が 9 始まり → 503

```bash
curl -X POST -d '{"id":"999"}' http://127.0.0.1:8000/api/item
```

`--rule-response` と `--rule-response-file` を混在させることもできます（それぞれ同じ順番の `--when` に対応）。


## 一覧レスポンス（envelope + item）

全体の JSON（envelope）と、配列1件分の雛形（item）を分けて指定します。

```bash
cat > envelope.json << 'EOF'
{"status":"ok","total":"{LIST_COUNT}","results":[]}
EOF

cat > item.json << 'EOF'
{"id":"TEST_{INDEX:05}","name":"item-{INDEX:03}"}
EOF

rapi host /items get   -f envelope.json   --list-key results   --list-item-file item.json   --list-count 3

rapi start --port 8000
curl http://127.0.0.1:8000/items
```

返る例:

```json
{
  "status": "ok",
  "total": "3",
  "results": [
    {"id": "TEST_00001", "name": "item-001"},
    {"id": "TEST_00002", "name": "item-002"},
    {"id": "TEST_00003", "name": "item-003"}
  ]
}
```

| オプション | 意味 |
|-----------|------|
| `-f` / `-r` | envelope（全体）。`results` と同列のフィールドもここに書く |
| `--list-key` | 配列を埋めるフィールド（`results` や `data.items`） |
| `--list-item` / `--list-item-file` | 1件分の JSON 雛形 |
| `--list-count` | 件数 |
| `--list-start` | `{INDEX}` の開始値（デフォルト 1） |

| 記法 | 例（INDEX=1） |
|------|----------------|
| `{INDEX}` | `1` |
| `{INDEX:05}` | `00001` |
| `{LIST_COUNT}` | envelope 内の件数埋め込み |

## QUERY（RFC 10008）

```bash
rapi host /search query -r '{"results":[]}'
rapi start
```


## OpenAPI 形式の保存・読込

```bash
# OpenAPI 3 YAML として書き出し
rapi save openapi.yaml --format openapi
# x-rapi-* なし（標準 OpenAPI のみ）
rapi save openapi.yaml --format openapi --no-x-rapi

# 読み込み（拡張子 .yaml/.yml は自動判定）
rapi load openapi.yaml
rapi load openapi.yaml --format openapi --replace
```

- 標準の `paths` / `responses` / `example` を利用
- rapi 独自の条件・一覧などは `x-rapi-*` 拡張に保持（再読込で復元）
- OpenAPI 利用時は **PyYAML** が必要（`install.sh` または `pip install -r requirements.txt`）

## 定義の保存・読み込み

```bash
rapi save my-mocks.json
rapi save openapi.yaml --format openapi
# x-rapi-* なし（標準 OpenAPI のみ）
rapi save openapi.yaml --format openapi --no-x-rapi
rapi load my-mocks.json
rapi load openapi.yaml --format openapi
rapi load my-mocks.json --replace
```

## コマンド追加

`rapi/commands/` に Python ファイルを置くとサブコマンドとして自動登録されます。

```python
# rapi/commands/hello.py
def register(subparsers):
    p = subparsers.add_parser("hello", help="example")
    p.set_defaults(func=run)

def run(args):
    print("hello")
```

## 状態ファイル

| パス | 内容 |
|------|------|
| `~/.rapi/definitions.json` | 定義 |
| `~/.rapi/rapi.pid` | PID |
| `~/.rapi/rapi.port` | 起動中のポート |
| `~/.rapi/rapi.log` | ログ（起動時に pid / port を記録） |

## テスト

```bash
cd rapi-tool
pip install pytest pytest-cov
export PYTHONPATH=.
python3 -m pytest tests/ -q --cov=rapi --cov-report=term-missing
```

## ライセンス

MIT License（詳細は `LICENSE` を参照）
