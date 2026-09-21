// 시연(우회) 모드의 «각자 화면» 쿠키 규칙. Node 내장 테스트 러너 — `npm run test:unit`.
// 쿠키는 사용자가 마음대로 고칠 수 있으므로, 읽을 때 이상한 값을 거르는지가 핵심이다.
import { test } from 'node:test'
import assert from 'node:assert/strict'

import {
  MAX_DEMO_SCHEDULES,
  MAX_HIDDEN_NOTICES,
  isNoticeId,
  parseDemoBellTimes,
  parseDemoSchedules,
  parseHiddenNoticeIds,
  serializeDemoSchedules,
} from '../demo-cookies.ts'

const item = (over: Record<string, unknown> = {}) => ({
  id: 'a1',
  title: '태권도',
  dayOfWeek: 1,
  startTime: '16:00',
  endTime: '17:00',
  location: null,
  memo: null,
  color: 'blue',
  ...over,
})

// ── 시각 3칸 ────────────────────────────────────────────────────────────────────

test('쿠키가 없으면 보정 없음(원래 표 그대로)', () => {
  assert.deepEqual(parseDemoBellTimes(undefined), { offsetMinutes: 0, breakMinutes: null, lunchMinutes: null })
})

test('정상 값은 그대로 읽는다', () => {
  const raw = JSON.stringify({ offsetMinutes: -10, breakMinutes: 5, lunchMinutes: 40 })
  assert.deepEqual(parseDemoBellTimes(raw), { offsetMinutes: -10, breakMinutes: 5, lunchMinutes: 40 })
})

test('0 은 «안 넣음(null)» 과 구분된다', () => {
  const parsed = parseDemoBellTimes(JSON.stringify({ offsetMinutes: 0, breakMinutes: 0, lunchMinutes: 0 }))
  assert.equal(parsed.breakMinutes, 0)
  assert.equal(parsed.lunchMinutes, 0)
})

test('범위 밖 값은 DB 제약과 같은 기준으로 버린다', () => {
  const parsed = parseDemoBellTimes(JSON.stringify({ offsetMinutes: 999, breakMinutes: -1, lunchMinutes: 500 }))
  assert.deepEqual(parsed, { offsetMinutes: 0, breakMinutes: null, lunchMinutes: null })
})

test('소수·문자열·null 은 버린다', () => {
  const parsed = parseDemoBellTimes(JSON.stringify({ offsetMinutes: 1.5, breakMinutes: '5', lunchMinutes: null }))
  assert.deepEqual(parsed, { offsetMinutes: 0, breakMinutes: null, lunchMinutes: null })
})

test('깨진 JSON·배열·숫자는 기본값으로 돌아간다', () => {
  for (const raw of ['{{{', '[]', '123', 'null', '"x"']) {
    assert.deepEqual(parseDemoBellTimes(raw), { offsetMinutes: 0, breakMinutes: null, lunchMinutes: null }, raw)
  }
})

// ── 방과후 일정 ─────────────────────────────────────────────────────────────────

test('일정은 요일·시작 시각 순으로 정렬된다', () => {
  const raw = JSON.stringify([
    item({ id: 'c', dayOfWeek: 3, startTime: '15:00', endTime: '16:00' }),
    item({ id: 'b', dayOfWeek: 1, startTime: '17:00', endTime: '18:00' }),
    item({ id: 'a', dayOfWeek: 1, startTime: '09:00', endTime: '10:00' }),
  ])
  assert.deepEqual(parseDemoSchedules(raw).map(i => i.id), ['a', 'b', 'c'])
})

test('배열이 아니면 빈 목록', () => {
  for (const raw of [undefined, '', '{}', '"x"', '{{{']) {
    assert.deepEqual(parseDemoSchedules(raw), [], String(raw))
  }
})

