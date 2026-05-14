"""
ingestion/parser.py
────────────────────────────────────────────────────────────────────────────
Parses Markdown files with YAML frontmatter into a flat list of chunk dicts.

Each .md file has this structure:
  ---
  policy_id: HOME-FIRE-TN-2024
  doc_type: policy
  coverage_type: fire
  region: tamil_nadu
  ...
  ---

  <!-- chunk_id: coverage_001 | tags: fire, structure -->
  ## What is covered

  Content text goes here...

  ---

  <!-- chunk_id: exclusions_001 | tags: exclusion, arson -->
  ## What is not covered

  Content text goes here...

For doc_type: faq, the ## heading becomes the question and is combined
with the body as "Q: {heading}\nA: {body}" for better semantic matching.
"""

import re
import hashlib
from pathlib import Path
from typing import Any

import frontmatter


# Required top-level metadata fields every .md file must have
REQUIRED_FIELDS = {"doc_type", "coverage_type", "region"}

# Regex to parse the chunk label comment:
# <!-- chunk_id: my_chunk_001 | tags: fire, structure, coverage -->
CHUNK_LABEL_RE = re.compile(
    r"<!--\s*chunk_id:\s*(?P<chunk_id>\S+)\s*\|?\s*(?:tags?:\s*(?P<tags>[^-\n]+?))?\s*-->",
    re.IGNORECASE,
)


class ParseError(Exception):
    """Raised when a document file fails validation."""
    pass


def _stable_point_id(chunk_id: str) -> int:
    """
    Convert a string chunk_id to a stable integer Qdrant point ID.
    Uses SHA-256 so the same chunk_id always produces the same integer.
    This is what makes surgical single-chunk updates possible.
    """
    digest = hashlib.sha256(chunk_id.encode()).hexdigest()
    return int(digest[:16], 16)  # first 16 hex chars → 64-bit int


def _parse_tags(raw: str | None) -> list[str]:
    """Parse comma-separated tags string into a clean list."""
    if not raw:
        return []
    return [t.strip() for t in raw.split(",") if t.strip()]


def _split_into_blocks(body: str) -> list[str]:
    """
    Split the document body on --- dividers.
    Strips empty blocks that result from leading/trailing dividers.
    """
    blocks = re.split(r"\n---\n", body)
    return [b.strip() for b in blocks if b.strip()]


def _extract_heading(block: str) -> tuple[str, str]:
    """
    Extract the first ## heading from a block.
    Returns (heading_text, body_without_heading_line).
    """
    match = re.search(r"^#{1,3}\s+(.+)$", block, re.MULTILINE)
    if not match:
        return "", block
    heading = match.group(1).strip()
    # Remove the heading line from the body
    body = block[: match.start()] + block[match.end() :]
    return heading, body.strip()


def parse_file(file_path: Path) -> list[dict[str, Any]]:
    """
    Parse a single Markdown file into a list of chunk dicts.

    Each returned dict contains:
      - chunk_id       : str  — unique stable identifier
      - point_id       : int  — stable Qdrant point ID derived from chunk_id
      - content        : str  — text to embed and store
      - section_title  : str  — heading of this chunk
      - tags           : list[str]
      - source_file    : str  — filename for traceability
      - ...all doc-level metadata fields from frontmatter

    Raises ParseError for missing required fields or empty chunks.
    """
    raw_text = file_path.read_text(encoding="utf-8")

    # ── 1. Parse frontmatter ───────────────────────────────────────────────
    try:
        post = frontmatter.loads(raw_text)
    except Exception as exc:
        raise ParseError(f"{file_path.name}: Failed to parse frontmatter — {exc}") from exc

    doc_meta: dict[str, Any] = dict(post.metadata)
    body: str = post.content

    # ── 2. Validate required metadata ─────────────────────────────────────
    missing = REQUIRED_FIELDS - set(doc_meta.keys())
    if missing:
        raise ParseError(
            f"{file_path.name}: Missing required frontmatter fields: {missing}"
        )

    doc_meta["source_file"] = file_path.name
    doc_type = str(doc_meta.get("doc_type", "policy")).lower()

    # ── 3. Split body into chunk blocks ───────────────────────────────────
    blocks = _split_into_blocks(body)
    if not blocks:
        raise ParseError(f"{file_path.name}: No content blocks found after frontmatter.")

    chunks: list[dict[str, Any]] = []

    for block in blocks:
        # ── 4. Extract chunk label comment ────────────────────────────────
        label_match = CHUNK_LABEL_RE.search(block)

        if not label_match:
            # Block has no label — generate a positional ID but warn.
            # This is a content-team mistake; the validator in ingest.py
            # will catch it in --dry-run mode.
            print(
                f"  [parser] WARNING: Block in {file_path.name} has no chunk_id comment. "
                "Skipping block. Add <!-- chunk_id: xxx | tags: yyy --> above the heading."
            )
            continue

        chunk_id = label_match.group("chunk_id").strip()
        tags = _parse_tags(label_match.group("tags"))

        # Remove the comment line from the block before further processing
        clean_block = CHUNK_LABEL_RE.sub("", block).strip()

        # ── 5. Extract heading and body ───────────────────────────────────
        section_title, prose = _extract_heading(clean_block)
        prose = prose.strip()

        if not prose:
            raise ParseError(
                f"{file_path.name}: chunk_id '{chunk_id}' has an empty content body."
            )

        # ── 6. For FAQs: combine heading (question) + prose (answer) ──────
        if doc_type == "faq" and section_title:
            content = f"Q: {section_title}\nA: {prose}"
        else:
            content = f"{section_title}\n\n{prose}" if section_title else prose

        # ── 7. Build the chunk dict ───────────────────────────────────────
        chunk: dict[str, Any] = {
            "chunk_id": chunk_id,
            "point_id": _stable_point_id(chunk_id),
            "content": content,
            "section_title": section_title,
            "tags": tags,
            **doc_meta,
        }
        chunks.append(chunk)

    if not chunks:
        raise ParseError(f"{file_path.name}: Produced zero valid chunks.")

    return chunks


def parse_folder(folder: Path) -> list[dict[str, Any]]:
    """
    Recursively parse all .md files in a folder.
    Returns a flat list of all chunk dicts across all files.
    Prints a per-file summary.
    """
    all_chunks: list[dict[str, Any]] = []
    md_files = sorted(folder.rglob("*.md"))

    if not md_files:
        print(f"[parser] No .md files found in {folder}")
        return all_chunks

    for file_path in md_files:
        try:
            chunks = parse_file(file_path)
            all_chunks.extend(chunks)
            print(f"[parser] ✓ {file_path.name}: {len(chunks)} chunks")
        except ParseError as exc:
            print(f"[parser] ✗ {exc}")

    print(f"[parser] Total: {len(all_chunks)} chunks from {len(md_files)} files.")
    return all_chunks