from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

from .settings import settings

_client: AsyncIOMotorClient | None = None


def get_db() -> AsyncIOMotorDatabase:
    global _client
    if _client is None:
        _client = AsyncIOMotorClient(settings.mongo_url)
    return _client[settings.mongo_db]


async def resolve_version(client_version: str | None, *, pt: bool = False) -> str | None:
    """Translate `client_version=latest` (or None) to the actual version tag.

    Returns None if no patch has been ingested yet — callers should treat that
    as an empty result rather than a server error."""
    if client_version and client_version != "latest":
        return client_version
    alias = await get_db().aliases.find_one({"_id": "latest_pt" if pt else "latest"})
    return alias["client_version"] if alias else None
