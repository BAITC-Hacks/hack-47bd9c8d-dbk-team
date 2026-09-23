import { NextResponse } from "next/server";
import { config } from "@/lib/config";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function GET() {
  return NextResponse.json({
    ok: true,
    mock: config.mock,
    brokers: config.kafka.brokers,
    minio: `${config.minio.endPoint}:${config.minio.port}`,
  });
}
