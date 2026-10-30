"""Command line: ``python -m mosaic_api {harvest,export,serve,openapi}``."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

from . import bootstrap
from .adapters.inbound.http import create_app
from .config import load_settings


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="mosaic_api")
    ap.add_argument("--config", type=Path, help="config file (default config/mosaic-api.yaml or $MOSAIC_API_CONFIG)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("harvest", help="read every source and update the snapshot")
    ex = sub.add_parser("export", help="write the static API (for GitHub Pages)")
    ex.add_argument("--out", type=Path)
    sv = sub.add_parser("serve", help="run the live API (development or a server)")
    sv.add_argument("--host", default="127.0.0.1")
    sv.add_argument("--port", type=int, default=8000)
    op = sub.add_parser("openapi", help="print the OpenAPI contract")
    op.add_argument("--out", type=Path)
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    for noisy in ("httpx", "httpx2", "httpcore"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    settings = load_settings(args.config)

    if args.cmd == "harvest":
        report = bootstrap.harvest_service(settings).run()
        for s in report.snapshot.sources:
            state = f"ERROR {s.error} (kept {s.records} previous records)" if s.error else f"{s.records} records"
            done = f", {report.translated.get(s.id, 0)} translated, {report.reused.get(s.id, 0)} unchanged"
            print(f"{s.id}: {state}{'' if s.error else done}; {len(s.issues)} with issues")
        return 1 if all(s.error for s in report.snapshot.sources) else 0

    catalog = bootstrap.catalog_service(settings)
    app = create_app(catalog, settings.http.cors_origins, settings.http.max_page_size)
    if args.cmd == "export":
        from .adapters.inbound.exporter import export

        out = args.out or Path(settings.resolve(settings.export_dir))
        manifest = export(app, catalog, out)
        print(f"Static API: {manifest['counts']['resources']} resources -> {out}")
        return 0
    if args.cmd == "openapi":
        text = json.dumps(app.openapi(), indent=1, ensure_ascii=False)
        if args.out:
            args.out.write_text(text + "\n", encoding="utf-8")
        else:
            print(text)
        return 0
    import uvicorn

    uvicorn.run(app, host=args.host, port=args.port)
    return 0


if __name__ == "__main__":
    sys.exit(main())
