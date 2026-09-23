import { randomUUID } from "crypto";
import { NextResponse } from "next/server";
import { config } from "@/lib/config";
import { publishUploaded } from "@/lib/kafka";
import { putRecording } from "@/lib/minio";
import { setStatus } from "@/lib/store";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const ACCEPTED_EXTENSIONS = [
  ".mp3",
  ".m4a",
  ".mp4",
  ".wav",
  ".ogg",
  ".flac",
  ".webm",
];

export async function POST(req: Request) {
  const form = await req.formData();
  const file = form.get("file");
  const vtt = form.get("vtt");

  if (!(file instanceof File) || file.size === 0) {
    return NextResponse.json(
      { error: "Прикрепите аудио- или видеофайл встречи." },
      { status: 400 },
    );
  }

  const filename = file.name;
  const lower = filename.toLowerCase();
  if (!ACCEPTED_EXTENSIONS.some((ext) => lower.endsWith(ext))) {
    return NextResponse.json(
      {
        error: `Формат не поддерживается. Допустимо: ${ACCEPTED_EXTENSIONS.join(", ")}`,
      },
      { status: 400 },
    );
  }

  // Субтитры необязательны. Если они есть, обработчик берёт из них тайминги
  // и ИМЕНА говорящих вместо безымянной диаризации — поэтому находит их он
  // по суффиксу .transcript.vtt, под которым мы их и кладём.
  let vttFile: File | null = null;
  if (vtt instanceof File && vtt.size > 0) {
    if (!vtt.name.toLowerCase().endsWith(".vtt")) {
      return NextResponse.json(
        { error: "Субтитры должны быть файлом .vtt из Zoom." },
        { status: 400 },
      );
    }
    vttFile = vtt;
  }

  const meetingId = `m-${randomUUID().slice(0, 8)}`;
  const objectKey = `${meetingId}/${filename}`;
  const baseName = filename.replace(/\.[^.]+$/, "");
  const vttKey = `${meetingId}/${baseName}.transcript.vtt`;

  if (config.mock) {
    setStatus({ meeting_id: meetingId, state: "processing" });
    return NextResponse.json({ meeting_id: meetingId, mock: true });
  }

  try {
    const buffer = Buffer.from(await file.arrayBuffer());
    await putRecording(
      objectKey,
      buffer,
      file.type || "application/octet-stream",
    );
    if (vttFile) {
      await putRecording(
        vttKey,
        Buffer.from(await vttFile.arrayBuffer()),
        "text/vtt",
      );
    }
    await publishUploaded({
      meeting_id: meetingId,
      object_key: objectKey,
      filename,
      lang_hint: config.langHint,
      has_vtt: Boolean(vttFile),
    });
    setStatus({ meeting_id: meetingId, state: "processing" });
    return NextResponse.json({ meeting_id: meetingId });
  } catch (err) {
    console.error("[upload] failed", err);
    return NextResponse.json(
      { error: "Не удалось отправить запись в обработку. Проверьте MinIO и Kafka." },
      { status: 502 },
    );
  }
}
