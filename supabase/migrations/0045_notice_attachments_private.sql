-- 0011 이 이 버킷을 public 으로 만들면서 주석에 "보안 미적용" 이라고 스스로 적어 두었다.
-- 이제 앱이 접근 검사를 거쳐 단명(5분) 서명 URL 을 발급하므로
-- (app/api/notices/[noticeId]/attachments/[sourceId]) 버킷을 비공개로 돌린다.
--
-- storage.objects 정책은 추가하지 않는다(현재 0개 = service_role 전용 유지).
-- 서명 URL 발급이 service_role 로 이뤄지므로 정책이 필요 없다.

update storage.buckets
set public = false
where id = 'notice-attachments';
