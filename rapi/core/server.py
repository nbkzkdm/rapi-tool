from __future__ import annotations

import json
import os
import signal
import sys
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from .matching import match_body_pattern, match_conditions, match_value
from .models import Endpoint, ResponseSpec
from .placeholders import apply_placeholders, build_input_context
from .listgen import expand_list_in_body
from .store import DefinitionStore, default_store_path


def state_dir() -> Path:
    d = Path.home() / ".rapi"
    d.mkdir(parents=True, exist_ok=True)
    return d


def pid_file() -> Path:
    return state_dir() / "rapi.pid"


def port_file() -> Path:
    return state_dir() / "rapi.port"


def log_file() -> Path:
    return state_dir() / "rapi.log"


def get_pid() -> int | None:
    pf = pid_file()
    if not pf.is_file():
        return None
    try:
        pid = int(pf.read_text().strip())
    except ValueError:
        return None
    try:
        os.kill(pid, 0)
        return pid
    except OSError:
        pf.unlink(missing_ok=True)
        return None


def is_running() -> bool:
    return get_pid() is not None


def get_port() -> int | None:
    pf = port_file()
    if not pf.is_file():
        return None
    try:
        return int(pf.read_text().strip())
    except ValueError:
        return None


def stop_server(timeout: float = 2.0) -> bool:
    pid = get_pid()
    if not pid:
        return False
    try:
        os.kill(pid, signal.SIGTERM)
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                os.kill(pid, 0)
                time.sleep(0.1)
            except OSError:  # pragma: no cover
                break
        else:
            try:
                os.kill(pid, signal.SIGKILL)
            except OSError:  # pragma: no cover
                pass
    except OSError:  # pragma: no cover
        pass
    pid_file().unlink(missing_ok=True)
    port_file().unlink(missing_ok=True)
    return True


def looks_like_json(text: str) -> bool:
    s = text.strip()
    if not ((s.startswith("{") and s.endswith("}")) or (s.startswith("[") and s.endswith("]"))):
        return False
    try:
        json.loads(s)
        return True
    except json.JSONDecodeError:
        return False


