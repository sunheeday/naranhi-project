create table if not exists public.school_events (
  id uuid primary key default gen_random_uuid(),
  school_id uuid not null references public.schools(id) on delete cascade,
  notice_id uuid not null references public.notices(id) on delete cascade,
  title text not null,
  event_date date not null,
  location text,
  description text,
  source_language text not null default 'ko',
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (notice_id, event_date)
);

with ranked_schedules as (
  select
    notices.school_id,
    schedules.notice_id,
    coalesce(notices.title, schedules.title, '학교 일정') as title,
    schedules.event_date,
    null::text as location,
    nullif(btrim(split_part(coalesce(notices.original_text, ''), E'\n', 1)), '') as description,
    schedules.created_at,
    row_number() over (
      partition by schedules.notice_id, schedules.event_date
      order by schedules.created_at desc, schedules.id desc
    ) as rn
  from public.schedules
  join public.notices on notices.id = schedules.notice_id
  where notices.school_id is not null
)
insert into public.school_events (
  school_id,
  notice_id,
  title,
  event_date,
  location,
  description,
  source_language,
  created_at,
  updated_at
)
select
  school_id,
  notice_id,
  title,
  event_date,
  location,
  description,
  'ko',
  created_at,
  now()
from ranked_schedules
where rn = 1
on conflict (notice_id, event_date) do update
set
  school_id = excluded.school_id,
  title = excluded.title,
  location = excluded.location,
  description = excluded.description,
  updated_at = excluded.updated_at;

create index if not exists school_events_school_date_idx
on public.school_events (school_id, event_date);

create index if not exists school_events_notice_idx
on public.school_events (notice_id);

drop trigger if exists school_events_set_updated_at on public.school_events;

create trigger school_events_set_updated_at
before update on public.school_events
for each row execute function public.set_updated_at();

alter table public.school_events enable row level security;

do $$
begin
  if not exists (
    select 1
    from pg_policies
    where schemaname = 'public'
      and tablename = 'school_events'
      and policyname = 'school events select own school'
  ) then
    create policy "school events select own school"
    on public.school_events for select
    using (
      exists (
        select 1
        from public.children
        where children.school_id = school_events.school_id
          and children.user_id = auth.uid()
      )
    );
  end if;
end;
$$;
