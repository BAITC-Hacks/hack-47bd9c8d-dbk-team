/**
 * Языки протокола. Отдельно от lib/translate.ts намеренно: перевод тянет
 * клиент объектного хранилища и работает только на сервере, а список языков
 * нужен и переключателю в браузере. Импорт серверного модуля из клиентского
 * компонента затягивает в бандл node-модули и ломает сборку.
 */
export const LANGUAGES = {
  ru: "русский",
  kk: "казахский",
  en: "английский",
} as const;

export type Lang = keyof typeof LANGUAGES;

export function isLang(value: unknown): value is Lang {
  return typeof value === "string" && value in LANGUAGES;
}
