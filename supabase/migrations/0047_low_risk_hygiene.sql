-- (1) updated_at 컬럼은 있는데 트리거가 없어서 UPDATE 해도 값이 안 바뀌던 두 테이블.
--     notice_card_translations 는 코드도 수동으로 안 채우므로(notice_service 의 upsert
--     payload 에 updated_at 없음) 삽입 시각에 영원히 고정되어 있었다.
--     app_jobs 는 코드가 수동으로 채우지만 누락 경로가 있으면 조용히 stale 이 된다.
--     트리거가 덮어쓰므로 기존 수동 세팅은 그대로 둬도 무해하다.
drop trigger if exists notice_card_translations_set_updated_at on public.notice_card_translations;
create trigger notice_card_translations_set_updated_at
before update on public.notice_card_translations
for each row execute function public.set_updated_at();

drop trigger if exists app_jobs_set_updated_at on public.app_jobs;
create trigger app_jobs_set_updated_at
before update on public.app_jobs
for each row execute function public.set_updated_at();

-- (2) notice_cards 의 SELECT 정책이 논리적으로 동일한 것 둘이다.
--     0008:10-21 의 추가 조건 notices.school_id is not null 은 0006:81 이
--     school_id 를 NOT NULL 로 만든 이후 항상 참이다. PERMISSIVE 라 결과는 같지만
--     거의 같은 EXISTS 서브쿼리가 SELECT 마다 두 번 평가된다.
--     0009 가 idempotent 가드로 재생성까지 하는 0006/0009 쪽을 정본으로 남긴다.
drop policy if exists "notice cards select own school notice" on public.notice_cards;

-- (3) 유령 스토리지 버킷 notice-originals.
--     0001:243-254 가 만들고, 0006:92-94 가 정책 3개를 전부 지웠고,
--     유일한 참조 테이블 document_files 도 0006:65 가 drop 했다. 코드 참조 0건.
--     0006:91 주석이 스스로 "bucket 자체는 대시보드에서 수동으로 삭제할 것" 이라고
--     적어 두고 석 달간 안 지워졌다.
--
--     ⚠️ SQL 로는 못 지운다. storage.buckets 에 BEFORE DELETE «문장» 트리거
--     protect_buckets_delete 가 걸려 있어 storage.protect_delete() 가
--     42501 을 던진다. 문장 단위라 매칭 0행이어도 발사된다 —
--     `delete ... where id = ...` 를 어떤 가드로 감싸도 마이그레이션이 거기서 멈춘다.
--     운영에서는 Storage API(DELETE /storage/v1/bucket/notice-originals)로 지웠다.
--     새 환경을 세울 때도 같은 방법을 쓴다. 여기서는 남은 오브젝트만 확인해 둔다.
do $$
declare
  leftover integer;
begin
  select count(*) into leftover
  from storage.objects
  where bucket_id = 'notice-originals';

  if leftover > 0 then
    raise exception 'notice-originals 버킷에 오브젝트가 %개 남아 있습니다. 먼저 비우세요.', leftover;
  end if;
end $$;
