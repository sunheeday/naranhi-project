'use client'

import { useState, useTransition } from 'react'
import { selectDemoSchool } from './actions'

export interface DemoSchoolItem {
  key: string
  name: string
  level: 'elementary' | 'middle'
}

interface Props {
  schools: DemoSchoolItem[]
  currentKey: string
  title: string
  hint: string
}

export default function DemoSchoolPicker({ schools, currentKey, title, hint }: Props) {
  const [selected, setSelected] = useState(currentKey)
  const [error, setError] = useState<string | null>(null)
  const [isPending, startTransition] = useTransition()

  function handlePick(key: string) {
    if (key === selected || isPending) return
    setError(null)
    const previous = selected
    setSelected(key)
    startTransition(async () => {
      try {
        await selectDemoSchool(key)
      } catch (e) {
        setSelected(previous)
        setError(e instanceof Error ? e.message : '선택에 실패했어요.')
      }
    })
  }

  return (
    <section className="flex flex-col gap-3" aria-labelledby="demo-school-heading">
      <div className="flex flex-col gap-0.5">
        <h2 id="demo-school-heading" className="text-sm font-semibold text-text-secondary">
          {title}
        </h2>
        <p className="text-xs text-text-disabled">{hint}</p>
      </div>

      <div role="radiogroup" aria-label={title} className="flex flex-col gap-2">
        {schools.map(school => {
          const active = school.key === selected
          return (
            <button
              key={school.key}
              type="button"
              role="radio"
              aria-checked={active}
              onClick={() => handlePick(school.key)}
              disabled={isPending}
              className={`flex items-center justify-between rounded-card border p-4 text-start transition-colors disabled:opacity-60 ${
                active
                  ? 'border-primary bg-primary-soft'
                  : 'border-border bg-surface'
              }`}
            >
              <span className="flex items-center gap-2 min-w-0">
                <span
                  className={`shrink-0 rounded-full px-1.5 py-0.5 text-[11px] font-bold ${
                    school.level === 'elementary'
                      ? 'bg-amber-100 text-amber-700'
                      : 'bg-sky-100 text-sky-700'
                  }`}
                >
                  {school.level === 'elementary' ? '초' : '중'}
                </span>
                <span className={`truncate text-base ${active ? 'font-bold text-ink' : 'text-text-primary'}`}>
                  {school.name}
                </span>
              </span>
              {active && <span className="shrink-0 text-primary font-semibold">✓</span>}
            </button>
          )
        })}
      </div>

      {error && <p role="alert" className="text-sm text-red-500">{error}</p>}
    </section>
  )
}
