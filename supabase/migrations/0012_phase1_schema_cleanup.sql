-- Phase 1 schema cleanup:
-- - remove unused translation review columns
-- - remove unused schedule sync column
-- - remove unused profile role column and enum

drop index if exists public.notice_ai_translations_review_idx;

alter table public.notice_ai_translations
  drop column if exists requires_admin_review,
  drop column if exists admin_review_reason;

alter table public.schedules
  drop column if exists gcal_event_id;

alter table public.profiles
  drop column if exists role;

drop type if exists public.user_role;
