"use client";

import { FileDown, Printer } from "lucide-react";
import { useState } from "react";
import { exportDocx } from "@/lib/export-docx";
import type { MeetingResult } from "@/lib/types";
import { Button } from "@/components/ui/button";

export function ExportButtons({ result }: { result: MeetingResult }) {
  const [busy, setBusy] = useState(false);

  async function handleDocx() {
    setBusy(true);
    try {
      await exportDocx(result);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex gap-2 print:hidden">
      <Button variant="secondary" onClick={handleDocx} disabled={busy}>
        <FileDown className="h-4 w-4" aria-hidden />
        {busy ? "Формирую…" : "Скачать DOCX"}
      </Button>
      <Button variant="secondary" onClick={() => window.print()}>
        <Printer className="h-4 w-4" aria-hidden />
        Печать / PDF
      </Button>
    </div>
  );
}
