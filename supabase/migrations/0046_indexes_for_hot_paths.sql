-- 지금 필요해서가 아니라, 나중에 필요할 때 이미 있어야 하기 때문이다.
-- 운영 중 create index concurrently 는 트랜잭션 밖에서 돌아야 해서 마이그레이션
-- 파일에 넣기 까다롭다 — 지금(테이블이 작을 때) 넣어야 나중에 덜 고생한다.
--
-- 2026-08-29 supabase inspect db table-stats --linked (읽기 전용) 로 직접 잰 운영 행 수:
--   notices 44 / notice_cards 32 / notice_ai_translations 160 / app_jobs 231 / children 9
-- (계획서가 적어둔 notices 38 / notice_cards 29 / notice_ai_translations 155 / app_jobs 230 은
--  작성 시점 스냅샷이라 실측과 약간 다르다. 자릿수는 동일하게 두 자리~세 자리라 잠금 시간에
--  대한 결론은 바뀌지 않는다 — 아래 각주 참고.)
--
-- 전부 additive 이며 되돌리기는 drop index 한 줄이다.
--
-- CONCURRENTLY 를 쓰지 않는 이유: 모든 대상 테이블이 세 자리 이하 행이라(위 실측),
-- 일반 create index 의 짧은(수 ms급) ACCESS EXCLUSIVE 잠금이 무시할 만하고,
-- CONCURRENTLY 는 트랜잭션 안에서 실행할 수 없어 이 마이그레이션 러너(단일 트랜잭션)와
-- 충돌한다. 표에 실측된 인덱스 목록(supabase inspect db index-stats --linked)과 대조해
-- 아래 인덱스들이 기존과 겹치지 않음을 확인했다(각 항목 주석 참고).

-- 1) notice_cards 는 notice_id 로만 조회되는데(질문마다 카드 목록) PK 말고는 인덱스가
--    없었다(index-stats 로 확인: notice_cards_pkey 뿐). RLS 정책 "notice cards select own
--    school notice"(0008:10-22, 0001:190-206 의 원형)가 매 행마다
--    notices.id = notice_cards.notice_id 로 조인하고, 0001:61 의
--    "on delete cascade" 도 인덱스 없는 FK 라 부모 notices 삭제 시 전체 스캔이다.
create index if not exists notice_cards_notice_id_idx
  on public.notice_cards (notice_id);

-- 2) children(user_id) 단독 조회 — lib/server-cache.ts:97(getLatestChildForUser),
--    lib/server-cache.ts:119(getChildrenForUser) 둘 다 .eq('user_id', userId) 뿐,
--    school_id 조건이 없다.
--    기존 children_user_school_id_idx 는 (user_id, school_id) WHERE school_id IS NOT NULL
--    부분 인덱스(0003:13-15)라, 조건 없는 WHERE user_id = ? 는 부분 조건(school_id IS NOT
--    NULL)을 증명하지 못해 플래너가 못 탄다. 부분 조건을 떼어 재생성하면 선두 컬럼
--    단독 조회도 태울 수 있다.
--    (별도의 children(user_id) 단일 인덱스는 만들지 않는다 — 아래 복합 인덱스의
--     선두 컬럼이라 중복이다.)
drop index if exists public.children_user_school_id_idx;
create index if not exists children_user_school_id_idx
  on public.children (user_id, school_id);

-- 3) children(school_id) 단독 — backend/app/services/content_extraction_service.py:1041-1050
--    (_school_translation_locales: children 을 select user_id where school_id=? 로 조회)과
--    RLS "school events select own school"(0017:86-95, school_events.school_id =
--    children.school_id 로 조인). 복합 인덱스의 선두 컬럼이 아니라 못 탄다.
create index if not exists children_school_id_idx
  on public.children (school_id);

-- 4) 홈 목록 — app/(app)/page.tsx:217-222 의
--    .eq('school_id', child.school_id).eq('status', 'done')
--    .order('created_at', { ascending: false }).limit(50)
--    기존 notices_school_id_idx(0003:17-19, school_id 단일, WHERE school_id IS NOT NULL 부분)는
--    status 필터·created_at 정렬이 인덱스 밖이라 정렬은 별도 스캔이 된다.
create index if not exists notices_school_status_created_idx
  on public.notices (school_id, status, created_at desc);

-- 5) 추출 큐 스캔 — status IN ('pending','error','processing') 형태로 세 값을 한 번에
--    묻는 경로가 있는데, 0007 의 부분 인덱스 둘(notices_extraction_claim_idx: status IN
--    ('pending','error'), notices_extraction_stale_processing_idx: status = 'processing')은
--    각각 자기 부분 조건과 정확히 일치하는 조회에만 쓰이고, 세 값을 함께 묻는 조회에는
--    어느 쪽도 증명되지 않아 시퀀셜 스캔이 된다.
create index if not exists notices_status_created_idx
  on public.notices (status, created_at);

-- 6) 완료된 잡을 job_key 로 되짚는 경로 —
--    backend/app/services/job_queue_service.py:101-117(completed_recently:
--    .eq('job_key', job_key).eq('status', 'completed').gte('finished_at', cutoff)) 과
--    :119-133(latest_job: .eq('job_key', job_key).order('created_at', desc=True).limit(1)).
--    기존 app_jobs_active_job_key_idx 는 WHERE status IN ('queued','processing') 부분
--    유니크 인덱스(0027:22-24)라 completed 상태 잡은 그 밖에 있어 못 탄다.
create index if not exists app_jobs_job_key_created_idx
  on public.app_jobs (job_key, created_at desc);

-- 7) stale 'processing' 잡 회수 —
--    backend/app/services/job_queue_service.py:135-157(reclaim_stale_jobs:
--    .in_('job_type', job_types).eq('status', 'processing').lt('started_at', cutoff)).
--    기존 app_jobs_type_status_available_idx(job_type, status, available_at, created_at,
--    0027:19-20)는 available_at·created_at 만 있어 started_at 조건은 인덱스 밖이다.
create index if not exists app_jobs_started_at_idx
  on public.app_jobs (started_at);
