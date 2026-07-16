# Global Tech Translation Skill

## Purpose

`skills/global-tech-translation/` vendors the WomenStack global technology article translation skill into this repository. It turns a public overseas technology article URL into a traceable translation package with source extraction, analysis, chunk prompts, draft/revision files, QA metadata, and optional low-cost model routing.

This project copy keeps the skill next to the existing project skills so MemFlow agents can reference a stable in-repository path without depending on the user's global Codex skill installation.

## Public Interface

The skill is triggered by its `SKILL.md` instructions or by running its pipeline script directly from the repository root:

```powershell
python skills\global-tech-translation\scripts\run_translation_pipeline.py --url "https://example.com/post" --mode deep --translator auto
```

Important files:

- `skills/global-tech-translation/SKILL.md`: workflow, trigger language, translation policy, output contract, and agent handoff rules.
- `skills/global-tech-translation/EXTEND.md`: default target language, audience, tone, chunk thresholds, and terminology overrides.
- `skills/global-tech-translation/references/`: glossary, source policy, translator profile, and shared prompt material.
- `skills/global-tech-translation/scripts/run_translation_pipeline.py`: main URL-to-translation package pipeline.
- `skills/global-tech-translation/scripts/rebuild_from_chunk_drafts.py`: rebuilds merged and final translation files after chunk drafts are completed.
- `skills/global-tech-translation/scripts/finalize_agent_translation.py`: validates agent-completed translations and updates QA status.

## Persisted Fields And Outputs

No MemFlow database fields, HTTP APIs, Notion schema, or app state transitions are changed.

The skill writes article outputs under its local `output/` directory by default. That directory is ignored by `skills/global-tech-translation/.gitignore` and must not be committed because it may contain raw or translated user content.

Typical generated files include:

- `00-source.md`
- `01-analysis.md`
- `02-shared-prompt.md`
- `03-chunks.json`
- `04-chunk-sources/`
- `04-chunk-prompts/`
- `04-drafts/`
- `05-merged.md`
- `06-critique.md`
- `07-revision.md`
- `08-agent-handoff.md`
- `09-agent-completion-prompt.md`
- `translation.md`
- `qa.json`

## State And Failure Behavior

The skill-level QA state is represented in generated `qa.json`, not in MemFlow application state.

Expected failure and fallback behavior:

- Unreachable or unsupported source URLs fail during source extraction and should keep the original URL in the output metadata.
- Missing translation API keys route `--translator auto` to the Codex handoff path instead of pretending a final translation is complete.
- Chunk drafts remain intermediate artifacts until `rebuild_from_chunk_drafts.py` and `finalize_agent_translation.py` complete successfully.
- Publication-ready output requires `qa.json` to show a ready/completed verdict or explicit human approval.

## Test Coverage And Verification

This change vendors the skill files only. Verification is file-level and syntax-level:

- Confirmed `skills/global-tech-translation/SKILL.md` and supporting references/scripts exist.
- Compiled the Python scripts under `skills/global-tech-translation/scripts`.
- Confirmed no application API, database schema, or frontend state was modified.
