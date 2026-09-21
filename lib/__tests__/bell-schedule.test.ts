// Node 22 내장 테스트 러너로 돌린다 — `npm run test:unit`.
// 이 저장소에는 프론트 테스트 프레임워크가 없었다. jest/vitest 를 새로 들이는 대신
// 의존성 0 인 node:test 를 쓴다. bell-schedule 은 순수 함수뿐이라 이걸로 충분하다.
import { test } from 'node:test'
import assert from 'node:assert/strict'

import {
  applyBellOverrides,
  applyOffset,
  defaultBellSchedule,
  extendBellSchedule,
  resolveDismissal,
  type BellPeriod,
} from '../bell-schedule.ts'

/** 부천부흥중 2026학년도 시정표 실측값(2026-08-30 홈페이지 일과표 이미지 판독).
 *  점심 직후 5교시가 쉬는 시간 0분으로 붙는 것이 이 표의 핵심 불규칙성이다. */
const PCBUHEUNG: BellPeriod[] = [
  { period: 1, startTime: '09:10', endTime: '09:55' },
  { period: 2, startTime: '10:05', endTime: '10:50' },
  { period: 3, startTime: '11:00', endTime: '11:45' },
  { period: 4, startTime: '11:55', endTime: '12:40' },
  { period: 5, startTime: '13:30', endTime: '14:15' },
  { period: 6, startTime: '14:25', endTime: '15:10' },
  { period: 7, startTime: '15:20', endTime: '16:05' },
]

test('6교시 날 하교는 마지막 교시 끝 + 종례 10분', () => {
  assert.equal(resolveDismissal(PCBUHEUNG, 6, 0), '15:20')
})

test('7교시 날 하교', () => {
  assert.equal(resolveDismissal(PCBUHEUNG, 7, 0), '16:15')
})

test('보정 -10분이 하교에 반영된다', () => {
  assert.equal(resolveDismissal(PCBUHEUNG, 6, -10), '15:10')
})

test('표에 없는 교시면 null — 억지로 추정하지 않는다', () => {
  assert.equal(resolveDismissal(PCBUHEUNG, 9, 0), null)
})

test('교시 0 이하도 null', () => {
  assert.equal(resolveDismissal(PCBUHEUNG, 0, 0), null)
})

test('applyOffset 은 시작·종료를 함께 민다', () => {
  const shifted = applyOffset(PCBUHEUNG, -10)
  assert.equal(shifted[0].startTime, '09:00')
  assert.equal(shifted[0].endTime, '09:45')
  assert.equal(shifted[6].endTime, '15:55')
})

test('applyOffset 0 은 원본을 그대로 돌려준다', () => {
  assert.equal(applyOffset(PCBUHEUNG, 0), PCBUHEUNG)
})

test('applyOffset 은 원본 배열을 변형하지 않는다', () => {
  applyOffset(PCBUHEUNG, 30)
  assert.equal(PCBUHEUNG[0].startTime, '09:10')
})

test('초등 표준값 — 1교시 09:00, 40분 수업', () => {
  const p = defaultBellSchedule('인천문남초등학교')
  assert.deepEqual(p[0], { period: 1, startTime: '09:00', endTime: '09:40' })
  assert.equal(p[1].startTime, '09:50')
})

test('초등 표준값 — 4교시 뒤 점심 50분', () => {
  // 09:00 +40 → 09:40, +10 → 09:50 … 4교시 11:30–12:10, 점심 50분, 5교시 13:00
  const p = defaultBellSchedule('인천문남초등학교')
  assert.equal(p[3].startTime, '11:30')
  assert.equal(p[3].endTime, '12:10')
  assert.equal(p[4].startTime, '13:00')
})

test('초등은 6교시까지', () => {
  assert.equal(defaultBellSchedule('인천문남초등학교').length, 6)
})

test('중학 표준값 — 1교시 09:10, 45분, 7교시까지', () => {
  const p = defaultBellSchedule('부천부흥중학교')
  assert.equal(p[0].startTime, '09:10')
  assert.equal(p[0].endTime, '09:55')
  assert.equal(p.length, 7)
})

