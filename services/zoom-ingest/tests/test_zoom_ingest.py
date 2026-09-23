from zoom_ingest.bot import (
    build_ffmpeg_cmd,
    build_join_url,
    make_meeting_id as bot_meeting_id,
    parse_invite,
)
from zoom_ingest.poller import Poller, make_meeting_id, pick_media_files


class FakeResponse:
    def __init__(self, data: bytes):
        self.content = data

    def close(self):
        pass


class FakeZoom:
    def __init__(self, meetings):
        self._meetings = meetings
        self.downloads = []

    def list_users(self):
        return [{"id": "u1"}]

    def list_recordings(self, user_id, date_from, date_to):
        return self._meetings

    def download(self, url):
        self.downloads.append(url)
        return FakeResponse(b"audio-bytes")


class FakeStorage:
    def __init__(self, state=None):
        self.state = state or {"processed_uuids": [], "last_pass_at": None}
        self.objects = {}
        self.saved = False

    def load_state(self):
        return self.state

    def save_state(self, state):
        self.saved = True
        self.state = state

    def put_recording(self, object_key, data, content_type):
        self.objects[object_key] = (data, content_type)


class FakeEvents:
    def __init__(self):
        self.sent = []

    def publish_uploaded(self, meeting_id, object_key, filename, lang_hint):
        self.sent.append(
            {
                "meeting_id": meeting_id,
                "object_key": object_key,
                "filename": filename,
                "lang_hint": lang_hint,
            }
        )


class FakeConfig:
    zoom_user_id = "u1"
    lookback_days = 1
    lang_hint = "auto"


def meeting(uuid, files, meeting_id=123456789, start="2026-09-23T10:00:00Z"):
    return {
        "uuid": uuid,
        "id": meeting_id,
        "recording_start": start,
        "recording_files": files,
    }


def zfile(file_type, status="completed", url=None):
    return {
        "file_type": file_type,
        "status": status,
        "download_url": url or f"https://zoom.us/rec/download/{file_type.lower()}",
    }


# --- bot: pure helpers ---

def test_parse_invite_url_with_pwd():
    mid, pwd = parse_invite("https://zoom.us/j/12345678901?pwd=AbC123x")
    assert mid == "12345678901"
    assert pwd == "AbC123x"


def test_parse_invite_wc_join():
    mid, pwd = parse_invite("https://zoom.us/wc/join/98765432109")
    assert mid == "98765432109"
    assert pwd == ""


def test_parse_invite_bare_id_with_spaces():
    mid, pwd = parse_invite("123 456 7890", passcode="secret")
    assert mid == "1234567890"
    assert pwd == "secret"


def test_parse_invite_rejects_garbage():
    try:
        parse_invite("not-a-zoom-link")
    except ValueError:
        return
    raise AssertionError("ожидали ValueError")


def test_build_join_url():
    assert (
        build_join_url("12345678901", "x")
        == "https://zoom.us/wc/join/12345678901?pwd=x"
    )
    assert build_join_url("12345678901", "") == "https://zoom.us/wc/join/12345678901"


def test_build_ffmpeg_cmd_records_sink_monitor(tmp_path):
    cmd = build_ffmpeg_cmd(tmp_path / "out.webm", sink="zoom_capture")
    assert "zoom_capture.monitor" in cmd
    assert cmd[0] == "ffmpeg"
    assert "libopus" in cmd


def test_bot_meeting_id_format():
    key = bot_meeting_id("12345678901")
    assert key.startswith("zoom-live-12345678901-")
    assert len(key.split("-")[-1]) == 15  # YYYYMMDDTHHMMSS


# --- poller: pure helpers ---

def test_make_meeting_id_deterministic():
    assert (
        make_meeting_id(123456789, "2026-09-23T10:00:00Z")
        == "zoom-123456789-20260923T100000"
    )


def test_make_meeting_id_fallback_without_timestamp():
    key = make_meeting_id(123456789, "", uuid="abc")
    assert key.startswith("zoom-123456789-u")
    assert make_meeting_id(123456789, "", uuid="abc") == key  # детерминировано


def test_pick_media_prefers_m4a_and_transcript():
    picked = pick_media_files([zfile("MP4"), zfile("M4A"), zfile("TRANSCRIPT")])
    assert set(picked) == {"M4A", "TRANSCRIPT"}


def test_pick_media_falls_back_to_mp4():
    picked = pick_media_files([zfile("MP4")])
    assert set(picked) == {"MP4"}


def test_pick_media_skips_processing():
    assert pick_media_files([zfile("M4A", status="processing")]) == {}


# --- poller: run_once with fakes ---

def test_run_once_ingests_and_emits_contract_event():
    zoom = FakeZoom([meeting("uuid-1", [zfile("M4A"), zfile("TRANSCRIPT")])])
    storage = FakeStorage()
    events = FakeEvents()
    poller = Poller(FakeConfig(), zoom, storage, events)

    assert poller.run_once() == 1
    assert "zoom-123456789-20260923T100000/audio.m4a" in storage.objects
    assert "zoom-123456789-20260923T100000/transcript.vtt" in storage.objects
    assert events.sent == [
        {
            "meeting_id": "zoom-123456789-20260923T100000",
            "object_key": "zoom-123456789-20260923T100000/audio.m4a",
            "filename": "audio.m4a",
            "lang_hint": "auto",
        }
    ]
    assert storage.saved
    assert "uuid-1" in storage.state["processed_uuids"]


def test_run_once_dedupes_processed_uuids():
    zoom = FakeZoom([meeting("uuid-1", [zfile("M4A")])])
    storage = FakeStorage({"processed_uuids": ["uuid-1"], "last_pass_at": None})
    events = FakeEvents()
    poller = Poller(FakeConfig(), zoom, storage, events)

    assert poller.run_once() == 0
    assert zoom.downloads == []
    assert events.sent == []


def test_run_once_skips_meetings_without_media():
    zoom = FakeZoom([meeting("uuid-2", [zfile("TRANSCRIPT")])])
    storage = FakeStorage()
    events = FakeEvents()
    poller = Poller(FakeConfig(), zoom, storage, events)

    assert poller.run_once() == 0
    assert events.sent == []


def test_run_once_dry_run_downloads_nothing():
    zoom = FakeZoom([meeting("uuid-3", [zfile("M4A")])])
    storage = FakeStorage()
    poller = Poller(FakeConfig(), zoom, storage, None)

    assert poller.run_once(dry_run=True) == 1
    assert zoom.downloads == []
    assert not storage.saved
