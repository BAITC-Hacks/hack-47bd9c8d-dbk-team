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

  const meetingId = `m-${randomUUID().slice(0, 8)}`;
  const objectKey = `${meetingId}/${filename}`;

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
    await publishUploaded({
      meeting_id: meetingId,
      object_key: objectKey,
      filename,
      lang_hint: config.langHint,
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
