# Output contract

The script emits `source_type`, `source`, `text`, `segments`, `resources`, `metadata`, and `errors` as JSON.

Video segments contain `timestamp`, `text`, and `score`. Resources contain `url`, `category`, `label`, and `context`.

- `project`: GitHub/GitLab repository links or project/repository/source-code labels.
- `skill`: Skill, plugin, MCP, Agent capability, marketplace, or `SKILL.md` links.
- `recommended`: other HTTP(S) recommendations.

Do not persist raw frames, downloaded media, or full article bodies without explicit authorization.
