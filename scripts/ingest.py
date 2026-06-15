"""Parse policy Markdown documents and load them into Qdrant."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from app.config import settings
from app.rag.ingestion.parser import parse_folder
from app.rag.ingestion.qdrant_writer import upsert_chunks


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--folder",
        type=Path,
        default=settings.docs_dir,
        help="Folder containing Markdown policy documents",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Parse and validate documents without writing to Qdrant",
    )
    args = parser.parse_args()

    folder = args.folder.expanduser()
    if not folder.is_absolute():
        folder = ROOT / folder
    folder = folder.resolve()
    if not folder.exists():
        parser.error(f"Document folder does not exist: {folder}")

    chunks = parse_folder(folder)
    accepted = upsert_chunks(chunks, dry_run=args.dry_run)
    action = "validated" if args.dry_run else "upserted"
    print(f"[ingest] {action} {accepted} chunks from {folder}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
