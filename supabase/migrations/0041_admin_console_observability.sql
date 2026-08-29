-- 관측 기반: 크롤 실행 이력 + 번역 검토 신호.
--
-- 번호가 0039 가 아니라 0041인 이유: 스펙 §5.3 은 이 사업에 0039 를 배정했지만
-- 사업 E(RSS·공식 API)가 0039(school_events_source)와 0040(school_crawl_state_rss_feed)을
-- 이미 가져갔다. 0042~0044 는 비어 있고 사업 D 는 0045 부터 쓴다.
-- (2026-08-29 python scripts/check_migration_numbers.py 로 확인: 마이그레이션 42개, 번호 중복 없음)

-- ── ① 크롤 실행 이력 ─────────────────────────────────────────────
-- 지금은 요약이 stdout JSON 한 줄로만 나가고 사라진다
-- (scheduled_school_crawler.py:48, run_async 의 print(json.dumps(...))).
-- 역사적 성공률을 볼 유일한 데이터 소스가 된다.
--
-- 컬럼은 ScheduledCrawlerSummary(scheduled_crawler_service.py:61-76) 의 필드를
-- 그대로 담는다. 브리프는 "14개 키"라 했으나 실측 결과 필드는 15개다 —
-- fallback_count(게시판 오선택 카운트, :72·:346·:365, "게시판이 가정통신문이 아니라
-- 공지사항으로 대체됐다"는 신호)가 브리프 스니펫에서 빠져 있었다. 실패는 아니라서
-- success_rate/alarm 계산에는 안 들어가지만(:344-345 주석) 빠뜨리면 이 신호가
-- 화면에서 영구히 안 보이므로 추가했다.
--
-- outcome 이 왜 필요한가 — 두 가지 함정이 실측된 코드 동작이다:
--   ① scheduled_crawler_service.py:340-341 은 processed_count == 0 이면
--      success_rate 를 1.0 으로, alarm 을 False 로 만든다. 즉 «아무것도 안 돌았음» 이
--      «성공» 과 구별되지 않는다 → 'idle' 로 따로 기록한다(구분은 Task 8 이 processed_count
--      로 판정해서 채운다 — 이 마이그레이션은 CHECK 로 값만 확보한다).
--   ② exit 1 의 사유가 둘로 겹친다 — 성공률 미달(exit_code(), :81-82)과 크래시
--      (scheduled_school_crawler.py:58-71, main() 의 예외 처리 — 이 경로는
--      ScheduledCrawlerSummary 자체가 없다). exit code 로는 구별할 수 없다
--      → 'alarm' 과 'crashed' 로 나눈다.
--
-- 개인정보: 이 테이블에는 공지 제목·본문·학부모/학생 이름·연락처가 들어가지 않는다.
-- targets/results 는 school_id·school_name·상태 코드·개수만 담는 JSON이고
-- (ScheduledSchoolTarget.to_dict, ScheduledSchoolResult.to_dict), 학교명은 개별
-- 학생 식별자가 아니다. error_message 도 크롤러/시스템 예외 메시지
-- (`f"{type(exc).__name__}: {exc}"`, scheduled_school_crawler.py:65)이지 공지 본문이 아니다.
--
-- 보존 기간: 브리프에 지시 없어 직접 정한다. 하루 2회(06/18시,
-- .github/workflows/deploy-api-cloud-run.yml:138 "매일 06/18시 Cloud Scheduler")
-- 실행이라 연 730행 남짓 — 용량 위험이 없어 1년을 기본으로 잡는다. 자동 정리 잡은
-- 이번 범위 밖(브리프 미지정)이라 만들지 않는다. 필요해지면 관리자가 아래를 수동
-- 실행(또는 추후 별도 Task 에서 정기 잡화):
--   delete from public.crawl_run_history where created_at < now() - interval '1 year';
create table if not exists public.crawl_run_history (
  id uuid primary key default gen_random_uuid(),
  started_at timestamptz not null,
  finished_at timestamptz not null,
  outcome text not null,
  dry_run boolean not null default false,
  force boolean not null default false,
  total_registered integer not null default 0,
  selected_count integer not null default 0,
  skipped_count integer not null default 0,
  processed_count integer not null default 0,
  success_count integer not null default 0,
  failure_count integer not null default 0,
  fallback_count integer not null default 0,
  -- 이름은 CRAWLER_SCHEDULE_FAIL_RATE_THRESHOLD 지만 실제로는 «성공률» 과 비교한다
  -- (config.py:163-167, scheduled_crawler_service.py:341). 화면 라벨은 «성공률 임계치».
  success_rate numeric not null default 0,
  alarm boolean not null default false,
  targets jsonb not null default '[]'::jsonb,
  results jsonb not null default '[]'::jsonb,
  error_message text,
  created_at timestamptz not null default now(),
  constraint crawl_run_history_outcome_check
    check (outcome in ('ok', 'idle', 'alarm', 'crashed'))
);

create index if not exists crawl_run_history_created_idx
  on public.crawl_run_history (created_at desc);

-- 내부 운영 테이블. RLS 활성 + 정책 0개 = anon/authenticated 전면 차단, service_role 전용.
-- 선례 0013_school_crawl_state.sql:72, 0036_app_jobs_rls.sql
alter table public.crawl_run_history enable row level security;

-- ── ② 번역 검토 신호 ─────────────────────────────────────────────
-- 0012:6-10 이 requires_admin_review / admin_review_reason 를,
-- 0020:1-2 가 사유를 담던 metadata 를 지웠다. 남은 validation_status 는
-- 최종 번역문(final_translation)만 있으면 무조건 'passed' 로 덮어써진다
-- (notice_service.py:786-788). 안전장치는 동작하는데 출력을 받는 곳이 없다 —
-- 진짜 사유는 LOGGER.warning 한 줄(:790-795)로만 존재한다.
--
-- needs_review 는 사용자 노출을 바꾸지 않는다 — 번역문은 그대로 나가고
-- 검토 큐에도 «함께» 올라간다. review_reason 은 metadata.validation_failure_reason
-- 값을 담을 자리다 — 실측 결과 이 값은 자유서술문이 아니라 짧은 사유 코드다
-- ("quota_best_effort_fallback" notice_service.py:665,
--  "hard_fact_validation_failed" orchestrator.py:504) 이므로 공지 본문이 섞일 위험이 없다.
--
-- notice_ai_translations 는 이미 RLS + "자기 학교 공지만 select" 정책이 있다
-- (0008_school_notice_cards_policy.sql). 이 두 컬럼도 같은 행 단위 정책을 그대로
-- 물려받아 보호자에게도 보이게 된다 — 브리프가 "사용자 노출을 바꾸지 않는다"고 명시한
-- 그대로이고, 값 자체가 사유 코드일 뿐이라 노출 위험이 없다고 판단했다.
alter table public.notice_ai_translations
  add column if not exists needs_review boolean not null default false,
  add column if not exists review_reason text;

-- 0005:26-27 이 지웠던 검토 인덱스와 같은 역할. 검토 대상만 담는 부분 인덱스라
-- 전체 행 중 소수만 인덱싱된다.
create index if not exists notice_ai_translations_needs_review_idx
  on public.notice_ai_translations (needs_review)
  where needs_review;
