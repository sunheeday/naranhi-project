-- 공지의 "제출/행동 마감일"을 구조화해 저장한다.
-- LLM이 이미 hard_facts.deadlines(normalized YYYY-MM-DD)로 마감일을 추출하므로,
-- 그중 가장 이른 날짜를 notices.due_date에 저장해 홈 화면 D-day에 직접 사용한다.
-- (schedules.event_date는 '행사일+마감일'이 섞여 있어 마감일 식별에 부적합하다.)
alter table public.notices
  add column if not exists due_date date;

create index if not exists notices_due_date_idx
on public.notices (due_date)
where due_date is not null;
