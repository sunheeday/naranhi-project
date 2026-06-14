'use client'

import { useState, useTransition } from 'react'
import {
  dietaryPreferenceUiCopy,
  dietaryRestrictionIds,
  dietaryRestrictionLabel,
  type DietaryRestrictionId,
} from '@/lib/dietary-restrictions'
import type { Locale } from '@/lib/i18n'
import { updateChildDietaryRestrictions } from './actions'

interface Props {
  childId: string
  initialValue: DietaryRestrictionId[]
  locale: Locale
}

export default function DietaryRestrictionsForm({ childId, initialValue, locale }: Props) {
  const copy = dietaryPreferenceUiCopy[locale] ?? dietaryPreferenceUiCopy.ko
  const [selected, setSelected] = useState<DietaryRestrictionId[]>(initialValue)
  const [saved, setSaved] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [isPending, startTransition] = useTransition()

  function toggle(id: DietaryRestrictionId) {
    setSaved(false)
    setSelected(current =>
      current.includes(id)
        ? current.filter(item => item !== id)
        : [...current, id],
    )
  }

  function save() {
    setError(null)
    setSaved(false)
    startTransition(async () => {
      try {
        await updateChildDietaryRestrictions({
          childId,
          dietaryRestrictions: selected,
        })
        setSaved(true)
      } catch (e) {
        setError(e instanceof Error ? e.message : 'Failed to save dietary settings.')
      }
    })
  }

  return (
    <section aria-labelledby="dietary-heading">
      <div className="mb-3">
        <h2 id="dietary-heading" className="text-sm font-semibold text-text-secondary">
          {copy.title}
        </h2>
        <p className="mt-1 text-xs leading-relaxed text-text-secondary">{copy.description}</p>
      </div>
      <div className="flex flex-wrap gap-2">
        {dietaryRestrictionIds.map(id => {
          const active = selected.includes(id)
          return (
            <button
              key={id}
              type="button"
              aria-pressed={active}
              onClick={() => toggle(id)}
              disabled={isPending}
              className={[
                'rounded-pill border px-3 py-2 text-xs font-semibold transition-colors',
                active
                  ? 'border-primary bg-primary text-on-primary'
                  : 'border-border bg-surface text-text-primary active:bg-primary-light',
                isPending ? 'opacity-70' : '',
              ].join(' ')}
            >
              {dietaryRestrictionLabel(id, locale)}
            </button>
          )
        })}
      </div>
      {selected.length === 0 && (
        <p className="mt-2 text-xs text-text-secondary">{copy.empty}</p>
      )}
      {error && (
        <p role="alert" className="mt-2 text-xs text-red-500">{error}</p>
      )}
      {saved && !error && (
        <p role="status" className="mt-2 text-xs font-semibold text-primary">{copy.saved}</p>
      )}
      <button
        type="button"
        onClick={save}
        disabled={isPending}
        className="mt-3 h-10 rounded-btn bg-primary px-4 text-sm font-semibold text-on-primary disabled:opacity-60"
      >
        {isPending ? copy.saving : copy.save}
      </button>
    </section>
  )
}
