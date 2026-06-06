-- 아이별 종교/식이 금기 설정.
-- NEIS 급식 API는 종교 정보를 제공하지 않으므로, 보호자가 직접 선택한 금기를
-- 기준으로 급식 메뉴를 알레르기 코드 + 메뉴 이름 키워드로 추론해 경고를 표시한다.
-- 값 예시: {'halal','no_pork','no_beef','vegetarian','kosher'} (lib/dietary.ts 참조)
alter table public.children
  add column if not exists dietary_restrictions text[] not null default '{}';