test('고등 표준값 — 1교시 08:50, 50분', () => {
  const p = defaultBellSchedule('부천고등학교')
  assert.equal(p[0].startTime, '08:50')
  assert.equal(p[0].endTime, '09:40')
})

test('학교급을 못 가리면 초등으로 본다 — 사용자 대부분이 초등이다', () => {
  assert.equal(defaultBellSchedule('이름없는학교')[0].startTime, '09:00')
  assert.equal(defaultBellSchedule('').length, 6)
})

test('표준 교시는 겹치지 않고 순서대로다', () => {
  for (const name of ['문남초등학교', '부흥중학교', '부천고등학교']) {
    const periods = defaultBellSchedule(name)
    let prevEnd = -1
    for (const p of periods) {
      const s = Number(p.startTime.slice(0, 2)) * 60 + Number(p.startTime.slice(3))
      const e = Number(p.endTime.slice(0, 2)) * 60 + Number(p.endTime.slice(3))
      assert.ok(s < e, `${name} ${p.period}교시 시작이 종료보다 늦다`)
      assert.ok(s >= prevEnd, `${name} ${p.period}교시가 앞 교시와 겹친다`)
      prevEnd = e
    }
  }
})

test('중학 표준값이 실측 부천부흥중과 1교시가 같다 — 표준값이 현실과 동떨어지지 않았다는 확인', () => {
  const p = defaultBellSchedule('부천부흥중학교')
  assert.equal(p[0].startTime, PCBUHEUNG[0].startTime)
  assert.equal(p[0].endTime, PCBUHEUNG[0].endTime)
})

// ── 부모가 고치는 세 값(1교시 시작·쉬는 시간·점심시간) ─────────────────────────

test('세 칸을 다 비우면 기존 동작(표 전체 밀기)과 같다', () => {
  const shifted = applyBellOverrides(PCBUHEUNG, { offsetMinutes: -10 })
  assert.deepEqual(shifted, applyOffset(PCBUHEUNG, -10))
})

test('쉬는 시간만 고치면 점심 자리는 원래 간격을 지킨다', () => {
  const result = applyBellOverrides(PCBUHEUNG, { breakMinutes: 5 })
  // 1교시 09:10~09:55 는 그대로, 2교시는 5분 뒤 시작
  assert.equal(result[0].startTime, '09:10')
  assert.equal(result[1].startTime, '10:00')
  // 쉬는 시간이 5분씩 줄어 4교시가 12:25 에 끝나고, 점심 50분은 그대로라 5교시는 13:15
  assert.equal(result[3].endTime, '12:25')
  assert.equal(result[4].startTime, '13:15')
})

test('점심시간만 고치면 오전은 그대로고 오후만 밀린다', () => {
  const result = applyBellOverrides(PCBUHEUNG, { lunchMinutes: 40 })
  assert.equal(result[3].endTime, '12:40')       // 4교시까지 원본 그대로
  assert.equal(result[4].startTime, '13:20')     // 점심 50분 → 40분이라 10분 당겨짐
  assert.equal(result[6].endTime, '15:55')
})

test('수업 길이는 원래 표의 것을 그대로 쓴다 — 홈페이지 판독본을 표준값으로 덮지 않는다', () => {
  const result = applyBellOverrides(PCBUHEUNG, { breakMinutes: 5, lunchMinutes: 40 })
  for (let i = 0; i < PCBUHEUNG.length; i++) {
    const before = toMin(PCBUHEUNG[i].endTime) - toMin(PCBUHEUNG[i].startTime)
    const after = toMin(result[i].endTime) - toMin(result[i].startTime)
    assert.equal(after, before, `${result[i].period}교시 수업 길이가 바뀌었다`)
  }
})

test('세 값을 다 넣으면 시작·쉬는 시간·점심이 모두 반영된다', () => {
  const result = applyBellOverrides(PCBUHEUNG, {
    offsetMinutes: -10,
    breakMinutes: 5,
    lunchMinutes: 40,
  })
  assert.equal(result[0].startTime, '09:00')
  assert.equal(result[1].startTime, '09:50')
  assert.equal(result[4].startTime, '12:55')
})

