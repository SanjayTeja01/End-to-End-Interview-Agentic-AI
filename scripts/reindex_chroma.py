#!/usr/bin/env python
"""Rebuild the ChromaDB vector index from PostgreSQL metadata + MinIO source documents.

ChromaDB is a derived, disposable index: deleting it loses no application data. Run:

    docker compose exec backend python /app/scripts/reindex_chroma.py --reset
    docker compose exec backend python /app/scripts/reindex_chroma.py --institute <uuid>
    docker compose exec backend python /app/scripts/reindex_chroma.py --only-stale   # after changing EMBEDDING_MODEL/VERSION
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys
import uuid

ROOT = pathlib.Path(__file__).resolve().parents[1]
for candidate in (ROOT / "backend", pathlib.Path("/app")):
    if (candidate / "app").exists():
        sys.path.insert(0, str(candidate))
        break


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--reset", action="store_true", help="Drop the whole collection before rebuilding")
    p.add_argument("--institute", type=uuid.UUID, help="Rebuild only one institution's documents")
    p.add_argument("--only-stale", action="store_true", help="Re-embed only versions built with a different embedding model/version")
    args = p.parse_args()

    from app.core.config import get_settings
    from app.core.database import SessionLocal
    from app.core.logging import configure_logging
    from rag.reindexing.reindex import reindex_all

    configure_logging(get_settings().log_level)
    db = SessionLocal()
    try:
        summary = reindex_all(db, institute_id=args.institute, reset=args.reset or bool(args.institute),
                              only_stale=args.only_stale)
    finally:
        db.close()
    print(json.dumps(summary, indent=2))
    return 0 if summary["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
