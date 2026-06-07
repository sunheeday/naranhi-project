alter table public.notice_ai_translations
  drop column if exists source_text,
  drop column if exists ingredient_identity_map,
  drop column if exists validation,
  drop column if exists raw_pipeline;
