-- NEIS SchoolSchedule(학교 공식 학사일정)을 공지 본문 AI 역추출 일정과 같은 테이블에
-- 공존시킨다. 둘은 서로를 포함하지 않는 다른 정보다 — 어느 한쪽을 버리면 정보가 준다.
--
-- 새 테이블로 나누지 않는 이유: 캘린더 쿼리가 하나로 남고(app/(app)/calendar/page.tsx:104-110),
-- RLS 정책이 이미 school_id 기준이며(0017), end_date(0044)·event_kinds(0028) 를 그대로 재사용한다.
--
-- 기존 행은 전부 공지에서 나왔으므로 기본값이 'notice_ai' 다 — 백필이 필요 없다.
alter table public.school_events
  add column if not exists source text not null default 'notice_ai';

-- NEIS 일정에는 이어 붙일 공지가 없다.
alter table public.school_events
  alter column notice_id drop not null;

do $$
begin
  if not exists (
    select 1
    from pg_constraint
    where conname = 'school_events_source_check'
      and conrelid = 'public.school_events'::regclass
  ) then
    alter table public.school_events
      add constraint school_events_source_check
      check (source in ('notice_ai', 'neis'));
  end if;
end;
$$;

-- notice_id 가 null 이면 unique (notice_id, event_date)(0029) 가 무력하다
-- (postgres 에서 null 은 서로 distinct). NEIS 행 전용 부분 유니크로 재실행을 막는다.
create unique index if not exists school_events_neis_uidx
on public.school_events (school_id, event_date, title)
where source = 'neis';

create index if not exists school_events_school_source_date_idx
on public.school_events (school_id, source, event_date);