test('쉬는 시간 0분도 «안 넣음»과 구분된다', () => {
  const zero = applyBellOverrides(PCBUHEUNG, { breakMinutes: 0 })
  const none = applyBellOverrides(PCBUHEUNG, {})
  assert.equal(zero[1].startTime, '09:55')   // 1교시 끝나자마자 2교시
  assert.equal(none[1].startTime, '10:05')   // 원래 10분 쉼
})

test('빈 표를 넣어도 터지지 않는다', () => {
  assert.deepEqual(applyBellOverrides([], { breakMinutes: 5 }), [])
})

test('표준표에도 적용된다 — 점심은 4교시 뒤로 잡힌다', () => {
  const base = defaultBellSchedule('문남초등학교')
  const result = applyBellOverrides(base, { lunchMinutes: 40 })
  assert.equal(result[3].endTime, base[3].endTime)              // 4교시까지 그대로
  assert.equal(toMin(result[4].startTime), toMin(base[4].startTime) - 10)
})

function toMin(hhmm: string): number {
  return Number(hhmm.slice(0, 2)) * 60 + Number(hhmm.slice(3))
}

test('간격이 전부 같으면 점심 자리를 못 찾고 점심 값을 무시한다', () => {
  // 초등 저학년처럼 오전만 있는 표. 점심은 맨 끝이라 교시 사이에 빈자리가 없다.
  const morningOnly: BellPeriod[] = [
    { period: 1, startTime: '09:00', endTime: '09:40' },
    { period: 2, startTime: '09:50', endTime: '10:30' },
    { period: 3, startTime: '10:40', endTime: '11:20' },
    { period: 4, startTime: '11:30', endTime: '12:10' },
  ]
  const result = applyBellOverrides(morningOnly, { lunchMinutes: 40 })
  assert.deepEqual(result, morningOnly)
})

test('간격 차이가 작으면(15분 대 10분) 점심으로 보지 않는다', () => {
  const noisy: BellPeriod[] = [
    { period: 1, startTime: '09:00', endTime: '09:40' },
    { period: 2, startTime: '09:50', endTime: '10:30' },
    { period: 3, startTime: '10:45', endTime: '11:25' },
  ]
  assert.deepEqual(applyBellOverrides(noisy, { lunchMinutes: 40 }), noisy)
})

test('점심 자리를 못 찾아도 쉬는 시간 보정은 모든 간격에 적용된다', () => {
  const morningOnly: BellPeriod[] = [
    { period: 1, startTime: '09:00', endTime: '09:40' },
    { period: 2, startTime: '09:50', endTime: '10:30' },
    { period: 3, startTime: '10:40', endTime: '11:20' },
  ]
  const result = applyBellOverrides(morningOnly, { breakMinutes: 5 })
  assert.equal(result[1].startTime, '09:45')
  assert.equal(result[2].startTime, '10:30')
})

test('교시가 하나뿐인 표는 그대로 나온다', () => {
  const single: BellPeriod[] = [{ period: 1, startTime: '09:00', endTime: '09:40' }]
  assert.deepEqual(applyBellOverrides(single, { breakMinutes: 5, lunchMinutes: 40 }), single)
})

test('시각표 밖 교시는 앞 교시 뒤로 이어 붙인다 — 초등 7교시', () => {
  const p = extendBellSchedule(defaultBellSchedule('인천문남초등학교'), 7)
  assert.equal(p.length, 7)
  // 6교시 13:50–14:30 → 쉬는 10분 → 7교시 14:40–15:20 (수업 40분 그대로)
  assert.deepEqual(p[6], { period: 7, startTime: '14:40', endTime: '15:20' })
})

test('시각표 안의 교시만 있으면 그대로 돌려준다', () => {
  const base = defaultBellSchedule('인천문남초등학교')
  assert.deepEqual(extendBellSchedule(base, 6), base)
  assert.deepEqual(extendBellSchedule(base, 0), base)
})

test('빈 시각표는 그대로 빈 채로 돌려준다', () => {
  assert.deepEqual(extendBellSchedule([], 8), [])
})
