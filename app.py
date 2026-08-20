from __future__ import annotations

import logging
import os

from prospector.settings import Settings
from prospector.web import create_app

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"), format="%(asctime)s %(levelname)s %(name)s: %(message)s")

settings = Settings()
app = create_app(settings=settings)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=settings.port, threaded=True)
