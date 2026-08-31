-- 학교별 교시 시각표. 한 교시가 한 행.
--
-- 파라미터(1교시 시작 + 수업 길이 + 쉬는 시간)로 계산하지 않는 이유:
-- 실측 일과표가 규칙적이지 않다. 부천부흥중 2026학년도 시정표를 보면
-- 4교시가 12:40에 끝나고 점심 뒤 5교시가 13:30에 «쉬는 시간 0분»으로 바로 붙는데,
-- 5→6, 6→7 은 10분씩 쉰다. 이 예외를 수식으로는 담을 수 없다.
-- 표준값도 같은 형태로 심으므로 읽는 쪽은 출처를 구분할 필요가 없다.
create table if not exists public.school_bell_schedules (
  id uuid primary key default gen_random_uuid(),
  school_id uuid not null references public.schools(id) on delete cascade,
  period smallint not null check (period between 1 and 12),
  start_time time not null,
  end_time time not null,
  -- 'default'  = 학교급 표준값(즉시 사용 가능한 추정치)
  -- 'homepage' = 홈페이지 일과표에서 수집(사람 승인 전까지 사용 금지)
  -- 'manual'   = 관리자 직접 입력
  source text not null default 'default'
    check (source in ('default', 'homepage', 'manual')),
  -- homepage 출처일 때 판독한 원본(대개 일과표 이미지) 주소. 승인 화면에서 대조용.
  source_url text,
  -- 승인 시각. null 이면 화면·알림 어디에서도 쓰지 않는다.
  -- AI 가 그림을 잘못 읽으면 틀린 하교 시각이 부모에게 알림으로 나간다.
  confirmed_at timestamptz,
  confirmed_by uuid references public.admin_users(id) on delete set null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint school_bell_schedules_time_order check (start_time < end_time),
  unique (school_id, period)
);

create index if not exists school_bell_schedules_school_idx
  on public.school_bell_schedules (school_id, period);

drop trigger if exists school_bell_schedules_set_updated_at on public.school_bell_schedules;
create trigger school_bell_schedules_set_updated_at
before update on public.school_bell_schedules
for each row execute function public.set_updated_at();

-- 부모는 자기 자녀가 다니는 학교 것만 «읽기». 쓰기는 service_role 만(관리자 콘솔 경유).
-- 한 부모의 수정이 같은 학교 다른 부모에게 번지면 안 되므로 부모 쓰기 정책은 두지 않는다.
alter table public.school_bell_schedules enable row level security;

do $$
begin
  if not exists (
    select 1 from pg_policies
    where schemaname = 'public'
      and tablename = 'school_bell_schedules'
      and policyname = 'bell schedules select own school'
  ) then
    create policy "bell schedules select own school"
    on public.school_bell_schedules for select
    using (
      exists (
        select 1 from public.children
        where children.school_id = school_bell_schedules.school_id
          and children.user_id = auth.uid()
      )
    );
  end if;
end;
$$;

-- 자녀별 시각 보정(분). 부모가 «우리 학교는 8시 50분에 시작해요» 하면 -10 이 들어간다.
-- 학교 공용 데이터를 건드리지 않고 그 자녀에게만 적용된다.
alter table public.children
  add column if not exists bell_offset_minutes smallint not null default 0;

alter table public.children
  drop constraint if exists children_bell_offset_range;
alter table public.children
  add constraint children_bell_offset_range
  check (bell_offset_minutes between -120 and 120);
