-- app_jobs 는 내부 작업 큐다. 0027 에서 테이블만 만들고 RLS 를 켜지 않아
-- anon 키로 payload/result/last_error 가 전부 조회되는 상태였다.
--
-- 정책은 만들지 않는다. RLS 활성 + 정책 0개 = anon/authenticated 전면 차단.
-- 접근 경로는 service_role(백엔드 job_queue_service, 운영 스크립트)뿐이고
-- service_role 은 RLS 를 우회하므로 동작에 영향이 없다.
-- 같은 성격의 내부 운영 테이블인 school_crawl_state(0013) 와 동일한 패턴이다.

alter table public.app_jobs enable row level security;
