-- 공지 첨부파일을 우리 Supabase Storage 에 보관한다(학교 서버 의존/차단 제거, 학교가 파일을
-- 내려도 우리 사본은 유지). 카드의 미리보기/다운로드는 이 버킷의 public URL 을 가리킨다.
--
-- 공개(public) 버킷: URL 을 알면 접근 가능(이번 단계는 보안 미적용 — 추후 비공개+서명URL 전환 가능).
-- 업로드는 백엔드(service_role)만 수행하므로 RLS 정책 없이도 동작한다(service_role 은 RLS 우회).
insert into storage.buckets (id, name, public)
values ('notice-attachments', 'notice-attachments', true)
on conflict (id) do nothing;
