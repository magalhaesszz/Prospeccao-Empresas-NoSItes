from __future__ import annotations

import logging
import os

from prospector.db import Database
from prospector.migration import prepare_legacy_database
from prospector.settings import Settings
from prospector.web import create_app

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"), format="%(asctime)s %(levelname)s %(name)s: %(message)s")

settings = Settings()
db = Database(settings.database_url)
if settings.database_url:
    prepare_legacy_database(db)
app = create_app(settings=settings, db=db)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=settings.port, threaded=True)
