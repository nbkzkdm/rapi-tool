# rapi

A CLI for building **REST API mocks** for testing.

Define endpoints, methods, and responses (with conditional rules and placeholders)
using `rapi host`, then listen with `rapi start`.
Clients call it like a normal HTTP API (GET / POST / QUERY, etc.).

[日本語](README.md)


> **Direction**  
> For now, the primary path is the CLI (`host` → `start`) so you can spin up local test mocks quickly.  
> Future work will gradually make **OpenAPI a first-class input path** as well (starting with examples and basic path/method/parameters).  
> rapi-specific features (conditional rules, list generation, etc.) remain available via CLI options and `x-rapi-*` extensions — a two-layer model.

## Features

- Mock REST endpoints (path + method)
- JSON responses (from a string or a file)
- Query / body validation
- Conditional responses (e.g. return 400 only for a specific ID)
- Embed request values into responses (`{INPUT.body.id}`)
- Background start / stop / status

## Install

```bash
unzip rapi-tool.zip
cd rapi-tool
sh install.sh
# installs to ~/.local/bin/rapi by default
# also runs pip install -r requirements.txt when possible (PyYAML for OpenAPI)

# install runtime deps only
pip install -r requirements.txt

# ensure PATH includes it if needed
export PATH="$HOME/.local/bin:$PATH"
```

Install elsewhere:

```bash
sh install.sh /usr/local/bin    # may require privileges
# or
sh install.sh ~/bin
```

After install, use it **without** a `python` prefix:

```bash
rapi --help
rapi host /sample get -r '{"ok":true}'
rapi start
rapi status
rapi stop
```

## Subcommands

| Command | Description |
|---------|-------------|
| `rapi host` | Register a REST definition (no port here) |
| `rapi start` | Start the server (`--port`, default 8000) |
| `rapi stop` | Stop the server |
| `rapi restart` | Restart the server |
| `rapi status` | Show running state and definitions |
| `rapi delete` | Delete a definition (stops server if running) |
| `rapi save` | Export definitions to JSON |
| `rapi load` | Import definitions from JSON |

## Basic flow

```bash
# define (no port at this step)
rapi host /sample get -r '{"ok":true,"q":"{INPUT.query.id}"}'

rapi host /sample post \
  -r '{"ok":true,"id":"{INPUT.body.id}"}' \
  --when 'body.id=004' \
  --rule-status 400 \
  --rule-response '{"error":"invalid id","received":"{INPUT.body.id}"}'

# start (port is specified here)
rapi start --port 8000

# call
curl 'http://127.0.0.1:8000/sample?id=123'
curl -X POST -d '{"id":"004"}' http://127.0.0.1:8000/sample

rapi status
rapi stop
```

On start, PID and port are written to `~/.rapi/rapi.log`.


## Path + query examples

### List (query)

```bash
rapi host /items get \
  --param 'limit=~^\d+$' \
  --param offset \
  -r '{"limit":"{INPUT.query.limit}","offset":"{INPUT.query.offset}"}'

rapi start --port 8000
curl 'http://127.0.0.1:8000/items?limit=10&offset=0'
```

### Detail (path parameter)

```bash
rapi host '/items/{id}' get \
  -r '{"id":"{INPUT.path.id}"}'

curl http://127.0.0.1:8000/items/42
```

### Path + query

```bash
rapi host '/users/{userId}/orders' get \
  --param 'status=open' \
  -r '{"userId":"{INPUT.path.userId}","status":"{INPUT.query.status}"}'

curl 'http://127.0.0.1:8000/users/u1/orders?status=open'
```

### Path condition → error branch

```bash
rapi host '/users/{id}' get \
  -r '{"id":"{INPUT.path.id}","ok":true}' \
  --when 'path.id=000' \
  --rule-status 404 \
  --rule-response '{"error":"not found","id":"{INPUT.path.id}"}'
```

### Multiple query params + strict

```bash
rapi host /search get \
  --param q \
  --param 'page=~^\d+$' \
  --strict \
  -r '{"q":"{INPUT.query.q}","page":"{INPUT.query.page}"}'
```

## Placeholders

| Syntax | Meaning |
|--------|---------|
| `{INPUT.method}` | HTTP method |
| `{INPUT.path}` | Path |
| `{INPUT.query.aaa}` | Query parameter |
| `{INPUT.body}` | Full body |
| `{INPUT.body.id}` | JSON field `id` |
| `{INPUT.header.X-Request-Id}` | Request header |

`"Test{INPUT.body.id}"` + id=004 → `"Test004"`

## Conditional responses

- `--when` rules are evaluated top to bottom; **first match wins**
- Conditions inside one `--when` are **AND** (comma-separated)
- If no rule matches, the default response is used

### `=` vs `=~`

| Form | Meaning |
|------|---------|
| `body.id=004` | **Exact match** (value is exactly `004`) |
| `body.id=~^9` | **Regex** (text after `~` is a regular expression) |

`~` is not part of the request value; it switches rapi into regex mode.

| Example | Matches |
|---------|---------|
| `body.id=004` | only `"004"` |
| `body.id=~^9` | values starting with 9, e.g. `"9"`, `"999"`, `"90"` |
| `body.id=~^\d{3}$` | exactly 3 digits |

Prefer **single quotes** around `--when` values so the shell does not treat `^` specially.

### Definition example

```bash
rapi host /api/item post \
  -r '{"ok":true,"id":"{INPUT.body.id}"}' \
  --when 'body.id=004' --rule-status 400 \
  --rule-response '{"error":"bad id","received":"{INPUT.body.id}"}' \
  --when 'body.id=~^9' --rule-status 503 \
  --rule-response '{"error":"unavailable"}'

rapi start --port 8000
```

