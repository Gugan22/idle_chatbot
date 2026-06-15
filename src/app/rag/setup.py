"""
src/app/rag/setup.py
─────────────────────────────────────────────────────────────────────────────
One-time Qdrant collection setup.
Fixed for qdrant-client >= 1.9:
  ef_construction → ef_construct  (renamed in the Pydantic model)

Safe to re-run — skips if collection already exists.

Usage:
    poetry run python src/app/rag/setup.py
    poetry run python src/app/rag/setup.py --recreate   # DELETES ALL DATA
"""

import sys
import argparse
from pathlib import Path

# ── Ensure src/ is on sys.path ────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parents[3]
SRC  = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from app.config import settings

from qdrant_client import QdrantClient
from qdrant_client.models import (
    VectorParams,
    Distance,
    HnswConfigDiff,
    BinaryQuantization,
    BinaryQuantizationConfig,
    PayloadSchemaType,
    OptimizersConfigDiff,
)


def create_collection(client: QdrantClient, recreate: bool = False) -> None:
    existing = [c.name for c in client.get_collections().collections]

    if settings.collection_name in existing:
        if recreate:
            print(f"[setup] Dropping collection '{settings.collection_name}'...")
            client.delete_collection(settings.collection_name)
            print("[setup] Dropped.")
        else:
            print(f"[setup] Collection '{settings.collection_name}' already exists. Skipping.")
            print("[setup] Use --recreate to drop and recreate (DELETES ALL DATA).")
            return

    print(f"[setup] Creating collection '{settings.collection_name}'...")
    print(f"        embed_dim = {settings.embed_dim}")
    print(f"        distance  = COSINE")
    print(f"        quantize  = Binary")

    client.create_collection(
        collection_name=settings.collection_name,
        vectors_config=VectorParams(
            size=settings.embed_dim,
            distance=Distance.COSINE,
            on_disk=True,
        ),
        hnsw_config=HnswConfigDiff(
            m=16,
            ef_construct=128,    # was ef_construction in qdrant-client < 1.9
            on_disk=False,
        ),
        quantization_config=BinaryQuantization(
            binary=BinaryQuantizationConfig(
                always_ram=True,
            )
        ),
        optimizers_config=OptimizersConfigDiff(
            memmap_threshold=50000,
        ),
    )
    print("[setup] Collection created.")

    # ── Payload indexes ────────────────────────────────────────────────────────
    payload_indexes = [
        ("doc_type",      PayloadSchemaType.KEYWORD),
        ("coverage_type", PayloadSchemaType.KEYWORD),
        ("region",        PayloadSchemaType.KEYWORD),
        ("policy_id",     PayloadSchemaType.KEYWORD),
        ("language",      PayloadSchemaType.KEYWORD),
        ("tags",          PayloadSchemaType.KEYWORD),
        ("version",       PayloadSchemaType.FLOAT),
    ]

    print("[setup] Creating payload indexes...")
    for field_name, schema_type in payload_indexes:
        client.create_payload_index(
            collection_name=settings.collection_name,
            field_name=field_name,
            field_schema=schema_type,
        )
        print(f"        + {field_name}")

    print("[setup] Setup complete.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Set up Qdrant collection.")
    parser.add_argument(
        "--recreate",
        action="store_true",
        help="Drop and recreate the collection. WARNING: deletes all data.",
    )
    args = parser.parse_args()

    if args.recreate:
        confirm = input(
            f"[setup] WARNING: Deletes ALL DATA in '{settings.collection_name}'.\n"
            "        Type 'yes' to confirm: "
        )
        if confirm.strip().lower() != "yes":
            print("[setup] Aborted.")
            sys.exit(0)

    client = QdrantClient(host=settings.qdrant_host, port=settings.qdrant_port)

    try:
        client.get_collections()
        print(f"[setup] Connected to Qdrant at {settings.qdrant_host}:{settings.qdrant_port}")
    except Exception as e:
        print(f"[setup] ERROR: Cannot connect to Qdrant — {e}")
        print("        Is Qdrant running? Try: scripts/podman-stack.sh infra")
        sys.exit(1)

    create_collection(client, recreate=args.recreate)


if __name__ == "__main__":
    main()
