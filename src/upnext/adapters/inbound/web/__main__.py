"""Run the API directly: `python -m upnext.adapters.inbound.web`."""

from __future__ import annotations

import uvicorn

from upnext.config.settings import load_settings


def main() -> None:
    settings = load_settings()
    uvicorn.run("upnext.adapters.inbound.web.api:app", host=settings.host, port=settings.port, reload=False)


if __name__ == "__main__":
    main()
