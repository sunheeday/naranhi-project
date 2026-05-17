alter table public.schools
  add column if not exists homepage_url text,
  add column if not exists crawl_board_url text,
  add column if not exists crawl_board_kind text not null default 'unknown',
  add column if not exists crawl_status text not null default 'pending',
  add column if not exists crawl_error_message text,
  add column if not exists crawl_result jsonb not null default '{}'::jsonb,
  add column if not exists crawl_last_checked_at timestamptz,
  add column if not exists updated_at timestamptz not null default now();

do $$
begin
  if not exists (
    select 1
    from pg_constraint
    where conname = 'schools_crawl_board_kind_check'
      and conrelid = 'public.schools'::regclass
  ) then
    alter table public.schools
      add constraint schools_crawl_board_kind_check
      check (crawl_board_kind in ('family_notice', 'announcement_fallback', 'unknown'));
  end if;
end;
$$;

create index if not exists schools_crawl_status_idx
on public.schools (crawl_status);

create index if not exists schools_crawl_last_checked_at_idx
on public.schools (crawl_last_checked_at);

drop trigger if exists schools_set_updated_at on public.schools;

create trigger schools_set_updated_at
before update on public.schools
for each row execute function public.set_updated_at();
