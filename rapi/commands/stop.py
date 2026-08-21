"""rapi stop - stop background server."""

from __future__ import annotations

import argparse

from rapi.core.server import clear_stale_state, get_pid, get_port, stop_server


def register(subparsers: argparse._SubParsersAction) -> None:
    p = subparsers.add_parser(
        'stop',
        help='Stop mock server (optional --force SIGKILL)',
        description='Stop the background server for a group.\nWithout a recorded PID, does not kill by port; shows manual check commands.',
        epilog='examples:\n  rapi stop\n  rapi stop --group api-a --force\n',
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--group", default="default", help="Group to stop (default: default)")
    p.add_argument(
        "--force",
        action="store_true",
        help="Send SIGKILL immediately to the recorded PID (no graceful TERM wait)",
    )
    p.set_defaults(func=run)


def run(args: argparse.Namespace) -> None:
    group = getattr(args, "group", "default") or "default"
    force = bool(getattr(args, "force", False))
    pid = get_pid(group)
    port = get_port(group)

    if pid:
        if stop_server(group, force=force):
            how = "force-killed (SIGKILL)" if force else "stopped"
            print(f"Group '{group}' {how} (pid {pid})")
        else:
            print(f"Failed to stop group '{group}'.")
        return

    # No live PID — do not kill any process. Clean stale files and show manual checks.
    info = clear_stale_state(group)
    print(f"Group '{group}' has no running process recorded by rapi.")
    if info.get("cleared"):
        print("Cleared stale pid/port files (no process was signaled).")
    if port is not None:
        print(f"Last known port: {port}")
    print()
    print("If something is still listening, check manually (rapi will not kill by port):")
    if port is not None:
        print(f"  ss -ltnp | grep {port}")
        print(f"  lsof -i :{port}")
        print(f"  # then: kill <PID>   or   kill -9 <PID>")
    else:
        print("  ss -ltnp | grep 8000")
        print("  lsof -i :8000")
        print("  # then: kill <PID>   or   kill -9 <PID>")
