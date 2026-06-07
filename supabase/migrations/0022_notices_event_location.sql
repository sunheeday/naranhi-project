alter table public.notices
  add column if not exists event_location text;
