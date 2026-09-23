import { NextResponse } from "next/server";
import { listOutbox, mailConfigured, runNotifications } from "@/lib/notifications";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

// Сценарий 2: проверка сроков и рассылка напоминаний. Вызывается интерфейсом
// при открытии вкладки контроля и годится как цель для внешнего планировщика
// (cron, Kubernetes CronJob) — состояние отправки хранится в самом поручении,
// поэтому повторный вызов не шлёт одно и то же дважды.
export async function POST() {
  const fresh = await runNotifications(Date.now());
  return NextResponse.json({
    sent: fresh.filter((e) => e.state === "sent").length,
    pending: fresh.filter((e) => e.state === "pending").length,
    failed: fresh.filter((e) => e.state === "failed").length,
    mail_configured: mailConfigured(),
    outbox: listOutbox().slice(0, 50),
  });
}

export async function GET() {
  return NextResponse.json({
    mail_configured: mailConfigured(),
    outbox: listOutbox().slice(0, 50),
  });
}
