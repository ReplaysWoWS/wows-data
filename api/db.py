from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

from .settings import settings

_client: AsyncIOMotorClient | None = None


def get_db() -> AsyncIOMotorDatabase:
    global _client
    if _client is None:
        _client = AsyncIOMotorClient(settings.mongo_url)
    return _client[settings.mongo_db]


async def resolve_version(client_version: str | None, *, pt: bool = False) -> str | None:
    """Translate a user-facing version (or `latest` / None) to the internal
    data-partition tag used as the `client_version` field on stored docs.

    The ingest pipeline writes a fully-populated partition first, then flips
    the `latest` alias and a `ready: True` manifest in a final two-doc step.
    Resolving through that indirection is what guarantees readers never see
    a half-baked re-ingest. Returns None if no patch matches — callers
    should treat that as an empty result rather than a server error."""
    db = get_db()
    if client_version and client_version != "latest":
        manifest = await db.manifests.find_one(
            {"client_version": client_version, "ready": {"$ne": False}}
        )
        if manifest is None:
            return None
        return manifest.get("data_partition") or manifest["client_version"]
    alias = await db.aliases.find_one({"_id": "latest_pt" if pt else "latest"})
    if alias is None:
        return None
    return alias.get("data_partition") or alias["client_version"]
