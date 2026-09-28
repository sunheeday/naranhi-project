// 시연에 보여줄 공지의 기준. Node 내장 테스트 러너 — `npm run test:unit`.
import { test } from 'node:test'
import assert from 'node:assert/strict'

import { DEMO_EXCLUDED_NOTICE_IDS, DEMO_NOTICES_SINCE, isDemoNoticeVisible } from '../demo-notices.ts'

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

test('시연에서 뺀 공지는 학교마다 하나씩이다(부천 예방접종·함박초 우리학교365)', () => {
  assert.equal(DEMO_EXCLUDED_NOTICE_IDS.length, 2)
  assert.ok(DEMO_EXCLUDED_NOTICE_IDS.includes('0e7127a2-72ab-4ef6-8cf0-b2f425eaa4a9'))
  assert.ok(DEMO_EXCLUDED_NOTICE_IDS.includes('4372115f-07a8-4b6e-b92b-a163aa862ec1'))
})
