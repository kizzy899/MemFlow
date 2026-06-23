from pathlib import Path


REQUIRED_DOCS = [
    "00-implementation-log.md",
    "05-notion-sync-retry.md",
    "06-local-items-api.md",
    "07-sqlite-schema.md",
    "08-deduplication.md",
    "09-notion-validation.md",
    "10-testing-and-verification.md",
]


def test_phase_two_documents_exist_and_are_indexed() -> None:
    docs_dir = Path(__file__).resolve().parent.parent / "docs"
    index = (docs_dir / "README.md").read_text(encoding="utf-8")

    for filename in REQUIRED_DOCS:
        path = docs_dir / filename
        assert path.exists(), f"missing documentation: {filename}"
        assert filename in index, f"documentation is not indexed: {filename}"


def test_repository_documentation_rule_exists() -> None:
    root = Path(__file__).resolve().parent.parent
    instructions = (root / "AGENTS.md").read_text(encoding="utf-8")
    assert "docs/00-implementation-log.md" in instructions
    assert "docs/README.md" in instructions
