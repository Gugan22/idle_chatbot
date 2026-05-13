"""
setup_collection.py
────────────────────────────────────────────────────────────────────────────
One-time setup script. Creates the Qdrant collection, configures HNSW,
enables Binary Quantization, and creates payload indexes on all filter fields.

Safe to re-run — skips creation if the collection already exists.

Usage:
    python setup_collection.py
    python setup_collection.py --recreate   # drops and recreates (DELETES ALL DATA)
"""

import argparse
import sys
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
from app.config import settings


def create_collection(client: QdrantClient, recreate: bool = False) -> None:
    existing = [c.name for c in client.get_collections().collections]

    if settings.collection_name in existing:
        if recreate:
            print(f"[setup] Dropping existing collection '{settings.collection_name}'...")
            client.delete_collection(settings.collection_name)
            print("[setup] Collection dropped.")
        else:
            print(f"[setup] Collection '{settings.collection_name}' already exists. Skipping.")
            print("[setup] Run with --recreate to drop and recreate (DELETES ALL DATA).")
            return

    print(f"[setup] Creating collection '{settings.collection_name}'...")
    print(f"        embed_dim  = {settings.embed_dim}")
    print(f"        distance   = COSINE")
    print(f"        quantize   = Binary (40x memory reduction)")

    client.create_collection(
        collection_name=settings.collection_name,
        vectors_config=VectorParams(
            size=settings.embed_dim,
            distance=Distance.COSINE,
            # Store raw vectors on disk, quantized index in RAM.
            # This is the recommended setting for 30M+ vectors.
            on_disk=True,
        ),
        hnsw_config=HnswConfigDiff(
            m=16,                   # number of edges per node (higher = better recall, more RAM)
            ef_construction=128,    # search width during index build (higher = slower build, better quality)
            on_disk=False,          # keep HNSW graph in RAM for fast traversal
        ),
        # Binary Quantization: compresses each dimension to 1 bit.
        # Reduces memory from ~450GB to ~12GB for 30M × 384-dim vectors.
        # Recall loss is minimal with oversampling enabled.
        quantization_config=BinaryQuantization(
            binary=BinaryQuantizationConfig(
                always_ram=True,    # quantized index always in RAM, raw vectors on disk
            )
        ),
        optimizers_config=OptimizersConfigDiff(
            # Increase memmap_threshold to avoid too-frequent index rebuilds
            # during bulk ingestion of 30M documents.
            memmap_threshold=50000,
        ),
    )
    print("[setup] Collection created.")

    # ── Payload indexes ────────────────────────────────────────────────────
    # Without these, filtered searches scan every point.
    # With them, Qdrant can narrow the candidate set before ANN.
    # Create an index for every field you filter on in searcher.py.

    payload_indexes = [
        ("doc_type",      PayloadSchemaType.KEYWORD),   # policy | faq | exclusion | endorsement
        ("coverage_type", PayloadSchemaType.KEYWORD),   # fire | flood | theft | earthquake
        ("region",        PayloadSchemaType.KEYWORD),   # tamil_nadu | maharashtra | all …
        ("policy_id",     PayloadSchemaType.KEYWORD),   # HOME-FIRE-TN-2024
        ("language",      PayloadSchemaType.KEYWORD),   # en | ta | hi
        ("tags",          PayloadSchemaType.KEYWORD),   # array field — one index covers all tags
        ("version",       PayloadSchemaType.FLOAT),     # numeric — supports range filters
        ("last_updated",  PayloadSchemaType.TEXT),      # ISO date string
    ]

    print("[setup] Creating payload indexes...")
    for field_name, schema_type in payload_indexes:
        client.create_payload_index(
            collection_name=settings.collection_name,
            field_name=field_name,
            field_schema=schema_type,
        )
        print(f"        ✓ {field_name} ({schema_type})")

    print("[setup] All payload indexes created.")
    print("[setup] ✓ Setup complete.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Set up Qdrant collection for insurance RAG.")
    parser.add_argument(
        "--recreate",
        action="store_true",
        help="Drop and recreate the collection. WARNING: deletes all data.",
    )
    args = parser.parse_args()

    if args.recreate:
        confirm = input(
            f"[setup] WARNING: This will DELETE ALL DATA in '{settings.collection_name}'.\n"
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
        print(f"        Is Qdrant running? Try: podman start insurance-qdrant")
        sys.exit(1)

    create_collection(client, recreate=args.recreate)


if __name__ == "__main__":
    main()