'use client'

import { useState, useTransition } from 'react'
import { normalizeRestrictions, type DietaryRestriction } from '@/lib/dietary'
import DietarySelector, { type DietarySelectorLabels } from '@/components/dietary/DietarySelector'
import { updateChildDietary } from './actions'

interface Labels extends DietarySelectorLabels {
  edit: string
  saving: string
  saved: string
  none_selected: string
  save: string
  cancel: string
}

interface Props {
  childId: string
  initial: string[]
  labels: Labels
}

export default function DietaryEditor({ childId, initial, labels }: Props) {
  const initialRestrictions = normalizeRestrictions(initial)
  const [editing, setEditing] = useState(false)
  const [value, setValue] = useState<DietaryRestriction[]>(initialRestrictions)
  const [saved, setSaved] = useState<DietaryRestriction[]>(initialRestrictions)
  const [error, setError] = useState<string | null>(null)
  const [showSaved, setShowSaved] = useState(false)
  const [isPending, startTransition] = useTransition()

  function handleSave() {
    setError(null)
    startTransition(async () => {
      try {
        await updateChildDietary(childId, value)
        setSaved(value)
        setEditing(false)
        setShowSaved(true)
      } catch (e) {
        setError(e instanceof Error ? e.message : '저장에 실패했어요.')
      }
    })
  }

  function handleCancel() {
    setValue(saved)
    setEditing(false)
    setError(null)
  }

  const summary = saved.length === 0
    ? labels.none_selected
    : saved.map(k => labels.options[k]?.name ?? k).join(', ')

  return (
    <section aria-labelledby="dietary-heading">
      <div className="flex items-center justify-between mb-3">
        <h2 id="dietary-heading" className="text-sm font-semibold text-text-secondary">
          {labels.section_title}
        </h2>
        {!editing && (
          <button
            type="button"
            onClick={() => { setEditing(true); setShowSaved(false) }}
            className="text-sm font-semibold text-primary"
          >
            {labels.edit}
          </button>
        )}
      </div>

      {!editing ? (
        <>
          <p className="text-sm text-text-primary">{summary}</p>
          {showSaved && (
            <p role="status" className="text-xs text-primary mt-1">{labels.saved}</p>
          )}
        </>
      ) : (
        <div className="flex flex-col gap-4">
          <p className="text-sm text-text-secondary">{labels.hint}</p>
          <DietarySelector value={value} onChange={setValue} labels={labels} showHeader={false} disabled={isPending} />
          {error && <p role="alert" className="text-sm text-red-500">{error}</p>}
          <div className="flex gap-2">
            <button
              type="button"
              onClick={handleCancel}
              disabled={isPending}
              className="flex-1 h-11 rounded-btn border border-border bg-surface text-text-primary text-sm font-semibold disabled:opacity-50"
            >
              {labels.cancel}
            </button>
            <button
              type="button"
              onClick={handleSave}
              disabled={isPending}
              className="flex-1 h-11 rounded-btn bg-primary text-white text-sm font-semibold disabled:opacity-50"
            >
              {isPending ? labels.saving : labels.save}
            </button>
          </div>
        </div>
      )}
    </section>
  )
}
