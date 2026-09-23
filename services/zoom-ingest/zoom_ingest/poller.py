import logging
import re
from datetime import datetime, timedelta, timezone

from .config import Config
from .events import Events
from .storage import Storage
from .zoom_client import ZoomClient

log = logging.getLogger("zoom_ingest.poller")

# file_type → (filename, content_type). AUDIO first — it is what the
# pipeline needs; MP4 only as a fallback when M4A is missing.
FILE_MAP = {
    "M4A": ("audio.m4a", "audio/mp4"),
    "MP4": ("video.mp4", "video/mp4"),
    "TRANSCRIPT": ("transcript.vtt", "text/vtt"),
}


def make_meeting_id(
    zoom_meeting_id: int | str, recording_start: str, uuid: str = ""
) -> str:
    """zoom-<meeting_id>-<UTC YYYYMMDDTHHMMSS> — deterministic, readable,
    stable across repeated recordings of the same meeting. The list endpoint
    returns start_time (not recording_start) at meeting level; when no
    timestamp is available, fall back to a uuid suffix to avoid collisions."""
    stamp = re.sub(r"[-:]", "", recording_start).replace("Z", "")[:15]
    if not stamp:
        stamp = f"u{abs(hash(uuid)) % 10_000_000}"
    return f"zoom-{zoom_meeting_id}-{stamp}"


def pick_media_files(recording_files: list[dict]) -> dict[str, dict]:
    """One file per kind: audio (M4A preferred over MP4) + transcript."""
    completed = [f for f in recording_files if f.get("status") == "completed"]
    by_type: dict[str, dict] = {}
    for f in completed:
        by_type.setdefault(f.get("file_type", ""), f)
    picked: dict[str, dict] = {}
    if "M4A" in by_type:
        picked["M4A"] = by_type["M4A"]
    elif "MP4" in by_type:
        picked["MP4"] = by_type["MP4"]
    if "TRANSCRIPT" in by_type:
        picked["TRANSCRIPT"] = by_type["TRANSCRIPT"]
    return picked


class Poller:
    def __init__(
        self,
        config: Config,
        zoom: ZoomClient,
        storage: Storage,
        events: Events | None,
    ):
        self._config = config
        self._zoom = zoom
        self._storage = storage
        self._events = events

    def _user_ids(self) -> list[str]:
        if self._config.zoom_user_id:
            return [self._config.zoom_user_id]
        return [u["id"] for u in self._zoom.list_users()]

    def run_once(self, dry_run: bool = False) -> int:
        """One polling pass. Returns the number of ingested recordings."""
        state = self._storage.load_state()
        processed: set[str] = set(state.get("processed_uuids", []))
        date_to = datetime.now(timezone.utc).date()
        date_from = date_to - timedelta(days=self._config.lookback_days)
        ingested = 0

        for user_id in self._user_ids():
            meetings = self._zoom.list_recordings(
                user_id, date_from.isoformat(), date_to.isoformat()
            )
            for meeting in meetings:
                uuid = meeting.get("uuid", "")
                if not uuid or uuid in processed:
                    continue
                picked = pick_media_files(meeting.get("recording_files", []))
                if not any(k in picked for k in ("M4A", "MP4")):
                    log.info("пропуск %s: нет готового аудио/видео", uuid)
                    continue

                meeting_id = make_meeting_id(
                    meeting.get("id", "unknown"),
                    meeting.get("recording_start") or meeting.get("start_time", ""),
                    uuid,
                )
                log.info(
                    "ingest %s → %s (файлы: %s)",
                    uuid,
                    meeting_id,
                    ",".join(picked),
                )
                if dry_run:
                    ingested += 1
                    continue

                audio_key: str | None = None
                audio_name: str | None = None
                for file_type, zfile in picked.items():
                    download_url = zfile.get("download_url")
                    if not download_url:
                        log.warning("  %s: нет download_url, пропуск файла", file_type)
                        continue
                    filename, content_type = FILE_MAP[file_type]
                    object_key = f"{meeting_id}/{filename}"
                    resp = self._zoom.download(download_url)
                    data = resp.content
                    resp.close()
                    self._storage.put_recording(object_key, data, content_type)
                    log.info("  %s → %s (%d байт)", file_type, object_key, len(data))
                    if file_type in ("M4A", "MP4") and audio_key is None:
                        audio_key, audio_name = object_key, filename

                if self._events and audio_key:
                    self._events.publish_uploaded(
                        meeting_id=meeting_id,
                        object_key=audio_key,
                        filename=audio_name or "audio.m4a",
                        lang_hint=self._config.lang_hint,
                    )
                processed.add(uuid)
                ingested += 1

        if not dry_run:
            state["processed_uuids"] = sorted(processed)
            state["last_pass_at"] = datetime.now(timezone.utc).isoformat()
            self._storage.save_state(state)
        log.info("проход завершён: обработано %d записей", ingested)
        return ingested
