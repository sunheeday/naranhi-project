begin;

-- safety: school_id 없는 행이 있으면 중단
do $$
begin
  if exists (select 1 from public.notices where school_id is null limit 1) then
    raise exception 'ABORT: notices rows with null school_id found';
  end if;
end;
$$;

-- ── indexes ───────────────────────────────────────────────────────────────────
-- source 컬럼 포함된 구 인덱스 제거
drop index if exists public.notices_crawl_source_uid_uidx;
drop index if exists public.notices_crawl_detail_url_uidx;

-- source 없는 학교 기반 중복방지 인덱스 재생성
create unique index if not exists notices_school_post_uid_uidx
  on public.notices (school_id, source_post_uid)
  where source_post_uid is not null;

create unique index if not exists notices_school_detail_url_uidx
  on public.notices (school_id, detail_url)
  where detail_url is not null;

-- ── RLS policies ──────────────────────────────────────────────────────────────
-- child_id 기반 정책 제거 (child_id 컬럼 삭제 예정)
drop policy if exists "notices select own child" on public.notices;
drop policy if exists "notices insert own child" on public.notices;
drop policy if exists "notices update own child" on public.notices;
drop policy if exists "notices delete own child" on public.notices;

-- notice_ai_translations 의 구 child 기반 정책 제거
-- (테이블이 없는 환경(로컬)에서도 안전하게 처리)
do $$
begin
  if exists (
    select 1 from pg_class
    where relname = 'notice_ai_translations'
      and relnamespace = 'public'::regnamespace
  ) then
    drop policy if exists "notice ai translations select own notice" on public.notice_ai_translations;
  end if;
end;
$$;

-- "notices select own school" 은 0003에서 이미 생성됨 — 추가 불필요

-- notice_cards 정책을 school_id 기반으로 교체
drop policy if exists "notice cards select own notice" on public.notice_cards;

create policy "notice cards select own school"
  on public.notice_cards for select
  using (
    exists (
      select 1
      from public.notices
      join public.children on children.school_id = notices.school_id
      where notices.id = notice_cards.notice_id
        and children.user_id = auth.uid()
    )
  );

-- ── document_files 테이블 먼저 제거 (notices.child_id 참조 정책 포함) ──────────
drop table if exists public.document_files;

-- ── drop columns ──────────────────────────────────────────────────────────────
-- 주의: summary_translations 는 프론트/타입 호환 위해 유지 (v4 plan)
alter table public.notices
  drop column if exists child_id,
  drop column if exists source,
  drop column if exists source_post_id,
  drop column if exists storage_path,
  drop column if exists created_by;

-- ── school_id: NOT NULL 설정 + FK ON DELETE RESTRICT 으로 변경 ────────────────
alter table public.notices
  drop constraint if exists notices_school_id_fkey;

alter table public.notices
  alter column school_id set not null;

alter table public.notices
  add constraint notices_school_id_fkey
    foreign key (school_id) references public.schools(id) on delete restrict;

-- ── notice_source enum 제거 ───────────────────────────────────────────────────
drop type if exists public.notice_source;

-- ── storage bucket 정책 제거 ─────────────────────────────────────────────────
-- bucket 자체는 Supabase Dashboard > Storage 에서 수동으로 삭제할 것
drop policy if exists "notice originals upload own folder" on storage.objects;
drop policy if exists "notice originals read own folder" on storage.objects;
drop policy if exists "notice originals delete own folder" on storage.objects;

commit;
