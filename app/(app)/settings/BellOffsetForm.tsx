'use client'

import { useState, useTransition } from 'react'

import { updateBellTimes } from './actions'

interface Labels {
  title: string
  help: string
  label: string
  breakLabel: string
  lunchLabel: string
  blankHint: string
  breakRangeError: string
  lunchRangeError: string
  save: string
  saving: string
  saved: string
  error: string
}

interface Props {
  childId: string
  /** 지금 이 자녀에게 적용된 1교시 시작 시각 "HH:MM"(보정 반영본). */
  currentStart: string
  /** 부모가 넣어 둔 쉬는 시간(분). 안 넣었으면 null. */
  currentBreak: number | null
  /** 부모가 넣어 둔 점심시간(분). 안 넣었으면 null. */
  currentLunch: number | null
  labels: Labels
}

/** 빈칸은 «기본값을 쓴다»는 뜻이므로 0 과 구분해야 한다. 그래서 문자열로 들고 있다가
 *  보낼 때만 숫자로 바꾼다. */
function toMinutesOrNull(raw: string): number | null {
  const trimmed = raw.trim()
  return trimmed === '' ? null : Number(trimmed)
}

function inRange(value: number, min: number, max: number): boolean {
  return Number.isInteger(value) && value >= min && value <= max
}

/** 부모에게 «1교시 시작 · 쉬는 시간 · 점심시간» 세 칸을 묻는다.
 *  나머지 교시와 하교 시각은 이 값들에 맞춰 다시 계산된다.
 *  비워 둔 칸은 학교 표(홈페이지 판독본 또는 학교급 표준값)를 그대로 쓴다. */
export default function BellOffsetForm({
  childId,
  currentStart,
  currentBreak,
  currentLunch,
  labels,
}: Props) {
  const [start, setStart] = useState(currentStart)
  const [breakValue, setBreakValue] = useState(currentBreak === null ? '' : String(currentBreak))
  const [lunchValue, setLunchValue] = useState(currentLunch === null ? '' : String(currentLunch))
  const [saved, setSaved] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [isPending, startTransition] = useTransition()

  const dirty =
    start !== currentStart ||
    breakValue !== (currentBreak === null ? '' : String(currentBreak)) ||
    lunchValue !== (currentLunch === null ? '' : String(currentLunch))

  function save() {
    setError(null)
    setSaved(false)

    // 이 폼은 <form> 이 아니라 버튼 onClick 이라 input 의 min/max 가 강제되지 않는다.
    // 서버·DB 도 같은 범위로 막지만, 그쪽 메시지는 한국어라 여기서 먼저 잡는다.
    const breakMinutes = toMinutesOrNull(breakValue)
    const lunchMinutes = toMinutesOrNull(lunchValue)
    if (breakMinutes !== null && !inRange(breakMinutes, 0, 60)) {
      setError(labels.breakRangeError)
      return
    }
    if (lunchMinutes !== null && !inRange(lunchMinutes, 0, 120)) {
      setError(labels.lunchRangeError)
      return
    }

    startTransition(async () => {
      try {
        await updateBellTimes({ childId, firstPeriodStart: start, breakMinutes, lunchMinutes })
        setSaved(true)
      } catch (e) {
        setError(e instanceof Error ? e.message : labels.error)
      }
    })
  }

  function touch(setter: (value: string) => void) {
    return (value: string) => {
      setter(value)
      setSaved(false)
    }
  }

  return (
    <section aria-labelledby="bell-heading" className="flex flex-col gap-3">
      <div>
        <h2 id="bell-heading" className="text-sm font-semibold text-text-secondary">
          {labels.title}
        </h2>
        <p className="text-xs text-muted mt-1">{labels.help}</p>
      </div>

      <div className="flex items-center gap-3">
        <label htmlFor="bell-start" className="text-sm text-text-primary shrink-0 w-24">
          {labels.label}
        </label>
        <input
          id="bell-start"
          type="time"
          value={start}
          onChange={e => touch(setStart)(e.target.value)}
          className="h-[52px] px-4 rounded-btn border border-border bg-surface text-text-primary tabular-nums"
        />
      </div>

      <div className="flex items-center gap-3">
        <label htmlFor="bell-break" className="text-sm text-text-primary shrink-0 w-24">
          {labels.breakLabel}
        </label>
        <input
          id="bell-break"
          type="number"
          inputMode="numeric"
          min={0}
          max={60}
          value={breakValue}
          onChange={e => touch(setBreakValue)(e.target.value)}
          className="h-[52px] w-28 px-4 rounded-btn border border-border bg-surface text-text-primary tabular-nums"
        />
      </div>

      <div className="flex items-center gap-3">
        <label htmlFor="bell-lunch" className="text-sm text-text-primary shrink-0 w-24">
          {labels.lunchLabel}
        </label>
        <input
          id="bell-lunch"
          type="number"
          inputMode="numeric"
          min={0}
          max={120}
          value={lunchValue}
          onChange={e => touch(setLunchValue)(e.target.value)}
          className="h-[52px] w-28 px-4 rounded-btn border border-border bg-surface text-text-primary tabular-nums"
        />
      </div>

      <p className="text-xs text-muted">{labels.blankHint}</p>

      <button
        type="button"
        onClick={save}
        disabled={!dirty || isPending}
        className="h-[52px] px-5 rounded-btn bg-primary text-white font-semibold disabled:opacity-40 self-start"
      >
        {isPending ? labels.saving : labels.save}
      </button>

      {saved && <p className="text-sm text-success">{labels.saved}</p>}
      {error && (
        <p role="alert" className="text-sm text-red-600">
          {error}
        </p>
      )}
    </section>
  )
}
