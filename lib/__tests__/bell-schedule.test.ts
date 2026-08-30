// Node 22 내장 테스트 러너로 돌린다 — `npm run test:unit`.
// 이 저장소에는 프론트 테스트 프레임워크가 없었다. jest/vitest 를 새로 들이는 대신
// 의존성 0 인 node:test 를 쓴다. bell-schedule 은 순수 함수뿐이라 이걸로 충분하다.
import { test } from 'node:test'
import assert from 'node:assert/strict'

import {
  applyOffset,
  defaultBellSchedule,
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
