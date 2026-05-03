from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from .db import get_db
from .routes import encyclopedia
from .settings import settings

_API_DESCRIPTION = """
A read-only catalog of **World of Warships** game data — ships, nations,
crew, achievements, ribbons, battle types, maps and more — extracted
straight from the game client and refreshed every patch.

### New here? Start with these three calls

1. `GET /v1/ships` — browse every ship in the live patch. Try the
   `nation=usa` or `type=Battleship` filters.
2. `GET /v1/achievements` — every in-game achievement with icons and
   localised descriptions.
3. `GET /v1/battle-types` — the list of battle modes (Random, Co-op,
   Ranked, Clan Battles, Operations, …).

Every response is plain JSON and every endpoint accepts the same two
options:

| Query param | What it does | Example |
|-------------|--------------|---------|
| `version`   | Pin to a specific patch (e.g. `15.3.0.0`). Omit for the latest patch. | `?version=15.3.0.0` |
| `language`  | Translate `name` / `description` fields. Defaults to `en`. | `?language=ru` |

Available languages typically include `en`, `ru`, `de`, `fr`, `es`,
`pl`, `cs`, `tr`, `ja`, `zh_sg` (mirrors what ships in the client).

### Icons & images

Every `icon` / `icons` / `flags` / `images` / `portrait` field is a
fully-qualified URL to a PNG. Files are content-addressed (the SHA is
in the URL), so they never change — feel free to cache them forever.

### Versioning

The data behind every response is tied to a game patch. The default is
**the latest patch we have ingested**; pass `?version=X.Y.Z.W` to get
a snapshot from an older patch. Hit `/health` to see which patches are
currently loaded.

### Quick links

- **Health & ingest status**: [`/health`](/health)
- **Raw OpenAPI schema**: [`/openapi.json`](/openapi.json)
- **Game-data ingest**: runs automatically in the background; see
  `/health.last_run` for the most recent run.
"""

_TAGS_METADATA = [
    {
        "name": "encyclopedia",
        "description": (
            "Browse the in-game catalog: ships, nations, crew, "
            "achievements, ribbons, battle types, maps and more. "
            "Every endpoint serves data from a single game patch — "
            "the latest by default, or a specific one via `?version=`."
        ),
    },
    {
        "name": "system",
        "description": "Service health and ingest status.",
    },
]

app = FastAPI(
    title="WoWs Encyclopedia API",
    description=_API_DESCRIPTION,
    version="0.0.1",
    docs_url=None,
    openapi_tags=_TAGS_METADATA,
    contact={"name": "REPLAYS / WOWS", "url": "https://replayswows.com/"},
)

_STATIC_DIR = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")


# FastAPI's get_swagger_ui_html replaces the upstream stylesheet when
# swagger_css_url is set — which strips out all of Swagger UI's structural
# CSS. We render the page manually so we can load the upstream CSS *and*
# layer our theme on top of it.
_SWAGGER_JS = "https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui-bundle.js"
_SWAGGER_CSS = "https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui.css"


@app.get("/docs", include_in_schema=False, response_class=HTMLResponse)
async def custom_swagger_ui() -> HTMLResponse:
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{app.title} — Docs</title>
<link rel="stylesheet" href="{_SWAGGER_CSS}">
<link rel="stylesheet" href="/static/swagger-theme.css">
</head>
<body>
<div id="swagger-ui"></div>
<script src="{_SWAGGER_JS}"></script>
<script>
window.ui = SwaggerUIBundle({{
    url: '{app.openapi_url}',
    dom_id: '#swagger-ui',
    layout: 'BaseLayout',
    deepLinking: true,
    showExtensions: true,
    showCommonExtensions: true,
    presets: [SwaggerUIBundle.presets.apis, SwaggerUIBundle.SwaggerUIStandalonePreset],
}});
</script>
</body>
</html>"""
    return HTMLResponse(html)


app.include_router(encyclopedia.router)

# Icon blobs are content-addressed — the SHA in the URL guarantees the bytes
# never change, so we let CDNs and browsers cache them effectively forever.
_ICON_CACHE_HEADER = "public, max-age=31536000, immutable"


@app.middleware("http")
async def _cache_icon_blobs(request: Request, call_next):
    response = await call_next(request)
    if request.url.path.startswith("/icons/blobs/"):
        response.headers["Cache-Control"] = _ICON_CACHE_HEADER
    return response


# StaticFiles refuses to mount a non-existent directory; create it on startup
# so a fresh deployment doesn't crash before the first ingest runs.
_blobs_dir = Path(settings.icons_blobs_dir)
_blobs_dir.mkdir(parents=True, exist_ok=True)
app.mount("/icons/blobs", StaticFiles(directory=str(_blobs_dir)), name="icons")


@app.get(
    "/health",
    tags=["system"],
    summary="Service health and ingest status",
    description=(
        "Lightweight liveness probe used by load balancers and uptime "
        "checks. Also reports how many patches have been ingested, the "
        "current `latest` patch alias, and the result of the last "
        "background ingest run."
    ),
)
async def health() -> dict:
    db = get_db()
    manifests = await db.manifests.count_documents({})
    latest = await db.aliases.find_one({"_id": "latest"})
    last_run = await db.last_run.find_one({"_id": "ingest"})
    if last_run is not None:
        last_run.pop("_id", None)
    return {
        "ok": True,
        "patches_ingested": manifests,
        "latest_version": latest["client_version"] if latest else None,
        "last_run": last_run,
    }
