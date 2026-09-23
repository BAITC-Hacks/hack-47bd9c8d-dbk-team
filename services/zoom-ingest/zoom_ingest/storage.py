import io
import json

from minio import Minio

STATE_KEY = "state.json"


class Storage:
    """MinIO: recordings bucket for media, state bucket for dedupe state."""

    def __init__(
        self,
        endpoint: str,
        access_key: str,
        secret_key: str,
        secure: bool,
        recordings_bucket: str,
        state_bucket: str,
    ):
        self._client = Minio(
            endpoint,
            access_key=access_key,
            secret_key=secret_key,
            secure=secure,
        )
        self._recordings_bucket = recordings_bucket
        self._state_bucket = state_bucket

    def _ensure_bucket(self, bucket: str) -> None:
        if not self._client.bucket_exists(bucket):
            self._client.make_bucket(bucket)

    def put_recording(
        self, object_key: str, data: bytes, content_type: str
    ) -> None:
        self._ensure_bucket(self._recordings_bucket)
        self._client.put_object(
            self._recordings_bucket,
            object_key,
            io.BytesIO(data),
            len(data),
            content_type=content_type,
        )

    def load_state(self) -> dict:
        """Processed recording UUIDs + last successful pass timestamp."""
        try:
            resp = self._client.get_object(self._state_bucket, STATE_KEY)
            try:
                return json.loads(resp.read().decode("utf-8"))
            finally:
                resp.close()
                resp.release_conn()
        except Exception:
            return {"processed_uuids": [], "last_pass_at": None}

    def save_state(self, state: dict) -> None:
        self._ensure_bucket(self._state_bucket)
        payload = json.dumps(state, ensure_ascii=False).encode("utf-8")
        self._client.put_object(
            self._state_bucket,
            STATE_KEY,
            io.BytesIO(payload),
            len(payload),
            content_type="application/json",
        )
