-- 자녀별 쉬는 시간·점심시간 보정(분).
-- 0048 의 bell_offset_minutes(1교시 시작 보정)와 짝을 이룬다 — 부모가 세 칸까지 고친다.
-- null 이면 그 항목만 기존 표(홈페이지 판독본 또는 학교급 표준값)의 간격을 그대로 쓴다.
-- 학교 공용 데이터(school_bell_schedules)는 건드리지 않는다.
alter table public.children
  add column if not exists bell_break_minutes smallint;

alter table public.children
  add column if not exists bell_lunch_minutes smallint;

-- 상식 밖 값 차단. 쉬는 시간 0~60분, 점심 0~120분.
alter table public.children
  drop constraint if exists children_bell_break_range;
alter table public.children
  add constraint children_bell_break_range
  check (bell_break_minutes is null or bell_break_minutes between 0 and 60);

alter table public.children
  drop constraint if exists children_bell_lunch_range;
alter table public.children
  add constraint children_bell_lunch_range
  check (bell_lunch_minutes is null or bell_lunch_minutes between 0 and 120);