### Conditional sample: normal (200)

```bash
curl -X POST -d '{"id":"001"}' http://127.0.0.1:8000/api/item
```

### Conditional sample: id=004 → 400

```bash
curl -X POST -d '{"id":"004"}' http://127.0.0.1:8000/api/item
```

### Conditional sample: id starts with 9 → 503

```bash
curl -X POST -d '{"id":"999"}' http://127.0.0.1:8000/api/item
```

## Request body validation (`--body` / `--body-file`)

Checks that the incoming request body matches expectations. On mismatch, returns **400**.

| Option | Meaning |
|--------|---------|
| `-b` / `--body` | Expected body as a string |
| `--body-file` | Expected body loaded from a file |

- If the value/file starts with `~` → **regex** (partial match)
- Otherwise → **equality**
  - Leading/trailing whitespace and trailing newlines are ignored
  - If both sides parse as JSON, compare parsed values (key order / spacing ignored)

### Sample: exact match (file)

Returns 200 only when the body matches `expected.json`:

```bash
cat > expected.json << 'EOF'
{"name":"taro","age":30}
EOF

rapi host /users post \
  -r '{"ok":true}' \
  --body-file expected.json

rapi start --port 8000

# OK
curl -X POST -H 'Content-Type: application/json' \
  -d '{"name":"taro","age":30}' \
  http://127.0.0.1:8000/users

# NG (400)
curl -X POST -H 'Content-Type: application/json' \
  -d '{"name":"jiro"}' \
  http://127.0.0.1:8000/users
```

### Sample: regex (file)

Leading `~` enables regex mode:

```bash
cat > expected_re.txt << 'EOF'
~"name"\s*:\s*".+"
EOF

rapi host /users post \
  -r '{"ok":true}' \
  --body-file expected_re.txt
```

### Sample: on the command line

```bash
# exact match
rapi host /users post -r '{"ok":true}' --body '{"name":"taro"}'

# regex (body contains a "name" key)
rapi host /users post -r '{"ok":true}' --body '~"name"'
```

### Response body from a file (note)

For the **response** body, use `-f` / `--response-file` (not `--body-file`):

```bash
cat > response.json << 'EOF'
{"ok":true,"id":"{INPUT.body.id}"}
EOF

rapi host /users post -f response.json
```

## Conditional response bodies from files (`--rule-response-file`)

Load rule (error / branch) response bodies from files instead of inline strings.

| Option | Meaning |
|--------|---------|
| `--rule-response` | Rule response body as a string |
| `--rule-response-file` | Same, from a file |
| `--rule-status` | HTTP status for that rule |

`--when` / `--rule-status` / `--rule-response` (or `--rule-response-file`) are paired **in order**.

### Sample

```bash
# default response
cat > ok.json << 'EOF'
{"ok":true,"id":"{INPUT.body.id}"}
EOF

# when id=004
cat > err004.json << 'EOF'
{"error":"bad id","received":"{INPUT.body.id}"}
EOF

# when id starts with 9
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

### Conditional sample: normal (200)

```bash
curl -X POST -d '{"id":"001"}' http://127.0.0.1:8000/api/item
```

### Conditional sample: id=004 → 400

```bash
curl -X POST -d '{"id":"004"}' http://127.0.0.1:8000/api/item
```

### Conditional sample: id starts with 9 → 503

```bash
curl -X POST -d '{"id":"999"}' http://127.0.0.1:8000/api/item
```

You can mix `--rule-response` and `--rule-response-file` (each pairs with the `--when` at the same index).


## List responses (envelope + item)

```bash
rapi host /items get \
  -f envelope.json \
  --list-key results \
  --list-item-file item.json \
  --list-count 3
```

- `{INDEX}` / `{INDEX:05}` — zero-padded index in the item template
- `{LIST_COUNT}` — count inside the envelope
- `--list-start` — starting index (default 1)

## QUERY (RFC 10008)

```bash
rapi host /search query -r '{"results":[]}'
rapi start
```


## OpenAPI save / load

```bash
rapi save openapi.yaml --format openapi
# standard OpenAPI only (no x-rapi-*)
rapi save openapi.yaml --format openapi --no-x-rapi
rapi load openapi.yaml
rapi load openapi.yaml --format openapi --replace
```

- Uses standard `paths` / `responses` / `example`
- rapi-specific rules/lists are kept in `x-rapi-*` extensions
- Requires **PyYAML** (`install.sh` or `pip install -r requirements.txt`)

## Save / load definitions

```bash
rapi save my-mocks.json
rapi load my-mocks.json
rapi load my-mocks.json --replace
```

## Adding commands

Drop a Python file under `rapi/commands/` to register a new subcommand automatically.

```python
# rapi/commands/hello.py
def register(subparsers):
    p = subparsers.add_parser("hello", help="example")
    p.set_defaults(func=run)

def run(args):
    print("hello")
```

## State files

| Path | Contents |
|------|----------|
| `~/.rapi/definitions.json` | Definitions |
| `~/.rapi/rapi.pid` | PID |
| `~/.rapi/rapi.port` | Listening port |
| `~/.rapi/rapi.log` | Log (records pid / port on start) |

## Tests

```bash
cd rapi-tool
pip install pytest pytest-cov
export PYTHONPATH=.
python3 -m pytest tests/ -q --cov=rapi --cov-report=term-missing
```

## License

MIT License (see `LICENSE`)
