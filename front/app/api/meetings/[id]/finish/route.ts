import { NextResponse } from "next/server";
import { config } from "@/lib/config";
import { publishUploaded } from "@/lib/kafka";
import { putRecording } from "@/lib/minio";
import {
  assembleSession,
  dropSession,
  hasSession,
  missingSeqs,
} from "@/lib/recording-sessions";
import { setStatus } from "@/lib/store";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const MIME_EXT: Record<string, string> = {
  "audio/webm": "webm",
  "audio/mp4": "mp4",
  "audio/ogg": "ogg",
};

// Recording finished: assemble chunks → MinIO recordings/<id>/live.<ext>
// → Kafka meetings.uploaded (the "запись завершена" event of the contract).
export async function POST(
  _req: Request,
  { params }: { params: Promise<{ id: string }> },
) {
  const { id } = await params;
  if (!hasSession(id)) {
    return NextResponse.json(
      { error: "Сессия записи не найдена." },
      { status: 404 },
    );
  }

  const assembled = assembleSession(id);
  if (!assembled) {
    return NextResponse.json(
      { error: "Запись пуста — не получено ни одного чанка." },
      { status: 400 },
    );
  }

  const missing = missingSeqs(id);
  if (missing.length > 0) {
    return NextResponse.json(
      {
        error: `Потеряны фрагменты записи: ${missing.join(", ")}.`,
        missing,
      },
      { status: 409 },
    );
  }

  const baseMime = assembled.mime.split(";")[0];
  const ext = MIME_EXT[baseMime] ?? "webm";
  const filename = `live.${ext}`;
  const objectKey = `${id}/${filename}`;

  if (config.mock) {
    dropSession(id);
    setStatus({ meeting_id: id, state: "processing" });
    return NextResponse.json({ meeting_id: id, mock: true });
  }

  try {
    await putRecording(objectKey, assembled.data, assembled.mime);
    await publishUploaded({
      meeting_id: id,
      object_key: objectKey,
      filename,
      lang_hint: config.langHint,
    });
    dropSession(id);
    setStatus({ meeting_id: id, state: "processing" });
    return NextResponse.json({ meeting_id: id });
  } catch (err) {
    console.error("[finish] failed", err);
    return NextResponse.json(
      { error: "Не удалось сохранить запись. Проверьте MinIO и Kafka." },
      { status: 502 },
    );
  }
}
