from __future__ import annotations

import argparse
from pathlib import Path

from .config import load_config
from .db import setup_database
from .routes import create_app


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="wechat_feedback_app")
    subparsers = parser.add_subparsers(dest="command", required=True)

    serve_parser = subparsers.add_parser("serve")
    serve_parser.add_argument("--config", default="config/app.example.yaml")

    init_parser = subparsers.add_parser("init-db")
    init_parser.add_argument("--config", default="config/app.example.yaml")

    args = parser.parse_args(argv)
    config = load_config(Path(args.config), root=Path.cwd())

    if args.command == "init-db":
        setup_database(config)
        return

    if args.command == "serve":
        import uvicorn

        app = create_app(config)
        uvicorn.run(app, host=config.app.host, port=config.app.port)


if __name__ == "__main__":
    main()
