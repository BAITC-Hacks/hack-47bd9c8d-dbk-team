"use client";

/**
 * Какая встреча сейчас в работе — переживает обновление страницы.
 *
 * Состояние конвейера живёт на сервере (`lib/store.ts`, плюс восстановление
 * из MinIO в `/api/meetings/[id]/status`), а на клиенте оставалось только в
 * React: после F5 экран обработки пропадал, и человек думал, что запись
 * потерялась. Здесь хранится ровно то, чего серверу не узнать, — какую
 * встречу показывать этому браузеру.
 *
 * localStorage может быть недоступен: приватный режим, отключённые данные
 * сайта, SSR. Все обращения обёрнуты — потеря памяти между перезагрузками
 * хуже, чем её отсутствие, но она не должна ронять страницу.
 */

const KEY = "meeting-copilot:active";

export interface ActiveMeeting {
  meetingId: string;
  /** ISO-время начала обработки: таймер на экране считается от него. */
  startedAt: string;
}

export function readActiveMeeting(): ActiveMeeting | null {
  try {
    const raw = window.localStorage.getItem(KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as Partial<ActiveMeeting>;
    if (!parsed?.meetingId) return null;
    return {
      meetingId: parsed.meetingId,
      startedAt: parsed.startedAt ?? new Date().toISOString(),
    };
  } catch {
    return null;
  }
}

export function rememberActiveMeeting(meetingId: string, startedAt: string) {
  try {
    window.localStorage.setItem(KEY, JSON.stringify({ meetingId, startedAt }));
  } catch {
    // приватный режим или запрещённые данные сайта — работаем без памяти
  }
}

export function forgetActiveMeeting() {
  try {
    window.localStorage.removeItem(KEY);
  } catch {
    // см. выше
  }
}
