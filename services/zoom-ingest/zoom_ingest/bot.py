import logging
import os
import re
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

from .config import Config
from .events import Events
from .storage import Storage

log = logging.getLogger("zoom_ingest.bot")

DEFAULT_BOT_NAME = "ИИ-секретарь (запись)"
CAPTURE_SINK = os.environ.get("ZOOM_BOT_PULSE_SINK", "zoom_capture")


def parse_invite(invite: str, passcode: str | None = None) -> tuple[str, str]:
    """Zoom invite URL or bare meeting id → (meeting_id, passcode)."""
    invite = invite.strip()
    match = re.search(r"(?:/j/|/wc/join/|/wc/)(\d{9,11})", invite)
    if match:
        meeting_id = match.group(1)
    elif re.fullmatch(r"[\d ]{9,13}", invite):
        meeting_id = invite.replace(" ", "")
    else:
        raise ValueError(f"Не похоже на ссылку или ID встречи Zoom: {invite!r}")
    if passcode is None:
        pwd = re.search(r"[?&]pwd=([^&]+)", invite)
        passcode = pwd.group(1) if pwd else ""
    return meeting_id, passcode


def build_join_url(meeting_id: str, passcode: str) -> str:
    url = f"https://zoom.us/wc/join/{meeting_id}"
    if passcode:
        url += f"?pwd={passcode}"
    return url


def build_ffmpeg_cmd(output_path: Path, sink: str = CAPTURE_SINK) -> list[str]:
    """Record the monitor of the PulseAudio null sink the browser plays into."""
    return [
        "ffmpeg", "-y",
        "-f", "pulse",
        "-i", f"{sink}.monitor",
        "-c:a", "libopus",
        "-b:a", "64k",
        str(output_path),
    ]


def make_meeting_id(meeting_id: str) -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    return f"zoom-live-{meeting_id}-{stamp}"


class MeetingBot:
    """Joins a Zoom meeting as a guest participant through the web client
    (headless Chromium), records mixed audio from a PulseAudio null sink,
    and pushes the file into the pipeline when the meeting ends.

    Runs inside Dockerfile.bot (chromium + pulseaudio + ffmpeg).
    Playwright is imported lazily — unit tests don't need it.
    """

    def __init__(self, config: Config, storage: Storage, events: Events | None):
        self._config = config
        self._storage = storage
        self._events = events

    def join_and_record(
        self,
        invite: str,
        name: str = DEFAULT_BOT_NAME,
        passcode: str | None = None,
        max_minutes: int = 180,
        output_dir: Path = Path("/tmp/zoom-bot"),
    ) -> str:
        from playwright.sync_api import sync_playwright

        meeting_id_num, pwd = parse_invite(invite, passcode)
        join_url = build_join_url(meeting_id_num, pwd)
        meeting_key = make_meeting_id(meeting_id_num)
        output_dir.mkdir(parents=True, exist_ok=True)
        audio_path = output_dir / f"{meeting_key}.webm"

        log.info("встреча %s → %s, вхожу как «%s»", meeting_id_num, meeting_key, name)
        ffmpeg = subprocess.Popen(
            build_ffmpeg_cmd(audio_path),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        try:
            self._attend(sync_playwright, join_url, name, max_minutes)
        finally:
            ffmpeg.terminate()
            try:
                ffmpeg.wait(timeout=15)
            except subprocess.TimeoutExpired:
                ffmpeg.kill()

        if not audio_path.exists() or audio_path.stat().st_size == 0:
            raise RuntimeError("Запись пуста — ffmpeg ничего не захватил.")

        data = audio_path.read_bytes()
        object_key = f"{meeting_key}/live.webm"
        self._storage.put_recording(object_key, data, "audio/webm")
        log.info("запись → %s (%d байт)", object_key, len(data))

        if self._events:
            self._events.publish_uploaded(
                meeting_id=meeting_key,
                object_key=object_key,
                filename="live.webm",
                lang_hint=self._config.lang_hint,
            )
        return meeting_key

    def _attend(self, sync_playwright, join_url: str, name: str, max_minutes: int) -> None:
        """Browser part: join and stay until the meeting ends or times out."""
        with sync_playwright() as pw:
            browser = pw.chromium.launch(
                headless=True,
                args=[
                    "--use-fake-ui-for-media-stream",
                    "--autoplay-policy=no-user-gesture-required",
                    "--no-sandbox",
                ],
            )
            page = browser.new_page()
            page.goto(join_url, wait_until="domcontentloaded")
            # Web client join form: name field + join button. Selectors drift
            # between Zoom releases — try the stable ones in order.
            name_input = page.locator(
                "input#input-for-name, input[placeholder*='name' i], "
                "input[placeholder*='имя' i]"
            ).first
            name_input.wait_for(timeout=60_000)
            name_input.fill(name)
            page.locator(
                "button#joinBtn, button:has-text('Join'), "
                "button:has-text('Присоединиться')"
            ).first.click()
            log.info("вошёл во встречу, записываю (макс. %d мин)", max_minutes)

            deadline = time.time() + max_minutes * 60
            while time.time() < deadline:
                if page.is_closed():
                    break
                # Meeting ended screens / host closed the room.
                if page.locator(
                    "text=/meeting has ended|встреча завершена|"
                    "host ended|organizer ended/i"
                ).count():
                    log.info("встреча завершена хостом")
                    break
                time.sleep(5)
            browser.close()
