from __future__ import annotations

import json
import sys

from app.config import get_settings
from app.db import Base, SessionLocal, engine
from app.db_migrations import run_sqlite_migrations
from app.services.container import ServiceContainer


def main() -> int:
    try:
        Base.metadata.create_all(bind=engine)
        run_sqlite_migrations(engine)
        container = ServiceContainer(get_settings())
        with SessionLocal() as db:
            data = container.link_archive_service.run(db)
        print(json.dumps({"success": True, "message": "归档完成", "data": data}, ensure_ascii=False, indent=2))
        return 2 if any(data[name] for name in ("failed_fetch", "failed_parse", "failed_notion")) else 0
    except Exception as exc:
        print(json.dumps({"success": False, "message": str(exc), "data": None}, ensure_ascii=False), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())