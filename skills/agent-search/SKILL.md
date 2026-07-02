---
name: agent-search
description: Extract on-screen text from local or public videos with sampled-frame OCR, and discover/classify project, Agent Skill, and recommended website URLs from articles or OCR text. Use for video text reading, resource discovery, GitHub project extraction, Skill address extraction, or recommended-link audits in MemFlow.
---

# Agent Search

Run the bundled deterministic extractor before summarizing results.

```powershell
.\.venv\Scripts\python.exe skills\agent-search\scripts\agent_search.py video <path-or-public-url> --interval 2
.\.venv\Scripts\python.exe skills\agent-search\scripts\agent_search.py article <path-url-or-text>
```

- Add `--pretty` for readable JSON.
- This version reads visible frame text, not spoken audio.
- Never persist downloaded media or article bodies; temporary media must be deleted.
- Read `references/output-contract.md` before API or database integration.
- Preserve video timestamps and group resources as `project`, `skill`, or `recommended`.
- Treat classification as a heuristic and retain original labels/context.
