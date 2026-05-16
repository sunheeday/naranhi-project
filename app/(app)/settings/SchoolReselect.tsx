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
}

interface Props {
  childId: string
  currentSchoolName: string
  hasNeisCode: boolean
  labels: Labels
}

export default function SchoolReselect({ childId, currentSchoolName, hasNeisCode, labels }: Props) {
  const [open, setOpen] = useState(false)
  const [school, setSchool] = useState<SchoolPick | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [savedAt, setSavedAt] = useState<number | null>(null)
  const [isPending, startTransition] = useTransition()

  function handleSave() {
    if (!school || !school.schoolCode) {
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
        })
        setSavedAt(Date.now())
        setOpen(false)
        setSchool(null)
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
          <span className={`text-xs ${hasNeisCode ? 'text-primary' : 'text-amber-700'}`}>
            {hasNeisCode ? `✓ ${labels.current_label}` : `⚠ ${labels.current_unset}`}
          </span>
        </div>
        <button
          type="button"
          onClick={() => setOpen(o => !o)}
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
              setError(null)
            }}
            placeholder={labels.search_placeholder}
            noResultLabel={labels.no_result}
            searchingLabel={labels.searching}
            errorLabel={labels.search_error}
          />
          {error && <p role="alert" className="text-sm text-red-500">{error}</p>}
          <div className="flex gap-2 mt-2">
            <button
              type="button"
              onClick={() => { setOpen(false); setSchool(null); setError(null) }}
              disabled={isPending}
              className="flex-1 h-10 rounded-btn border border-border text-sm text-text-secondary"
            >
              {labels.cancel}
            </button>
            <button
              type="button"
              onClick={handleSave}
              disabled={!school?.schoolCode || isPending}
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
