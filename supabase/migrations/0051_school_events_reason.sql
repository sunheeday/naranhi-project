-- 캘린더 카드에 «이 날짜가 무슨 날인지»(예: 체험비 납부 기간)를 보여주는 칸.
-- 공지 하나에서 날짜가 여러 개 나오면 제목·장소가 모두 공지 것이라 카드끼리 구분이 안 됐다
-- (notice_service._replace_school_events_from_pipeline 이 공지 제목·장소를 행마다 복사한다).
--
-- 보는 사람 언어별 값을 한 칸에 담는다: {"ko": "체험비 납부 기간", "en": "...", "zh": "...", ...}.
-- 비어 있으면(null) 카드에서 그 줄만 빠진다 — 기존 행은 그대로 둔다.
alter table public.school_events
  add column if not exists reason jsonb;
