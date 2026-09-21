-- 자녀 개인 일정(학원·피아노·태권도 등 주간 반복).
--
-- 학교 시간표는 «교시»로 오지만 학원은 "16:00"이지 "N교시"가 아니다.
-- 그래서 교시 번호로 매핑하지 않고 절대 시각(start_time/end_time)으로 따로 담는다.
-- 기능명세서-자녀-개인일정.md §2 결정 ③.
create table if not exists public.child_personal_schedules (
  id uuid primary key default gen_random_uuid(),
  child_id uuid not null references public.children(id) on delete cascade,

  title text not null,
  -- 0=일 ~ 6=토. JS getUTCDay() 및 messages 의 calendar.weekdays 배열 인덱스와 같다.
  -- DB 는 0~6 을 다 허용하되 v1 화면은 월~금만 보여준다.
  day_of_week smallint not null check (day_of_week between 0 and 6),
  start_time time not null,
  end_time time not null,
  location text,
  memo text,
  -- 팔레트 키만 받는다. 자유 hex 를 허용하면 다크 모드에서 읽히지 않는 조합이 생긴다.
  color text not null default 'blue'
    check (color in ('blue', 'green', 'orange', 'purple', 'pink')),

  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),

  constraint child_personal_schedules_time_order check (start_time < end_time)
);

create index if not exists child_personal_schedules_child_day_idx
  on public.child_personal_schedules (child_id, day_of_week);

drop trigger if exists child_personal_schedules_set_updated_at on public.child_personal_schedules;
create trigger child_personal_schedules_set_updated_at
before update on public.child_personal_schedules
for each row execute function public.set_updated_at();

-- 별도 user_id 컬럼을 두지 않고 children 을 조인해 소유권을 본다 —
-- notices/notice_cards 등 기존 child 소유 리소스와 같은 방식이다(중복·불일치 방지).
-- school_events 는 시스템이 만들어 for select 지만, 개인 일정은 부모가 직접
-- 만들고 고치고 지우므로 for all 이다.
alter table public.child_personal_schedules enable row level security;

do $$
begin
  if not exists (
    select 1 from pg_policies
    where schemaname = 'public'
      and tablename = 'child_personal_schedules'
      and policyname = 'child personal schedules manage own child'
  ) then
    create policy "child personal schedules manage own child"
    on public.child_personal_schedules for all
    using (
      exists (
        select 1 from public.children
        where children.id = child_personal_schedules.child_id
          and children.user_id = auth.uid()
      )
    )
    with check (
      exists (
        select 1 from public.children
        where children.id = child_personal_schedules.child_id
          and children.user_id = auth.uid()
      )
    );
  end if;
end;
$$;
