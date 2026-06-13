-- 시간표 과목명 즉석 번역 영구 캐시.
-- 정적 사전(lib/subject-dictionary.ts)에 없는 과목을 백엔드 Gemini로 1회 번역한 뒤
-- 여기에 저장한다 → 같은 과목은 앱 전체에서 평생 1회만 번역(429 쿼터 보호).
-- meals 테이블과 동일한 "전역 공유 캐시" 패턴: authenticated read, service role write.

create table public.subject_translations (
  ko_subject text not null,        -- 정규화된 base 한글(레벨 접미사 제외)
  locale     text not null,        -- en | zh | ar | ru | vi (확장 가능)
  translated text not null,
  created_at timestamptz not null default now(),
  primary key (ko_subject, locale)
);

alter table public.subject_translations enable row level security;

create policy "subject_translations select authenticated"
on public.subject_translations for select
to authenticated
using (true);

-- 쓰기(UPSERT)는 service role 전용 → 별도 insert/update 정책을 두지 않는다(meals 패턴).
