import type { Metadata } from "next";
import "./globals.css";
import { RecordingNotice } from "@/components/recording-notice";

export const metadata: Metadata = {
  title: "AI Meeting Copilot — протокол встречи",
  description:
    "Загрузка записи встречи, автоматический транскрипт, поручения и саммари.",
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="ru" className="dark">
      <body className="min-h-screen bg-zinc-950 font-sans text-zinc-100 antialiased">
        <RecordingNotice />
        <header className="border-b border-zinc-800 px-6 py-4 print:hidden">
          <div className="mx-auto flex max-w-6xl items-center justify-between">
            <div>
              <div className="text-base font-semibold">AI Meeting Copilot</div>
              <div className="text-xs text-zinc-500">
                Запись → транскрипт → поручения → протокол
              </div>
            </div>
          </div>
        </header>
        <main className="mx-auto max-w-6xl px-6 py-8 print:max-w-none print:px-0 print:py-0">
          {children}
        </main>
      </body>
    </html>
  );
}
