'use client'

import { useState, useTransition } from 'react'
import SchoolSearchInput, { type SchoolPick } from '@/app/onboarding/SchoolSearchInput'
import { updateChildSchool } from './actions'

interface Labels {
  title: string
  current_label: string
  current_unset: string
  reselect_button: string
  cancel: string
  save: string
  saving: string
  saved: string
  search_placeholder: string
  no_result: string
  searching: string
  search_error: string
  required: string
  grade_label: string
  class_label: string
  grade_placeholder: string
  class_placeholder: string
}

interface Props {
  childId: string
  currentSchoolName: string
  currentGrade: number
  currentClassNo: number | null
  hasNeisCode: boolean
  labels: Labels
}

function schoolLevelKind(school: SchoolPick | null): 'elementary' | 'middle' | 'high' | 'elementary_fallback' {
  const text = `${school?.level ?? ''}${school?.name ?? ''}`.replace(/\s+/g, '')
  if (/초등학교|초$/.test(text)) return 'elementary'
  if (/중학교|중$/.test(text)) return 'middle'
  if (/고등학교|고$/.test(text)) return 'high'
  return 'elementary_fallback'
}

function gradesForSchool(school: SchoolPick | null): number[] {
  const kind = schoolLevelKind(school)
  if (kind === 'middle' || kind === 'high') return [1, 2, 3]
  return [1, 2, 3, 4, 5, 6]
}

function gradeLabel(school: SchoolPick | null, grade: number, fallback: string): string {
  const kind = schoolLevelKind(school)
  if (kind === 'middle') return `중${grade}`
  if (kind === 'high') return `고${grade}`
  return fallback.replace('{grade}', String(grade))
}

export default function SchoolReselect({
  childId,
  currentSchoolName,
  currentGrade,
  currentClassNo,
  hasNeisCode,
  labels,
}: Props) {
  const [open, setOpen] = useState(false)
  const [school, setSchool] = useState<SchoolPick | null>(null)
  const [grade, setGrade] = useState<number | null>(currentGrade)
  const [classNo, setClassNo] = useState<number | null>(currentClassNo)
  const [error, setError] = useState<string | null>(null)
  const [savedAt, setSavedAt] = useState<number | null>(null)
  const [isPending, startTransition] = useTransition()

  function handleSave() {
    if (!school || !school.schoolCode || !grade || !classNo) {
      setError(labels.required)
      return
    }
    setError(null)
    startTransition(async () => {
      try {
        await updateChildSchool({
          childId,
          schoolName: school.name,
          schoolAddress: school.address,
          neisOfficeCode: school.officeCode,
          neisSchoolCode: school.schoolCode,
          grade,
          classNo,
        })
        setSavedAt(Date.now())
        setOpen(false)
        setSchool(null)
        setGrade(grade)
        setClassNo(classNo)
      } catch (e) {
        setError(e instanceof Error ? e.message : '저장 실패')
      }
    })
  }

  return (
    <section className="flex flex-col gap-3">
      <h2 className="text-sm font-semibold text-text-secondary">{labels.title}</h2>
      <div className="flex items-center justify-between bg-surface rounded-card border border-border p-4">
        <div className="flex flex-col">
          <span className="text-base text-text-primary">{currentSchoolName}</span>
          <span className="text-xs text-text-secondary">
            {labels.grade_label.replace('{grade}', String(currentGrade))}
            {' · '}
            {currentClassNo ? labels.class_label.replace('{class}', String(currentClassNo)) : labels.class_placeholder}
          </span>
          <span className={`text-xs ${hasNeisCode ? 'text-primary' : 'text-amber-700'}`}>
            {hasNeisCode ? `✓ ${labels.current_label}` : `⚠ ${labels.current_unset}`}
          </span>
        </div>
        <button
          type="button"
          onClick={() => {
            setOpen(o => {
              const next = !o
              if (next) {
                setSchool(null)
                setGrade(currentGrade)
                setClassNo(currentClassNo)
                setError(null)
              }
              return next
            })
          }}
          className="text-sm text-primary font-semibold px-3 py-1.5 rounded-btn"
        >
          {labels.reselect_button}
        </button>
      </div>

      {open && (
        <div className="bg-surface rounded-card border border-border p-4 flex flex-col gap-3">
          <SchoolSearchInput
            value={school}
            onSelect={s => {
              setSchool(s)
              setGrade(null)
              setClassNo(null)
              setError(null)
            }}
            placeholder={labels.search_placeholder}
            noResultLabel={labels.no_result}
            searchingLabel={labels.searching}
            errorLabel={labels.search_error}
          />
          <div className="grid grid-cols-2 gap-2">
            <select
              value={grade ?? ''}
              onChange={event => {
                const value = Number(event.target.value)
                setGrade(Number.isFinite(value) && value > 0 ? value : null)
                setError(null)
              }}
              disabled={!school?.schoolCode}
              aria-label={labels.grade_placeholder}
              className="h-10 rounded-btn border border-border bg-surface px-3 text-sm text-text-primary disabled:opacity-50"
            >
              <option value="">{labels.grade_placeholder}</option>
              {gradesForSchool(school).map(item => (
                <option key={item} value={item}>
                  {gradeLabel(school, item, labels.grade_label)}
                </option>
              ))}
            </select>
            <input
              type="number"
              min={1}
              max={20}
              inputMode="numeric"
              value={classNo ?? ''}
              onChange={event => {
                const value = Number(event.target.value)
                setClassNo(Number.isInteger(value) && value >= 1 && value <= 20 ? value : null)
                setError(null)
              }}
              disabled={!school?.schoolCode}
              aria-label={labels.class_placeholder}
              placeholder={labels.class_placeholder}
              className="h-10 rounded-btn border border-border bg-surface px-3 text-sm text-text-primary placeholder:text-text-disabled disabled:opacity-50"
            />
          </div>
          {error && <p role="alert" className="text-sm text-red-500">{error}</p>}
          <div className="flex gap-2 mt-2">
            <button
              type="button"
              onClick={() => {
                setOpen(false)
                setSchool(null)
                setGrade(currentGrade)
                setClassNo(currentClassNo)
                setError(null)
              }}
              disabled={isPending}
              className="flex-1 h-10 rounded-btn border border-border text-sm text-text-secondary"
            >
              {labels.cancel}
            </button>
            <button
              type="button"
              onClick={handleSave}
              disabled={!school?.schoolCode || !grade || !classNo || isPending}
              className="flex-1 h-10 rounded-btn bg-primary text-white text-sm font-semibold disabled:opacity-50"
            >
              {isPending ? labels.saving : labels.save}
            </button>
          </div>
        </div>
      )}

      {savedAt && (
        <p className="text-xs text-primary">✓ {labels.saved}</p>
      )}
    </section>
  )
}
