#!/usr/bin/env python3
"""Finalize agent-completed translation packages by updating qa.json."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from run_translation_pipeline import paragraph_split, read_frontmatter  # pylint: disable=import-error


PLACEHOLDER_MARKERS = (
    "No API key detected",
    "ask Codex to translate",
    "The current agent must continue",
    "translation.md is passthrough content",
    "Deep mode created critique and revision scaffolding",
)

STRUCTURED_SECTION_MARKERS = (
    "## 原英文标题",
    "## 原稿链接",
    "## 中文标题",
    "## 推荐公众号标题",
    "## 推荐摘要一句话",
    "## 正文翻译",
)
STRUCTURED_PLACEHOLDER = "（待补充）"
STRUCTURED_FRONTMATTER_FIELDS = (
    "original_title",
    "recommended_social_title",
    "summary",
)

DRAFT_STUB_MARKERS = (
    "Status: `needs_translation`",
    "## Source Snapshot",
    "Pipeline ran in codex mode",
    "Pipeline ran in passthrough mode",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Mark an agent-completed translation package as finalized.",
    )
    parser.add_argument(
        "--article-dir",
        required=True,
        help="Article output directory containing qa.json and translation artifacts.",
    )
    return parser.parse_args()


def read_text(path: Path) -> str:
    if not path.exists():
        raise FileNotFoundError(f"Required file not found: {path}")
    return path.read_text(encoding="utf-8")


def read_body(path: Path) -> str:
    _, body = read_frontmatter(path)
    return body.strip()


def validate_translation(article_dir: Path, qa: dict[str, object]) -> None:
    translation_path = Path(str(qa.get("translation_file") or article_dir / "translation.md"))
    translation_meta, translation_body = read_frontmatter(translation_path)
    translation_body = translation_body.strip()
    if not translation_body:
        raise ValueError("translation.md body is empty.")

    source_path = article_dir / "00-source.md"
    if source_path.exists():
        source_body = read_body(source_path)
        if source_body == translation_body:
            raise ValueError("translation.md still matches the source body; translation is not finalized.")
    if any(marker in translation_body for marker in DRAFT_STUB_MARKERS):
        raise ValueError("translation.md still contains chunk draft stub markers.")
    if str(qa.get("resolved_translator") or "") in {"codex", "passthrough"}:
        missing_frontmatter_fields = [
            field for field in STRUCTURED_FRONTMATTER_FIELDS if not str(translation_meta.get(field) or "").strip()
        ]
        missing_sections = [marker for marker in STRUCTURED_SECTION_MARKERS if marker not in translation_body]
        if missing_frontmatter_fields and missing_sections:
            raise ValueError(
                "translation.md is missing required structured metadata or sections: "
                + ", ".join(missing_frontmatter_fields + missing_sections)
            )
        if STRUCTURED_PLACEHOLDER in translation_body or any(
            str(translation_meta.get(field) or "").strip() == STRUCTURED_PLACEHOLDER
            for field in STRUCTURED_FRONTMATTER_FIELDS
        ):
            raise ValueError("translation.md still contains structured output placeholders.")

    revision_file = str(qa.get("revision_file") or "")
    if revision_file:
        revision_path = Path(revision_file)
        revision_body = read_text(revision_path).strip()
        if not revision_body:
            raise ValueError("07-revision.md is empty.")

    drafts_dir = article_dir / "04-drafts"
    if drafts_dir.exists():
        for draft_path in sorted(drafts_dir.glob("*.md")):
            draft_text = read_text(draft_path)
            if any(marker in draft_text for marker in DRAFT_STUB_MARKERS):
                raise ValueError(f"Chunk draft still contains placeholder markers: {draft_path.name}")


def finalize_qa(article_dir: Path) -> Path:
    qa_path = article_dir / "qa.json"
    qa = json.loads(read_text(qa_path))

    validate_translation(article_dir, qa)

    issues = [str(item) for item in qa.get("issues", [])]
    filtered_issues = [issue for issue in issues if not any(marker in issue for marker in PLACEHOLDER_MARKERS)]

    translation_path = Path(str(qa.get("translation_file") or article_dir / "translation.md"))
    translation_body = read_body(translation_path)
    translated_paragraphs = len(paragraph_split(translation_body)) if translation_body else 0
    source_paragraphs = int(qa.get("source_paragraphs") or 0)
    if source_paragraphs and translated_paragraphs / source_paragraphs >= 0.9:
        filtered_issues = [
            issue
            for issue in filtered_issues
            if issue != "Translated paragraph count is lower than source paragraph count."
        ]
    qa["translated_paragraphs"] = translated_paragraphs

    qa["requires_agent_completion"] = False
    qa["verdict"] = "ready"
    qa["issues"] = filtered_issues
    qa["finalized_by"] = "agent"

    qa_path.write_text(json.dumps(qa, ensure_ascii=False, indent=2), encoding="utf-8")
    return qa_path


def main() -> int:
    args = parse_args()
    article_dir = Path(args.article_dir).expanduser().resolve()
    try:
        qa_path = finalize_qa(article_dir)
    except Exception as exc:  # pylint: disable=broad-except
        sys.stderr.write(f"Finalize failed: {exc}\n")
        return 1

    print(f"finalized_qa: {qa_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
