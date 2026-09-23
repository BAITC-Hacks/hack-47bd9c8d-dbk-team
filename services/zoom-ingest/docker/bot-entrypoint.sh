#!/bin/sh
set -e

# Виртуальное звуковое устройство: браузер играет в него, ffmpeg слушает monitor.
pulseaudio -D --exit-idle-time=-1 --disallow-exit
pactl load-module module-null-sink sink_name=zoom_capture \
  sink_properties=device.description=ZoomCapture
pactl set-default-sink zoom_capture

exec python -m zoom_ingest bot "$@"
