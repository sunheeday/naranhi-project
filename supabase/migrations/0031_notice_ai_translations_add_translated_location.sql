alter table public.notice_ai_translations
  add column if not exists translated_location text;
