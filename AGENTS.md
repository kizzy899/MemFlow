# MemFlow repository instructions

Every feature or module change must update the project documentation in the same change.

Required documentation work:

1. Create or update the module document under `docs/`.
2. Add the document to `docs/README.md`.
3. Append the implementation sequence, decisions, changed files, and verification results to `docs/00-implementation-log.md`.
4. Document public APIs, persisted fields, state transitions, failure behavior, and test coverage.

Do not commit `.env`, secrets, generated databases, caches, or raw/translated user content.
