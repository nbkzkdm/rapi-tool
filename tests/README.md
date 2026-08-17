# Tests overview

Run:

```bash
export PYTHONPATH=.
python3 -m pytest tests/ -q --cov=rapi --cov-report=term-missing
```

## Files (what they cover)

| File | Focus |
|------|--------|
| `test_matching.py` | Query/body/header matching, regex (`~`), AND rules |
| `test_placeholders.py` | `{INPUT.xxx}` substitution |
| `test_listgen.py` | List envelope + `{INDEX:05}` generation |
| `test_models.py` | Endpoint/Rule serialize roundtrip (incl. group, list) |
| `test_store.py` | Definition store upsert/delete/import, **group isolation** |
| `test_server_handler.py` | Real HTTP GET/POST/QUERY, validation, rules |
| `test_server_process.py` | PID/port files, start/stop process helpers |
| `test_commands.py` | CLI: host/save/load/status/stop/delete, **--group** |
| `test_openapi.py` | OpenAPI export/import, `--no-x-rapi`, format detect |
| `test_coverage_gaps.py` | Edge cases (binary body, errors, main exceptions) |

## Tips

```bash
# list test names only
python3 -m pytest tests/ --collect-only -q

# one file
python3 -m pytest tests/test_openapi.py -v

# name match
python3 -m pytest tests/ -k group -v
```
