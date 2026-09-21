// 캘린더 중복 제거 규칙. Node 내장 테스트 러너 — `npm run test:unit`.
import { test } from 'node:test'
import assert from 'node:assert/strict'

import { dedupeEventsByNoticeEnd } from '../calendar-events.ts'

type Kind = 'event' | 'deadline'
const ev = (
  id: string,
  noticeId: string | null,
  eventDate: string,
  endDate: string | null | undefined = null,
  eventKinds?: Kind[],
) => ({ id, noticeId, eventDate, endDate, eventKinds })
const ids = (list: { id: string }[]) => list.map(e => e.id)

test('예방접종 공지: 끝나는 날이 같은 세 행이 하나로, 다른 프로그램(10/5~11/21)은 그대로', () => {
  const rows = [
    ev('a', 'n1', '2026-09-21', '2027-04-30'),
    ev('b', 'n1', '2026-09-28', '2027-04-30'),
    ev('c', 'n1', '2026-10-05', '2026-11-21'),
    ev('d', 'n1', '2026-11-21', null),
    ev('e', 'n1', '2027-04-30', null),
  ]
  assert.deepEqual(ids(dedupeEventsByNoticeEnd(rows)), ['a', 'c'])
})

test('정기시험 공지: 기간 행과 그 마감일 단일 행은 하나로, 시험일·공개기간은 그대로', () => {
  const rows = [
    ev('open', 'n2', '2026-10-06', '2026-10-12'),
    ev('exam', 'n2', '2026-10-13', '2026-10-14'),
    ev('appeal', 'n2', '2026-10-15', '2026-10-16'),
    ev('appeal-deadline', 'n2', '2026-10-16', null),
  ]
  assert.deepEqual(ids(dedupeEventsByNoticeEnd(rows)), ['open', 'exam', 'appeal'])
})

test('서로 다른 공지의 같은 날짜는 둘 다 남긴다', () => {
  const rows = [ev('x', 'n1', '2026-10-01', '2026-10-05'), ev('y', 'n2', '2026-10-01', '2026-10-05')]
  assert.deepEqual(ids(dedupeEventsByNoticeEnd(rows)), ['x', 'y'])
})

test('공지에 묶이지 않은 행(NEIS 학사일정)은 같은 날이어도 건드리지 않는다', () => {
  const rows = [ev('s1', null, '2026-10-03'), ev('s2', null, '2026-10-03'), ev('n', 'n1', '2026-10-03')]
  assert.deepEqual(ids(dedupeEventsByNoticeEnd(rows)), ['s1', 's2', 'n'])
})

test('시작일이 앞선 행이 입력 순서상 뒤에 있어도 그 행이 남는다', () => {
  const rows = [ev('later', 'n1', '2026-09-28', '2027-04-30'), ev('earlier', 'n1', '2026-09-21', '2027-04-30')]
  assert.deepEqual(ids(dedupeEventsByNoticeEnd(rows)), ['earlier'])
})

test('시작일이 같으면 기간이 있는 행을 남긴다(입력 순서와 무관)', () => {
  const noEnd = ev('no-end', 'n1', '2026-10-20', null)
  const withEnd = ev('with-end', 'n1', '2026-10-20', '2026-10-20')
  assert.deepEqual(ids(dedupeEventsByNoticeEnd([noEnd, withEnd])), ['with-end'])
  assert.deepEqual(ids(dedupeEventsByNoticeEnd([withEnd, noEnd])), ['with-end'])
})

test('단일 날짜 두 행이 같은 날이면 하나만', () => {
  const rows = [ev('p', 'n1', '2026-10-20'), ev('q', 'n1', '2026-10-20')]
  assert.equal(dedupeEventsByNoticeEnd(rows).length, 1)
})

test('빈 목록·중복 없는 목록은 그대로', () => {
  assert.deepEqual(dedupeEventsByNoticeEnd([]), [])
  const rows = [ev('a', 'n1', '2026-10-01', '2026-10-02'), ev('b', 'n1', '2026-10-05', '2026-10-06')]
  assert.deepEqual(ids(dedupeEventsByNoticeEnd(rows)), ['a', 'b'])
})

test('남은 행의 순서는 들어온 순서를 지킨다', () => {
  const rows = [ev('late', 'n1', '2026-12-01', '2026-12-02'), ev('early', 'n1', '2026-10-01', '2026-10-02')]
  assert.deepEqual(ids(dedupeEventsByNoticeEnd(rows)), ['late', 'early'])
})

// ── 끝나는 날 판정: 화면과 같은 기준 ──────────────────────────────────────────

test('끝나는 날이 빈 문자열이면 시작일을 끝나는 날로 본다', () => {
  const rows = [ev('single', 'n1', '2026-10-10', ''), ev('range', 'n1', '2026-10-01', '2026-10-10')]
  assert.deepEqual(ids(dedupeEventsByNoticeEnd(rows)), ['range'])
})

test('끝이 시작보다 이른 잘못된 행은 단일 날짜로 본다 — 엉뚱한 날짜 행과 묶이지 않는다', () => {
  const bad = ev('bad', 'n1', '2026-10-10', '2026-10-05')
  const oct5 = ev('oct5', 'n1', '2026-10-05', null)
  assert.deepEqual(ids(dedupeEventsByNoticeEnd([bad, oct5])), ['bad', 'oct5'])
})

// ── 종류(행사/마감) 합치기 ────────────────────────────────────────────────────

test('지워지는 마감 행의 종류가 남는 행에 합쳐진다', () => {
  const rows = [
    ev('range', 'n1', '2026-10-01', '2026-10-10', ['event']),
    ev('deadline', 'n1', '2026-10-10', null, ['deadline']),
  ]
  const [only, ...rest] = dedupeEventsByNoticeEnd(rows)
  assert.equal(rest.length, 0)
  assert.equal(only.id, 'range')
  assert.deepEqual([...(only.eventKinds ?? [])].sort(), ['deadline', 'event'])
})

test('예방접종: 남는 행이 세 행의 종류를 모두 갖는다', () => {
  const rows = [
    ev('a', 'n1', '2026-09-21', '2027-04-30', ['event']),
    ev('b', 'n1', '2026-09-28', '2027-04-30', ['event']),
    ev('e', 'n1', '2027-04-30', null, ['deadline']),
  ]
  const result = dedupeEventsByNoticeEnd(rows)
  assert.deepEqual(ids(result), ['a'])
  assert.deepEqual([...(result[0].eventKinds ?? [])].sort(), ['deadline', 'event'])
})

test('종류가 같으면 목록을 바꾸지 않는다(같은 객체를 돌려준다)', () => {
  const winner = ev('w', 'n1', '2026-10-01', '2026-10-10', ['event'])
  const result = dedupeEventsByNoticeEnd([winner, ev('l', 'n1', '2026-10-05', '2026-10-10', ['event'])])
  assert.equal(result[0], winner)
})

test('입력을 바꾸지 않는다', () => {
  const winner = ev('w', 'n1', '2026-10-01', '2026-10-10', ['event'])
  dedupeEventsByNoticeEnd([winner, ev('d', 'n1', '2026-10-10', null, ['deadline'])])
  assert.deepEqual(winner.eventKinds, ['event'])
})
