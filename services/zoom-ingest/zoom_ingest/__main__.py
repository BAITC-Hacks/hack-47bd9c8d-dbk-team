import argparse
import logging
import sys
import time
from pathlib import Path

from .bot import DEFAULT_BOT_NAME, MeetingBot
from .config import load_config
from .events import Events
from .poller import Poller
from .storage import Storage
from .zoom_client import ZoomClient


def build_infra(config, with_events: bool = True):
    storage = Storage(
        endpoint=config.minio_endpoint,
        access_key=config.minio_access_key,
        secret_key=config.minio_secret_key,
        secure=config.minio_secure,
        recordings_bucket=config.recordings_bucket,
        state_bucket=config.state_bucket,
    )
    events = (
        Events(config.kafka_brokers, config.topic_uploaded) if with_events else None
    )
    return storage, events


def main() -> int:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(name)s %(message)s"
    )
    parser = argparse.ArgumentParser(prog="zoom_ingest")
    sub = parser.add_subparsers(dest="command", required=True)

    poll = sub.add_parser("poll", help="забрать облачные записи постфактум")
    poll.add_argument("--once", action="store_true", help="один проход и выход")
    poll.add_argument(
        "--dry-run",
        action="store_true",
        help="показать, что было бы загружено, без скачивания и событий",
    )

    bot = sub.add_parser("bot", help="войти во встречу участником и записать")
    bot.add_argument("invite", help="ссылка-приглашение или ID встречи")
    bot.add_argument("--name", default=DEFAULT_BOT_NAME)
    bot.add_argument("--passcode", default=None)
    bot.add_argument("--max-minutes", type=int, default=180)
    bot.add_argument("--output-dir", type=Path, default=Path("/tmp/zoom-bot"))

    args = parser.parse_args()
    config = load_config()

    if args.command == "poll":
        zoom = ZoomClient(
            config.zoom_account_id,
            config.zoom_client_id,
            config.zoom_client_secret,
        )
        storage, events = build_infra(config, with_events=not args.dry_run)
        poller = Poller(config, zoom, storage, events)
        if args.once or args.dry_run:
            poller.run_once(dry_run=args.dry_run)
        else:
            while True:
                try:
                    poller.run_once()
                except Exception:
                    logging.getLogger("zoom_ingest").exception(
                        "проход упал, повтор через %d c", config.poll_interval_sec
                    )
                time.sleep(config.poll_interval_sec)
        if events:
            events.close()
        return 0

    if args.command == "bot":
        storage, events = build_infra(config)
        bot_runner = MeetingBot(config, storage, events)
        meeting_key = bot_runner.join_and_record(
            args.invite,
            name=args.name,
            passcode=args.passcode,
            max_minutes=args.max_minutes,
            output_dir=args.output_dir,
        )
        print(meeting_key)
        if events:
            events.close()
        return 0

    return 1


if __name__ == "__main__":
    sys.exit(main())
