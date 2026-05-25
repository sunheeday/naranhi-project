'use client'

import { useEffect, useRef, useState } from 'react'

export interface SchoolPick {
  name: string
  level: string
  officeCode: string
  schoolCode: string
  address: string
  homepageUrl?: string
}

interface Props {
  value: SchoolPick | null
  onSelect: (school: SchoolPick) => void
  placeholder: string
  noResultLabel: string
  searchingLabel: string
  errorLabel: string
}

export default function SchoolSearchInput({
  value,
  onSelect,
  placeholder,
  noResultLabel,
  searchingLabel,
  errorLabel,
}: Props) {
  const [query, setQuery] = useState(value?.name ?? '')
  const [results, setResults] = useState<SchoolPick[]>([])
  const [open, setOpen] = useState(false)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(false)
  const debounceRef = useRef<number | null>(null)

  useEffect(() => {
    if (!query || query.trim().length < 2) {
      queueMicrotask(() => {
        setResults([])
        setError(false)
        setLoading(false)
        setOpen(false)
      })
      return
    }
    if (value && value.name === query) {
      // 사용자가 한번 선택하고 그대로 두면 검색 안 함
      return
    }

    queueMicrotask(() => {
      setLoading(true)
      setError(false)
    })
    if (debounceRef.current) window.clearTimeout(debounceRef.current)
    debounceRef.current = window.setTimeout(async () => {
      try {
        const res = await fetch(`/api/schools/search?q=${encodeURIComponent(query.trim())}`)
        const json = await res.json()
        if (!res.ok) throw new Error(json?.error ?? 'failed')
        setResults((json.results ?? []).slice(0, 20))
        setOpen(true)
      } catch {
        setError(true)
        setResults([])
      } finally {
        setLoading(false)
      }
    }, 300)

    return () => {
      if (debounceRef.current) window.clearTimeout(debounceRef.current)
    }
  }, [query, value])

  function handlePick(school: SchoolPick) {
    onSelect(school)
    setQuery(school.name)
    setOpen(false)
    setResults([])
  }

  return (
    <div className="relative flex flex-col gap-2">
      <input
        type="text"
        value={query}
        onChange={e => {
          setQuery(e.target.value)
          // 직접 입력 중엔 선택 해제
          if (value && value.name !== e.target.value) {
            onSelect({ ...value, name: e.target.value, officeCode: '', schoolCode: '' })
          }
          setOpen(true)
        }}
        onFocus={() => results.length > 0 && setOpen(true)}
        placeholder={placeholder}
        aria-label={placeholder}
        autoComplete="off"
        className="w-full h-[52px] px-4 rounded-btn border border-border bg-surface text-base text-text-primary placeholder:text-text-disabled focus:outline-none focus:border-primary"
      />

      {loading && (
        <p className="text-xs text-text-secondary px-1" role="status">{searchingLabel}</p>
      )}

      {error && (
        <p className="text-xs text-red-500 px-1" role="alert">{errorLabel}</p>
      )}

      {open && results.length > 0 && (
        <ul
          role="listbox"
          className="absolute top-[60px] left-0 right-0 max-h-72 overflow-y-auto bg-surface border border-border rounded-btn shadow-card z-20"
        >
          {results.map(school => (
            <li key={`${school.officeCode}-${school.schoolCode}`} role="option" aria-selected={false}>
              <button
                type="button"
                onClick={() => handlePick(school)}
                className="w-full text-start px-4 py-3 hover:bg-surface-card active:bg-surface-card border-b border-hairline last:border-0"
              >
                <div className="flex items-center gap-2">
                  <span className="text-base font-semibold text-text-primary">{school.name}</span>
                  <span className="text-xs text-text-secondary">{school.level}</span>
                </div>
                {school.address && (
                  <p className="text-xs text-text-secondary mt-0.5 truncate">{school.address}</p>
                )}
              </button>
            </li>
          ))}
        </ul>
      )}

      {open && !loading && !error && query.trim().length >= 2 && results.length === 0 && (
        <p className="text-xs text-text-secondary px-1">{noResultLabel}</p>
      )}

      {value?.schoolCode && (
        <p className="text-xs text-primary px-1">
          ✓ {value.name} {value.level && `(${value.level})`}
        </p>
      )}
    </div>
  )
}
