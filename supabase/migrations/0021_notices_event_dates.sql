alter table public.notices
  add column if not exists event_dates jsonb not null default '[]'::jsonb;