class MockHandler(BaseHTTPRequestHandler):
    endpoints: list[Endpoint] = []

    def log_message(self, format: str, *args: Any) -> None:
        pass

    def _find(self) -> Endpoint | None:
        req_path = urlparse(self.path).path
        method = self.command.upper()
        for ep in self.endpoints:
            if ep.path == req_path and ep.method == method:
                return ep
        return None

    def _send(self, status: int, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        if self.command.upper() != "HEAD" and body:
            self.wfile.write(body)

    def _log_error(
        self,
        status: int,
        reason: str,
        *,
        query: dict[str, list[str]] | None = None,
        body_text: str | None = "",
        extra: dict[str, Any] | None = None,
    ) -> None:
        """Log error cause and related request data (goes to rapi.log when background)."""
        print(f"← {status} ERROR: {reason}")
        print(f"  request: {self.command} {self.path}")
        if query:
            qflat = {k: (v[0] if v else "") for k, v in query.items()}
            print(f"  query: {qflat}")
        if body_text is None:
            print("  body: <binary>")
        elif body_text != "":
            # truncate very long bodies in log
            shown = body_text if len(body_text) <= 2000 else body_text[:2000] + "...(truncated)"
            print(f"  body: {shown}")
        if extra:
            for k, v in extra.items():
                print(f"  {k}: {v}")
        try:
            sys.stdout.flush()
        except Exception:  # pragma: no cover
            pass

    def handle_request(self) -> None:
        content_length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(content_length) if content_length else b""

        print(f"→ {self.command} {self.path}")
        body_text: str | None
        try:
            body_text = raw.decode("utf-8") if raw else ""
            if body_text:
                print(f"  body: {body_text}")
        except UnicodeDecodeError:
            print(f"  body: <binary {len(raw)} bytes>")
            body_text = None

        ep = self._find()
        if ep is None:
            self._log_error(
                404,
                "no matching endpoint",
                query=parse_qs(urlparse(self.path).query, keep_blank_values=True),
                body_text=body_text,
                extra={"registered": [f"{e.method} {e.path}" for e in self.endpoints]},
            )
            self._send(404, b"Not Found", "text/plain; charset=utf-8")
            return

        parsed = urlparse(self.path)
        query = parse_qs(parsed.query, keep_blank_values=True)
        headers = {k: v for k, v in self.headers.items()}

        # required query params validation
        for key, expected in ep.params.items():
            if key not in query:
                msg = f"Missing required query param: {key}"
                self._log_error(
                    400, msg, query=query, body_text=body_text,
                    extra={"expected_param": key, "expected_value": expected},
                )
                self._send(400, msg.encode("utf-8"), "text/plain; charset=utf-8")
                return
            actual = query[key][0] if query[key] else ""
            if expected is not None and not match_value(actual, expected):
                msg = f"Invalid value for '{key}': expected '{expected}', got '{actual}'"
                self._log_error(
                    400, msg, query=query, body_text=body_text,
                    extra={"param": key, "expected": expected, "actual": actual},
                )
                self._send(400, msg.encode("utf-8"), "text/plain; charset=utf-8")
                return
        if ep.strict_params:
            extras = set(query.keys()) - set(ep.params.keys())
            if extras:
                msg = f"Unexpected query params: {', '.join(sorted(extras))}"
                self._log_error(
                    400, msg, query=query, body_text=body_text,
                    extra={"allowed_params": list(ep.params.keys()), "extra_params": sorted(extras)},
                )
                self._send(400, msg.encode("utf-8"), "text/plain; charset=utf-8")
                return

        # expected body validation
        if ep.expected_body is not None:
            if body_text is None:
                self._log_error(
                    400, "binary body cannot be validated",
                    query=query, body_text=None,
                    extra={"expected_body": ep.expected_body},
                )
                self._send(400, b"Binary body cannot be validated", "text/plain; charset=utf-8")
                return
            if not match_body_pattern(body_text, ep.expected_body):
                self._log_error(
                    400, "request body does not match expected",
                    query=query, body_text=body_text,
                    extra={"expected_body": ep.expected_body},
                )
                self._send(400, b"Request body does not match expected", "text/plain; charset=utf-8")
                return

        # select response: rules first (order), then default
        chosen: ResponseSpec = ep.default
        matched_rule = None
        for rule in ep.rules:
            if match_conditions(
                rule.conditions,
                method=self.command.upper(),
                path=parsed.path,
                query=query,
                headers=headers,
                body_text=body_text,
            ):
                chosen = rule.response
                matched_rule = rule
                break

        if chosen.status >= 400:
            self._log_error(
                chosen.status,
                "rule matched" if matched_rule else "default error response",
                query=query,
                body_text=body_text,
                extra={
                    **({"rule_when": matched_rule.conditions} if matched_rule else {}),
                    "response_body": chosen.body[:500] if len(chosen.body) > 500 else chosen.body,
                },
            )

        ctx = build_input_context(
            method=self.command.upper(),
            path=parsed.path,
            query=query,
            headers=headers,
            body_text=body_text,
        )
        # list expansion applies to default response only (rules keep explicit bodies)
        body_src = chosen.body
        if matched_rule is None and ep.list_key:
            body_src = expand_list_in_body(
                body_src,
                list_key=ep.list_key,
                list_item=ep.list_item,
                list_count=ep.list_count,
                list_start=ep.list_start,
            )
        body_out = apply_placeholders(body_src, ctx)

        ct = chosen.content_type
        if ct is None:
            ct = "application/json" if looks_like_json(body_out) else "text/plain; charset=utf-8"

        print(f"← {chosen.status}")
        self._send(chosen.status, body_out.encode("utf-8"), ct)

    def do_GET(self) -> None:
        self.handle_request()

    def do_POST(self) -> None:
        self.handle_request()

    def do_PUT(self) -> None:
        self.handle_request()

    def do_DELETE(self) -> None:
        self.handle_request()

    def do_PATCH(self) -> None:
        self.handle_request()

    def do_HEAD(self) -> None:
        self.handle_request()

    def do_OPTIONS(self) -> None:
        self.handle_request()

    def do_QUERY(self) -> None:
        """RFC 10008 HTTP QUERY method."""
        self.handle_request()


def run_server(host: str = "127.0.0.1", port: int = 8000, background: bool = True) -> None:
    store = DefinitionStore()
    endpoints = store.list()
    if not endpoints:
        print("No endpoints defined. Use 'rapi host ...' first.", file=sys.stderr)
        sys.exit(1)

    if background:
        if is_running():
            print("Already running. Use 'rapi stop' or 'rapi restart'.", file=sys.stderr)
            sys.exit(1)

        pid = os.fork()
        if pid > 0:
            # parent: record pid/port and notify user
            pid_file().write_text(str(pid))
            port_file().write_text(str(port))
            # also append startup line to log from parent (reliable even if child is slow)
            ts = time.strftime("%Y-%m-%d %H:%M:%S")
            with open(log_file(), "a", encoding="utf-8") as lf:
                lf.write(f"[{ts}] started pid={pid} host={host} port={port}\n")
                lf.flush()
            print(f"Started (pid {pid})")
            print(f"  listen : http://{host}:{port}")
            for ep in endpoints:
                print(f"  - {ep.method} {ep.path}  ({len(ep.rules)} rules)")
            return

        # child
        try:
            os.setsid()
        except Exception:  # pragma: no cover
            pass
        sys.stdin.close()
        log = open(log_file(), "a", encoding="utf-8")
        sys.stdout = log  # type: ignore
        sys.stderr = log  # type: ignore
        # child also logs with its own pid confirmation
        print(
            f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] "
            f"worker pid={os.getpid()} listening on {host}:{port} "
            f"endpoints={len(endpoints)}"
        )
        sys.stdout.flush()

    MockHandler.endpoints = endpoints
    server = HTTPServer((host, port), MockHandler)
    if not background:
        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] server on {host}:{port}  endpoints={len(endpoints)}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        if not background:
            print("\nStopped.")
    finally:
        server.server_close()
        if background:  # pragma: no cover - child process exit path
            pid_file().unlink(missing_ok=True)
            port_file().unlink(missing_ok=True)
