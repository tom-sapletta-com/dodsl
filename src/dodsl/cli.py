from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

from .errors import DoDslError
from .model import ProjectRequest
from .server import serve
from .service import DoDslService


def _print(value: Any) -> None:
    print(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2))


def _request(path: str) -> ProjectRequest:
    return ProjectRequest.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="dodsl")
    parser.add_argument("--projects-root", default=os.getenv("DODSL_PROJECTS_ROOT", "projects"))
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("init", "run"):
        command = commands.add_parser(name)
        command.add_argument("request")
        if name == "run":
            command.add_argument("--require-todo2code", action="store_true")
            command.add_argument("--no-reconcile", action="store_true")
    for name in ("ingest", "status", "reconcile"):
        command = commands.add_parser(name)
        command.add_argument("project_id")
    compile_command = commands.add_parser("compile")
    compile_command.add_argument("project_id")
    compile_command.add_argument("--require-todo2code", action="store_true")
    upload = commands.add_parser("import-file")
    upload.add_argument("project_id")
    upload.add_argument("path")
    upload.add_argument("--trust-role", default="customer")
    server = commands.add_parser("serve")
    server.add_argument("--host", default=os.getenv("DODSL_HOST", "127.0.0.1"))
    server.add_argument("--port", type=int, default=int(os.getenv("DODSL_PORT", "8788")))
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "serve":
            serve(args.projects_root, args.host, args.port)
            return 0
        dodsl = DoDslService(args.projects_root)
        if args.command == "init":
            _print(dodsl.create(_request(args.request)))
        elif args.command == "run":
            _print(dodsl.run(_request(args.request), require_todo2code=args.require_todo2code, reconcile=not args.no_reconcile))
        elif args.command == "ingest":
            _print(dodsl.ingest(args.project_id))
        elif args.command == "compile":
            _print(dodsl.compile(args.project_id, require_todo2code=args.require_todo2code))
        elif args.command == "reconcile":
            _print(dodsl.reconcile(args.project_id))
        elif args.command == "status":
            _print(dodsl.status(args.project_id))
        elif args.command == "import-file":
            _print(dodsl.import_file(args.project_id, args.path, trust_role=args.trust_role))
        return 0
    except (DoDslError, OSError, json.JSONDecodeError) as exc:
        _print({"error": type(exc).__name__, "message": str(exc)})
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
