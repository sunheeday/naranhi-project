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
  const [draft, setDraft] = useState<DietaryRestrictionId[]>(initialValue)
  const [open, setOpen] = useState(false)
  const [saved, setSaved] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [isPending, startTransition] = useTransition()

  function toggle(id: DietaryRestrictionId) {
    setSaved(false)
    setDraft(current =>
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
          dietaryRestrictions: draft,
        })
        setSelected(draft)
        setSaved(true)
        setOpen(false)
      } catch (e) {
        setError(e instanceof Error ? e.message : 'Failed to save dietary settings.')
      }
    })
  }

  function openPicker() {
    setDraft(selected)
    setError(null)
    setSaved(false)
    setOpen(true)
  }

  function closePicker() {
    if (isPending) return
    setDraft(selected)
    setOpen(false)
  }

  return (
    <section aria-labelledby="dietary-heading">
      <div className="mb-3">
        <h2 id="dietary-heading" className="text-sm font-semibold text-text-secondary">
          {copy.title}
        </h2>
        <p className="mt-1 text-xs leading-relaxed text-text-secondary">{copy.description}</p>
      </div>
      <button
        type="button"
        onClick={openPicker}
        className="flex w-full items-center justify-between gap-3 rounded-card border border-border bg-surface p-4 text-start active:bg-primary-light"
      >
        <span className="min-w-0">
          <span className="block text-sm font-semibold text-text-primary">{copy.select}</span>
          <span className="mt-1 flex flex-wrap gap-1.5">
            {selected.length === 0 ? (
              <span className="text-xs text-text-secondary">{copy.empty}</span>
            ) : (
              selected.map(id => (
                <span
                  key={id}
                  className="rounded-pill bg-primary-light px-2 py-0.5 text-[11px] font-semibold text-primary"
                >
                  {dietaryRestrictionLabel(id, locale)}
                </span>
              ))
            )}
          </span>
        </span>
        <span className="shrink-0 text-text-disabled" aria-hidden="true">›</span>
      </button>
      {error && (
        <p role="alert" className="mt-2 text-xs text-red-500">{error}</p>
      )}
      {saved && !error && (
        <p role="status" className="mt-2 text-xs font-semibold text-primary">{copy.saved}</p>
      )}
      {open && (
        <>
          <button
            type="button"
            aria-label={copy.close}
            onClick={closePicker}
            className="fixed inset-0 z-40 bg-black/40"
          />
          <div
            role="dialog"
            aria-modal="true"
            aria-labelledby="dietary-picker-title"
            className="fixed bottom-0 inset-x-0 z-50 mx-auto w-full max-w-app rounded-t-[28px] bg-surface px-6 pb-safe-4 shadow-[0_-4px_24px_rgba(0,0,0,0.16)]"
          >
            <div className="flex justify-center pt-3 pb-2">
              <div className="h-1 w-10 rounded-full bg-border" aria-hidden="true" />
            </div>
            <div className="py-3">
              <h3 id="dietary-picker-title" className="text-lg font-bold text-text-primary">
                {copy.title}
              </h3>
              <p className="mt-1 text-xs leading-relaxed text-text-secondary">{copy.description}</p>
            </div>
            <div className="grid grid-cols-1 gap-2">
              {dietaryRestrictionIds.map(id => {
                const active = draft.includes(id)
                return (
                  <button
                    key={id}
                    type="button"
                    aria-pressed={active}
                    onClick={() => toggle(id)}
                    disabled={isPending}
                    className={[
                      'flex min-h-12 items-center justify-between rounded-btn border px-4 py-3 text-sm font-semibold transition-colors',
                      active
                        ? 'border-primary bg-primary text-on-primary'
                        : 'border-border bg-bg text-text-primary active:bg-primary-light',
                      isPending ? 'opacity-70' : '',
                    ].join(' ')}
                  >
                    <span>{dietaryRestrictionLabel(id, locale)}</span>
                    {active && <span aria-hidden="true">✓</span>}
                  </button>
                )
              })}
            </div>
            <div className="mt-5 flex gap-2">
              <button
                type="button"
                onClick={closePicker}
                disabled={isPending}
                className="h-11 flex-1 rounded-btn border border-border text-sm font-semibold text-text-secondary disabled:opacity-60"
              >
                {copy.close}
              </button>
              <button
                type="button"
                onClick={save}
                disabled={isPending}
                className="h-11 flex-1 rounded-btn bg-primary text-sm font-semibold text-on-primary disabled:opacity-60"
              >
                {isPending ? copy.saving : copy.save}
              </button>
            </div>
          </div>
        </>
      )}
    </section>
  )
}