test('규칙에 어긋난 일정은 하나만 골라 버린다', () => {
  const raw = JSON.stringify([
    item({ id: 'ok' }),
    item({ id: 'no-title', title: '   ' }),
    item({ id: 'bad-time', startTime: '25:00' }),
    item({ id: 'end-before', startTime: '17:00', endTime: '16:00' }),
    item({ id: 'same-time', startTime: '16:00', endTime: '16:00' }),
    item({ id: 'bad-day', dayOfWeek: 7 }),
    item({ id: 'float-day', dayOfWeek: 1.5 }),
    item({ id: '' }),
    'not-an-object',
    null,
  ])
  assert.deepEqual(parseDemoSchedules(raw).map(i => i.id), ['ok'])
})

test('모르는 색은 blue, 긴 장소·메모는 잘린다', () => {
  const raw = JSON.stringify([
    item({ color: 'neon', location: 'ㄱ'.repeat(200), memo: 'ㄴ'.repeat(500) }),
  ])
  const [only] = parseDemoSchedules(raw)
  assert.equal(only.color, 'blue')
  assert.equal(only.location?.length, 60)
  assert.equal(only.memo?.length, 120)
})

test('개수 상한을 넘는 쿠키는 앞의 상한까지만 읽는다', () => {
  const many = Array.from({ length: MAX_DEMO_SCHEDULES + 10 }, (_, i) => item({ id: `id-${i}` }))
  assert.equal(parseDemoSchedules(JSON.stringify(many)).length, MAX_DEMO_SCHEDULES)
})

test('저장할 일정이 작으면 문자열을 돌려준다', () => {
  const json = serializeDemoSchedules(parseDemoSchedules(JSON.stringify([item()])))
  assert.ok(json && json.includes('태권도'))
})

test('개수 상한을 넘으면 null — 저장을 막는다', () => {
  const many = Array.from({ length: MAX_DEMO_SCHEDULES + 1 }, (_, i) => item({ id: `id-${i}` }))
  assert.equal(serializeDemoSchedules(many as never), null)
})

test('쿠키 크기(약 4KB)를 넘으면 null — 브라우저가 조용히 버리기 전에 막는다', () => {
  // 한글은 URL 인코딩되면 글자당 9바이트라 긴 제목·메모 몇 개면 4KB 를 넘는다.
  const big = Array.from({ length: 5 }, (_, i) =>
    item({ id: `big-${i}`, title: '가'.repeat(60), memo: '나'.repeat(120), location: '다'.repeat(60) }),
  )
  assert.equal(serializeDemoSchedules(parseDemoSchedules(JSON.stringify(big))), null)
})

// ── 숨긴 공지 ───────────────────────────────────────────────────────────────────

const U1 = '0d0b8f4c-76a0-4baf-9f41-8f7c2a7d0001'
const U2 = '0d0b8f4c-76a0-4baf-9f41-8f7c2a7d0002'

test('UUID 만 남기고 나머지는 버린다', () => {
  const raw = JSON.stringify([U1, 'abc', 123, null, '<script>', U2])
  assert.deepEqual(parseHiddenNoticeIds(raw), [U1, U2])
})

test('숨김 목록 상한', () => {
  const ids = Array.from({ length: MAX_HIDDEN_NOTICES + 5 }, (_, i) =>
    `0d0b8f4c-76a0-4baf-9f41-${String(i).padStart(12, '0')}`,
  )
  assert.equal(parseHiddenNoticeIds(JSON.stringify(ids)).length, MAX_HIDDEN_NOTICES)
})

test('깨진 쿠키는 빈 목록', () => {
  for (const raw of [undefined, '{{{', '{}', '"x"']) {
    assert.deepEqual(parseHiddenNoticeIds(raw), [], String(raw))
  }
})

test('공지 id 는 UUID 만 인정한다 — 서버 액션 인자가 조작돼도 쿠키에 못 들어간다', () => {
  assert.equal(isNoticeId(U1), true)
  for (const bad of ['', 'abc', '<script>', 'x'.repeat(5000), 123, null, undefined, {}, [U1]]) {
    assert.equal(isNoticeId(bad), false, String(bad).slice(0, 20))
  }
})
