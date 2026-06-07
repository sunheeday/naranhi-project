create table if not exists public.school_crawl_state (
  school_id uuid primary key references public.schools(id) on delete cascade,
  crawl_board_url text,
  crawl_board_kind text not null default 'unknown',
  crawl_status text not null default 'pending',
  crawl_error_message text,
  crawl_result jsonb not null default '{}'::jsonb,
  crawl_last_checked_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

do $$
begin
  if not exists (
    select 1
    from pg_constraint
    where conname = 'school_crawl_state_board_kind_check'
      and conrelid = 'public.school_crawl_state'::regclass
  ) then
    alter table public.school_crawl_state
      add constraint school_crawl_state_board_kind_check
      check (crawl_board_kind in ('family_notice', 'announcement_fallback', 'unknown'));
  end if;
end;
$$;

insert into public.school_crawl_state (
  school_id,
  crawl_board_url,
  crawl_board_kind,
  crawl_status,
  crawl_error_message,
  crawl_result,
  crawl_last_checked_at,
  created_at,
  updated_at
)
select
  id,
  crawl_board_url,
  crawl_board_kind,
  crawl_status,
  crawl_error_message,
  coalesce(crawl_result, '{}'::jsonb),
  crawl_last_checked_at,
  coalesce(created_at, updated_at, now()),
  coalesce(updated_at, created_at, now())
from public.schools
on conflict (school_id) do update
set
  crawl_board_url = excluded.crawl_board_url,
  crawl_board_kind = excluded.crawl_board_kind,
  crawl_status = excluded.crawl_status,
  crawl_error_message = excluded.crawl_error_message,
  crawl_result = excluded.crawl_result,
  crawl_last_checked_at = excluded.crawl_last_checked_at,
  updated_at = excluded.updated_at;

create index if not exists school_crawl_state_status_idx
on public.school_crawl_state (crawl_status);

create index if not exists school_crawl_state_last_checked_at_idx
on public.school_crawl_state (crawl_last_checked_at);

drop trigger if exists school_crawl_state_set_updated_at on public.school_crawl_state;

create trigger school_crawl_state_set_updated_at
before update on public.school_crawl_state
for each row execute function public.set_updated_at();

alter table public.school_crawl_state enable row level security;
