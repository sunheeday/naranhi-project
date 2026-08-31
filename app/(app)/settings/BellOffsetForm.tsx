'use client'

import { useState, useTransition } from 'react'

import { updateBellOffset } from './actions'

interface Labels {
  title: string
  help: string
  label: string
  save: string
  saving: string
  saved: string
  error: string
}

interface Props {
  childId: string
  /** 지금 이 자녀에게 적용된 1교시 시작 시각 "HH:MM"(보정 반영본). */
  currentStart: string
  labels: Labels
}

/** 부모에게 «1교시 시작 시각» 한 칸만 묻는다.
 *  나머지 교시와 하교 시각은 이 값에 맞춰 통째로 밀린다. */
export default function BellOffsetForm({ childId, currentStart, labels }: Props) {
  const [value, setValue] = useState(currentStart)
  const [saved, setSaved] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [isPending, startTransition] = useTransition()

  const dirty = value !== currentStart

  function save() {
    setError(null)
    setSaved(false)
    startTransition(async () => {
      try {
        await updateBellOffset({ childId, firstPeriodStart: value })
        setSaved(true)
      } catch (e) {
        setError(e instanceof Error ? e.message : labels.error)
      }
    })
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
        <label htmlFor="bell-start" className="text-sm text-text-primary shrink-0">
          {labels.label}
        </label>
        <input
          id="bell-start"
          type="time"
          value={value}
          onChange={e => {
            setValue(e.target.value)
            setSaved(false)
          }}
          className="h-[52px] px-4 rounded-btn border border-border bg-surface text-text-primary tabular-nums"
        />
        <button
          type="button"
          onClick={save}
          disabled={!dirty || isPending}
          className="h-[52px] px-5 rounded-btn bg-primary text-white font-semibold disabled:opacity-40"
        >
          {isPending ? labels.saving : labels.save}
        </button>
      </div>

      {saved && <p className="text-sm text-success">{labels.saved}</p>}
      {error && (
        <p role="alert" className="text-sm text-red-600">
          {error}
        </p>
      )}
    </section>
  )
}
