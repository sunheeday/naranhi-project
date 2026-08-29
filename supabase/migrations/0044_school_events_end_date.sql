-- 연속 행사 기간(예: 시험기간 6/24~6/30, 대회 6/8~6/11)을 '진짜 범위'로 저장한다.
-- 단일 날짜는 end_date = null. 캘린더는 더 이상 근접 날짜를 추측 병합하지 않고,
-- 원문에 범위로 표현된 경우(추출 normalized에 ISO 2개)에만 end_date가 채워진다.
alter table public.school_events
  add column if not exists end_date date;
