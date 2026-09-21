'use client'

import { useEffect, useRef, useState, useTransition } from 'react'
import { selectDemoSchool } from './actions'

export interface DemoSchoolItem {
  key: string
  name: string
}

interface Props {
  schools: DemoSchoolItem[]
  currentKey: string
  title: string
}

export default function DemoSchoolPicker({ schools, currentKey, title }: Props) {
  const [open, setOpen] = useState(false)
  const [selectedKey, setSelectedKey] = useState(currentKey)
  const [error, setError] = useState<string | null>(null)
  const [isPending, startTransition] = useTransition()
  const containerRef = useRef<HTMLDivElement>(null)

  const selectedSchool = schools.find(s => s.key === selectedKey) ?? schools[0]

  useEffect(() => {
    if (!open) return
    function onPointerDown(event: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(event.target as Node)) {
        setOpen(false)
      }
    }
    document.addEventListener('mousedown', onPointerDown)
    return () => document.removeEventListener('mousedown', onPointerDown)
  }, [open])

  function handlePick(key: string) {
    setOpen(false)
    if (key === selectedKey || isPending) return
    setError(null)
    const previous = selectedKey
    setSelectedKey(key)
    startTransition(async () => {
      try {
        await selectDemoSchool(key)
      } catch (e) {
        setSelectedKey(previous)
        setError(e instanceof Error ? e.message : '선택에 실패했어요.')
      }
    })
  }

  return (
    <section className="flex flex-col gap-3" aria-labelledby="demo-school-heading">
      <h2 id="demo-school-heading" className="text-sm font-semibold text-text-secondary">
        {title}
      </h2>

      <div ref={containerRef} className="flex flex-col">
        <button
          type="button"
          aria-haspopup="listbox"
          aria-expanded={open}
          disabled={isPending}
          onClick={() => setOpen(o => !o)}
          className="flex h-[52px] items-center justify-between gap-2 rounded-btn border border-border bg-surface px-4 text-base text-text-primary disabled:opacity-60"
        >
          <span className="truncate">{selectedSchool?.name}</span>
          <svg
            viewBox="0 0 20 20"
            fill="none"
            aria-hidden="true"
            className={`h-5 w-5 shrink-0 text-text-disabled transition-transform ${open ? 'rotate-180' : ''}`}
          >
            <path d="M5.5 8l4.5 4.5L14.5 8" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        </button>

        {open && (
          <ul
            role="listbox"
            aria-label={title}
            className="mt-2 overflow-hidden rounded-btn border border-border bg-surface"
          >
            {schools.map((school, index) => {
              const active = school.key === selectedKey
              return (
                <li key={school.key} role="option" aria-selected={active}>
                  <button
                    type="button"
                    onClick={() => handlePick(school.key)}
                    className={`flex h-[52px] w-full items-center justify-between gap-2 px-4 text-start text-base active:bg-surface-card ${
                      active ? 'font-semibold text-ink' : 'text-text-primary'
                    } ${index > 0 ? 'border-t border-hairline' : ''}`}
                  >
                    <span className="truncate">{school.name}</span>
                    {active && <span className="shrink-0 text-primary">✓</span>}
                  </button>
                </li>
              )
            })}
          </ul>
        )}
      </div>

      {error && <p role="alert" className="text-sm text-red-500">{error}</p>}
    </section>
  )
}
