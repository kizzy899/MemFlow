#!/usr/bin/env python3
"""Rebuild merged/revision/translation artifacts from completed chunk drafts."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from run_translation_pipeline import (  # pylint: disable=import-error
    apply_glossary,
    build_critique_text,
    extract_chunk_draft_body,
    extract_primary_source_title,
    load_extend_config,
    load_glossary,
    merge_glossary,
    read_frontmatter,
    render_translation_markdown,
)
PROJECT_ROOT = Path(__file__).resolve().parent.parent


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Rebuild translation artifacts from completed chunk drafts.",
    )
    parser.add_argument(
        "--article-dir",
        required=True,
        help="Article output directory containing 04-drafts and translation package files.",
    )
    parser.add_argument(
        "--sync-revision",
        action="store_true",
        help="Also overwrite 07-revision.md with the rebuilt merged body.",
    )
    return parser.parse_args()


def extract_assets(body: str) -> list[dict[str, str]]:
    assets: list[dict[str, str]] = []
    for line in body.splitlines():
        stripped = line.strip()
        match = re.match(r"!\[(.*?)\]\((.*?)\)", stripped)
        if not match:
            continue
        alt_text, path = match.groups()
        assets.append({"local_path": path, "alt_text": alt_text.strip()})
    return assets


def load_chunk_order(article_dir: Path) -> list[str]:
    chunks_path = article_dir / "03-chunks.json"
    chunks = json.loads(chunks_path.read_text(encoding="utf-8"))
    return [str(chunk["chunk_id"]) for chunk in chunks]


def rebuild(article_dir: Path, sync_revision: bool) -> dict[str, str]:
    translation_path = article_dir / "translation.md"
    source_path = article_dir / "00-source.md"
    merged_path = article_dir / "05-merged.md"
    critique_path = article_dir / "06-critique.md"
    revision_path = article_dir / "07-revision.md"
    qa_path = article_dir / "qa.json"
    drafts_dir = article_dir / "04-drafts"

    meta, _ = read_frontmatter(translation_path)
    source_meta, source_body = read_frontmatter(source_path)
    assets = extract_assets(source_body)

    chunk_ids = load_chunk_order(article_dir)
    draft_bodies: list[str] = []
    for chunk_id in chunk_ids:
        draft_path = drafts_dir / f"{chunk_id}.md"
        draft_text = draft_path.read_text(encoding="utf-8")
        draft_body = extract_chunk_draft_body(draft_text)
        if draft_body:
            draft_bodies.append(draft_body)

    merged_body = "\n\n".join(draft_bodies).strip()

    qa = json.loads(qa_path.read_text(encoding="utf-8"))
    extend_file = str(qa.get("extend_file") or PROJECT_ROOT / "EXTEND.md")
    glossary = merge_glossary(
        load_glossary(str(PROJECT_ROOT / "references" / "glossary.csv")),
        load_extend_config(extend_file).glossary_overrides or [],
    )
    merged_body = apply_glossary(merged_body, glossary)
    merged_path.write_text(merged_body + "\n", encoding="utf-8")
    if critique_path.exists():
        critique_text = build_critique_text(source_body, merged_body)
        critique_path.write_text(critique_text, encoding="utf-8")

    if sync_revision and revision_path.exists():
        revision_path.write_text(merged_body + "\n", encoding="utf-8")

    source_title = str(source_meta.get("title") or meta.get("original_title") or "Untitled")
    translation_body = render_translation_markdown(
        meta,
        source_title=source_title,
        source_text=source_body,
        body=merged_body,
        assets=assets,
        structured_output=str(qa.get("resolved_translator") or "") in {"codex", "passthrough"},
        chinese_title=str(meta.get("title") or "")
        if str(qa.get("resolved_translator") or "") in {"codex", "passthrough"}
        else extract_primary_source_title(source_title),
        social_title=str(meta.get("recommended_social_title") or ""),
        summary=str(meta.get("summary") or ""),
    )
    translation_path.write_text(translation_body, encoding="utf-8")

    return {
        "merged_file": str(merged_path),
        "critique_file": str(critique_path) if critique_path.exists() else "",
        "translation_file": str(translation_path),
        "revision_file": str(revision_path) if sync_revision and revision_path.exists() else "",
    }


def main() -> int:
    args = parse_args()
    article_dir = Path(args.article_dir).expanduser().resolve()
    result = rebuild(article_dir, args.sync_revision)
    for key, value in result.items():
        if value:
            print(f"{key}: {value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
