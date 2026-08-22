# rapi

A CLI for building **REST API mocks** for testing.

Define endpoints, methods, and responses (with conditional rules and placeholders)
using `rapi host`, then listen with `rapi start`.
Clients call it like a normal HTTP API (GET / POST / QUERY, etc.).

[日本語](README.md)

## Features

- Mock REST endpoints (path + method)
- JSON responses (from a string or a file)
- Query / body validation
- Conditional responses (e.g. return 400 only for a specific ID)
- Embed request values into responses (`{INPUT.body.id}`)
- Background start / stop / status
- Path parameters (`/users/{id}`)
- Per-group processes (`--group`)
- OpenAPI 3 load / save
- Connectivity check via `rapi call`

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
| `rapi host` | Register a REST definition (no port; `--group`, default `default`) |
| `rapi start` | Start the server (`--port` / `--group`; one process per group) |
| `rapi stop` | Stop (`--force` sends SIGKILL to the recorded PID) |
| `rapi restart` | Restart |
| `rapi status` | Running state and definitions (`-v` for detail) |
| `rapi call` | Request a running server (`--curl` prints an equivalent curl) |
| `rapi delete` | Delete a definition (stops the server if running) |
| `rapi save` | Export definitions to JSON or OpenAPI |
| `rapi load` | Import definitions from JSON or OpenAPI |

## Connectivity check (`call`)

Send a request from rapi to a running mock.

```bash
rapi start --port 8000

rapi call /slow get
rapi call /api post --body '{"id":"001"}'
rapi call /users/42 get -q 'verbose=1' --curl
```

| Option | Meaning |
|--------|---------|
| `--group` | Target group (port is taken from the running process) |
| `--port` / `--host` | Direct address (skips the running-process check if `--port` is set) |
| `-q` / `--query` | Query parameter (repeatable) |
| `-b` / `--body` / `--body-file` | Body |
| `-H` | Header |
| `--timeout` | Seconds (for delayed mocks) |
| `-v` | Show request details |
| `--curl` | After the call, print an equivalent curl command |

If the server is not running and `--port` is omitted, rapi exits with an error and suggests `rapi start` (it does not start automatically).

## Request log

When started in the background, requests are written to the group log.

```bash
tail -f ~/.rapi/groups/default/rapi.log
```

Example:

```text
[2026-08-19 21:00:00] REQ  GET /slow?x=1
         status=200  duration=1503ms  endpoint=GET:/slow
         query={'x': '1'}
```

| Field | Meaning |
|-------|---------|
| REQ | Method and path (including query) |
| status / duration | Status code and elapsed time (includes `--delay`) |
| endpoint | Matched definition name |
| path_params / query / body | Request data (long bodies are truncated) |

## Server status (`status`)

```bash
rapi status
rapi status --group default
rapi status -v                 # params / response bodies, etc.
```

- **Server** — running / pid / listen / log per group
- **Store** — definition file path and counts
- **Definitions** — method / path / status / delay / rules / query

## Stopping the server

```bash
rapi stop --group default
rapi stop --group default --force   # SIGKILL the recorded PID immediately
```

If no live PID is recorded, **no process is killed**. Stale pid/port files are removed and check commands are printed:

```bash
ss -ltnp | grep 8000
lsof -i :8000
# kill <PID>   or   kill -9 <PID>
```

rapi never kills an unknown process by port number alone.

## Groups (`--group`)

Split definitions and processes by name. Omitted group is `default`.

```bash
rapi host /a get -r '{"ok":true}' --group api-a
rapi host /b get -r '{"ok":true}' --group api-b

rapi start --group api-a --port 8001
rapi start --group api-b --port 8002

rapi status
rapi stop --group api-a
```

State files live under `~/.rapi/groups/<group>/` (pid / port / log).

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

On start, PID and port are written to `~/.rapi/groups/<group>/rapi.log`.

## Path parameters

Define paths with `{name}` templates.

```bash
rapi host '/users/{id}' get -r '{"id":"{INPUT.path.id}"}'
rapi start --port 8000
curl http://127.0.0.1:8000/users/42
# → {"id":"42"}
```

| Syntax | Meaning |
|--------|---------|
| `{INPUT.path}` | Full request path (`/users/42`) |
| `{INPUT.path.id}` | Path parameter `id` |
| `--when 'path.id=000'` | Usable in conditions too |

## Delayed responses (timeout testing)

```bash
rapi host /slow get -r '{"ok":true}' --delay 1500
rapi host /api post -r '{"ok":true}' \
  --when 'body.id=timeout' --rule-status 200 --rule-response '{"ok":true}' --rule-delay 3000
```

| Option | Meaning |
|--------|---------|
| `--delay MS` | Delay default response (milliseconds) |
| `--rule-delay MS` | Delay for the matching `--when` (paired by order) |

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

- Uses standard `paths` / `responses` / `example` / `examples`
- `parameters` (path-level + operation; query params become rapi required query checks)
- Local `$ref` under `#/components/...` (schema / parameter / requestBody)
- Builds a simple example from `schema` when no example is present
- `requestBody.required` + example → `expected_body` (body validation)
- Extra `responses` statuses → rules with `query.force=<status>`

When OpenAPI `responses` include statuses other than 200, load attaches **rapi convention** rules:

| responses | when |
|-----------|------|
| `"400"` | `query.force=400` |
| `"404"` | `query.force=404` |
| other | `query.force=<status>` |

```bash
rapi load examples/sample-openapi.yaml --replace
rapi start --port 8000
rapi call '/items/1' get -q verbose=1              # 200
rapi call '/items/1' get -q verbose=1 -q force=404 # 404 example
```

`force` is added even if the YAML does not declare that query parameter (for mock testing).

- rapi-specific rules / lists are stored in `x-rapi-*` and restored on reload
- OpenAPI support needs **PyYAML** (`install.sh` or `pip install -r requirements.txt`)

Sample files: `examples/sample-openapi.yaml` and `examples/sample-openapi.json`.

## Save / load definitions

```bash
rapi save my-mocks.json
rapi save openapi.yaml --format openapi
rapi save openapi.yaml --format openapi --no-x-rapi
rapi load my-mocks.json
rapi load openapi.yaml --format openapi
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
| `~/.rapi/groups/<group>/rapi.pid` | PID |
| `~/.rapi/groups/<group>/rapi.port` | Listening port |
| `~/.rapi/groups/<group>/rapi.log` | Log (records pid / port on start) |

## Tests

```bash
cd rapi-tool
pip install pytest pytest-cov
export PYTHONPATH=.
python3 -m pytest tests/ -q --cov=rapi --cov-report=term-missing
```

## License

MIT License (see `LICENSE`)
