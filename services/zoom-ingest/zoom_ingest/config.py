import os
from dataclasses import dataclass

from dotenv import load_dotenv


@dataclass(frozen=True)
class Config:
    zoom_account_id: str
    zoom_client_id: str
    zoom_client_secret: str
    zoom_user_id: str  # empty = poll every user in the account
    poll_interval_sec: int
    lookback_days: int
    kafka_brokers: list[str]
    topic_uploaded: str
    minio_endpoint: str
    minio_access_key: str
    minio_secret_key: str
    minio_secure: bool
    recordings_bucket: str
    state_bucket: str
    lang_hint: str


def load_config() -> Config:
    load_dotenv()

    def require(name: str) -> str:
        value = os.environ.get(name, "").strip()
        if not value:
            raise RuntimeError(f"Переменная окружения {name} не задана")
        return value

    return Config(
        zoom_account_id=require("ZOOM_ACCOUNT_ID"),
        zoom_client_id=require("ZOOM_CLIENT_ID"),
        zoom_client_secret=require("ZOOM_CLIENT_SECRET"),
        zoom_user_id=os.environ.get("ZOOM_USER_ID", "").strip(),
        poll_interval_sec=int(os.environ.get("ZOOM_POLL_INTERVAL_SEC", "120")),
        lookback_days=int(os.environ.get("ZOOM_LOOKBACK_DAYS", "1")),
        kafka_brokers=os.environ.get("KAFKA_BROKERS", "localhost:9092").split(","),
        topic_uploaded=os.environ.get("TOPIC_UPLOADED", "meetings.uploaded"),
        minio_endpoint=os.environ.get("MINIO_ENDPOINT", "localhost:9000"),
        minio_access_key=require("MINIO_ACCESS_KEY"),
        minio_secret_key=require("MINIO_SECRET_KEY"),
        minio_secure=os.environ.get("MINIO_USE_SSL", "false") == "true",
        recordings_bucket=os.environ.get("RECORDINGS_BUCKET", "recordings"),
        state_bucket=os.environ.get("STATE_BUCKET", "zoom-ingest"),
        lang_hint=os.environ.get("LANG_HINT", "auto"),
    )
