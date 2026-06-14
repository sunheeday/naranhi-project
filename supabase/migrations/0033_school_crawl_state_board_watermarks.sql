-- 정기 크롤 증분수집(watermark): 게시판(board_key)별 "마지막으로 본 최대 글번호"를 기록한다.
-- 다음 크롤은 이 값보다 큰 글만 신규로 처리 → 캐시 트림으로 삭제된 옛 글(고정공지 등)이
-- 게시판에 남아 재추출되는 낭비를 막는다. 글번호가 신뢰 가능한 숫자 일련번호인 경우에만 적용.
alter table public.school_crawl_state
  add column if not exists board_watermarks jsonb not null default '{}'::jsonb;
