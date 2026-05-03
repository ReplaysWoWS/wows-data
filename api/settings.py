from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    mongo_url: str = "mongodb://localhost:27017"
    mongo_db: str = "wows"

    # Where ingest places (and the API serves) content-addressed icon PNGs.
    # The on-disk layout under this dir is `<2-char-shard>/<sha256>.png`.
    icons_blobs_dir: str = "/app/data/icons/blobs"
    # URL prefix joined with `<2-char-shard>/<sha256>.png` to form public
    # icon URLs. Default points at the StaticFiles mount in api/main.py;
    # override to a CDN base URL in production.
    icon_url_prefix: str = "/icons/blobs"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


settings = Settings()
