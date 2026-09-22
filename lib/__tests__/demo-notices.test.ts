// 시연에 보여줄 공지의 기준. Node 내장 테스트 러너 — `npm run test:unit`.
import { test } from 'node:test'
import assert from 'node:assert/strict'

import {
  DEMO_EXCLUDED_NOTICE_IDS,
  DEMO_NOTICES_SINCE,
  DEMO_PINNED_NOTICES,
  demoPinnedNotice,
  isDemoNoticeVisible,
} from '../demo-notices.ts'

const AFTER = '2026-09-21T15:12:35.563992+00:00'
const BEFORE = '2026-08-28T10:00:00+00:00'

test('기준 시각 이후에 받은 공지는 보인다', () => {
  assert.equal(isDemoNoticeVisible({ id: 'a', created_at: AFTER }), true)
})

test('기준 시각 이전(예전) 공지는 감춘다', () => {
  assert.equal(isDemoNoticeVisible({ id: 'a', created_at: BEFORE }), false)
})

test('기준 시각과 정확히 같은 공지는 보인다', () => {
  assert.equal(isDemoNoticeVisible({ id: 'a', created_at: DEMO_NOTICES_SINCE }), true)
})

test('뺀 공지는 새 공지여도 감춘다', () => {
  for (const id of DEMO_EXCLUDED_NOTICE_IDS) {
    assert.equal(isDemoNoticeVisible({ id, created_at: AFTER }), false)
  }
})

test('시간대가 다른 표기도 같은 순간이면 같게 판정한다', () => {
  // 2026-09-22 00:30 +09:00 == 2026-09-21 15:30 UTC (기준보다 뒤)
  assert.equal(isDemoNoticeVisible({ id: 'a', created_at: '2026-09-22T00:30:00+09:00' }), true)
  // 2026-09-21 22:00 +09:00 == 13:00 UTC (기준보다 앞)
  assert.equal(isDemoNoticeVisible({ id: 'a', created_at: '2026-09-21T22:00:00+09:00' }), false)
})

test('날짜를 읽을 수 없으면 감춘다(실패하면 닫힘)', () => {
  assert.equal(isDemoNoticeVisible({ id: 'a', created_at: '' }), false)
  assert.equal(isDemoNoticeVisible({ id: 'a', created_at: 'not-a-date' }), false)
})

test('시연에서 뺀 공지는 함박초 1건 + 부천 9/21 공지 5건이다', () => {
  assert.equal(DEMO_EXCLUDED_NOTICE_IDS.length, 6)
  assert.ok(DEMO_EXCLUDED_NOTICE_IDS.includes('0e7127a2-72ab-4ef6-8cf0-b2f425eaa4a9'))
  assert.ok(DEMO_EXCLUDED_NOTICE_IDS.includes('4372115f-07a8-4b6e-b92b-a163aa862ec1'))
})

test('못 박은 부천 옛 공지는 기준 시각보다 앞서도 보인다', () => {
  for (const id of Object.keys(DEMO_PINNED_NOTICES)) {
    assert.equal(isDemoNoticeVisible({ id, created_at: BEFORE }), true)
  }
})

test('못 박은 공지는 5건이고 도착 표시는 2일·6일이다', () => {
  const ids = Object.keys(DEMO_PINNED_NOTICES)
  assert.equal(ids.length, 5)
  assert.deepEqual(
    ids.map(id => DEMO_PINNED_NOTICES[id].daysAgo).sort((a, b) => a - b),
    [2, 6, 6, 6, 6],
  )
})

test('마감 뱃지는 정기시험·줄넘기 둘만 붙는다', () => {
  assert.equal(demoPinnedNotice('c9e98a70-aa33-443a-b2a2-29939bc105fa')?.dueLabel, 'D-10 · 6/24')
  assert.equal(demoPinnedNotice('da2e340a-6011-409e-844e-97f5f9d061b0')?.dueLabel, 'D-5 · 6/19')
  assert.equal(demoPinnedNotice('38712f54-616d-445a-b146-3534a3bb3a41')?.dueLabel, null)
})

test('못 박지 않은 공지는 null 을 돌려준다', () => {
  assert.equal(demoPinnedNotice('a'), null)
})

test('못 박은 공지와 뺀 공지가 겹치지 않는다', () => {
  for (const id of Object.keys(DEMO_PINNED_NOTICES)) {
    assert.ok(!DEMO_EXCLUDED_NOTICE_IDS.includes(id))
  }
})
