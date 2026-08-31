'use client'

import { useEffect, useState, useTransition } from 'react'

import type { PersonalScheduleColor } from '@/types/database'

import {
  createPersonalSchedule,
  deletePersonalSchedule,
  updatePersonalSchedule,
} from './actions'

export const PERSONAL_COLORS: readonly PersonalScheduleColor[] = [
  'blue', 'green', 'orange', 'purple', 'pink',
]

/** 팔레트 키 → 토큰. 다크 모드에서도 읽히는 조합만 둔다. */
export const PERSONAL_COLOR_DOT: Record<PersonalScheduleColor, string> = {
  blue: 'bg-card-schedule',
  orange: 'bg-card-action',
  green: 'bg-success',
  purple: 'bg-purple-400',
  pink: 'bg-pink-400',
}

export interface PersonalScheduleDraft {
  id?: string
  title: string
  dayOfWeek: number
  startTime: string
  endTime: string
  location: string | null
  memo: string | null
  color: PersonalScheduleColor
}

export interface PersonalLabels {
  section: string
  add: string
  edit: string
  titleLabel: string
  titlePlaceholder: string
  weekdayLabel: string
  startLabel: string
  endLabel: string
  locationLabel: string
  locationPlaceholder: string
  memoLabel: string
  colorLabel: string
  save: string
  saving: string
  cancel: string
  delete: string
  deleteConfirmTitle: string
  deleteConfirmBody: string
  errTimeOrder: string
  weekdays: string[]
}

interface Props {
  childId: string
  draft: PersonalScheduleDraft
  labels: PersonalLabels
  onClose: () => void
}

export default function PersonalScheduleSheet({ childId, draft, labels, onClose }: Props) {
  const [title, setTitle] = useState(draft.title)
  const [dayOfWeek, setDayOfWeek] = useState(draft.dayOfWeek)
  const [startTime, setStartTime] = useState(draft.startTime)
  const [endTime, setEndTime] = useState(draft.endTime)
  const [location, setLocation] = useState(draft.location ?? '')
  const [memo, setMemo] = useState(draft.memo ?? '')
  const [color, setColor] = useState<PersonalScheduleColor>(draft.color)
  const [confirmDelete, setConfirmDelete] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [isPending, startTransition] = useTransition()

  const editing = Boolean(draft.id)
  const invalid = !title.trim() || startTime >= endTime

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  function submit() {
    setError(null)
    if (startTime >= endTime) {
      setError(labels.errTimeOrder)
      return
    }
    startTransition(async () => {
      try {
        const payload = {
          childId, title, dayOfWeek, startTime, endTime,
          location, memo, color,
        }
        if (draft.id) {
          await updatePersonalSchedule({ ...payload, id: draft.id })
        } else {
          await createPersonalSchedule(payload)
        }
        onClose()
      } catch (e) {
        setError(e instanceof Error ? e.message : 'Failed to save.')
      }
    })
  }

  function remove() {
    if (!draft.id) return
    setError(null)
    startTransition(async () => {
      try {
        await deletePersonalSchedule(draft.id!)
        onClose()
      } catch (e) {
        setError(e instanceof Error ? e.message : 'Failed to delete.')
      }
    })
  }

  return (
    <>
      <div className="fixed inset-0 z-40 bg-black/40" onClick={onClose} aria-hidden />
      <div
        role="dialog"
        aria-modal="true"
        aria-label={editing ? labels.edit : labels.add}
        className="fixed bottom-0 inset-x-0 z-50 max-h-[88vh] overflow-y-auto rounded-t-[28px] bg-surface px-6 pb-8 pt-3 shadow-[0_-4px_24px_rgba(0,0,0,0.16)]"
      >
        <div className="mx-auto mb-4 h-1 w-10 rounded-full bg-border" />
        <h2 className="text-lg font-bold text-text-primary mb-4">
          {editing ? labels.edit : labels.add}
        </h2>

        <div className="flex flex-col gap-4">
          <label className="flex flex-col gap-1.5">
            <span className="text-sm text-text-secondary">{labels.titleLabel}</span>
            <input
              value={title}
              onChange={e => setTitle(e.target.value)}
              placeholder={labels.titlePlaceholder}
              maxLength={60}
              className="h-[52px] px-4 rounded-btn border border-border bg-surface text-text-primary"
            />
          </label>

          <div className="flex flex-col gap-1.5">
            <span className="text-sm text-text-secondary">{labels.weekdayLabel}</span>
            {/* v1 은 월~금만 노출한다. DB 는 0~6 을 허용하지만 화면이 월~금 5일이라
                주말을 고르면 어디에도 안 보인다. */}
            <div className="flex gap-2">
              {[1, 2, 3, 4, 5].map(d => (
                <button
                  key={d}
                  type="button"
                  onClick={() => setDayOfWeek(d)}
                  aria-pressed={dayOfWeek === d}
                  className={[
                    'flex-1 h-[44px] rounded-btn border text-sm font-semibold',
                    dayOfWeek === d
                      ? 'border-primary bg-primary text-white'
                      : 'border-border text-text-primary',
                  ].join(' ')}
                >
                  {labels.weekdays[d]}
                </button>
              ))}
            </div>
          </div>

          <div className="flex gap-3">
            <label className="flex flex-1 flex-col gap-1.5">
              <span className="text-sm text-text-secondary">{labels.startLabel}</span>
              <input
                type="time"
                value={startTime}
                onChange={e => setStartTime(e.target.value)}
                className="h-[52px] px-4 rounded-btn border border-border bg-surface text-text-primary tabular-nums"
              />
            </label>
            <label className="flex flex-1 flex-col gap-1.5">
              <span className="text-sm text-text-secondary">{labels.endLabel}</span>
              <input
                type="time"
                value={endTime}
                onChange={e => setEndTime(e.target.value)}
                className="h-[52px] px-4 rounded-btn border border-border bg-surface text-text-primary tabular-nums"
              />
            </label>
          </div>

          <label className="flex flex-col gap-1.5">
            <span className="text-sm text-text-secondary">{labels.locationLabel}</span>
            <input
              value={location}
              onChange={e => setLocation(e.target.value)}
              placeholder={labels.locationPlaceholder}
              className="h-[52px] px-4 rounded-btn border border-border bg-surface text-text-primary"
            />
          </label>

          <label className="flex flex-col gap-1.5">
            <span className="text-sm text-text-secondary">{labels.memoLabel}</span>
            <textarea
              value={memo}
              onChange={e => setMemo(e.target.value)}
              rows={2}
              className="px-4 py-3 rounded-btn border border-border bg-surface text-text-primary resize-none"
            />
          </label>

          <div className="flex flex-col gap-1.5">
            <span className="text-sm text-text-secondary">{labels.colorLabel}</span>
            <div className="flex gap-3">
              {PERSONAL_COLORS.map(c => (
                <button
                  key={c}
                  type="button"
                  onClick={() => setColor(c)}
                  aria-label={c}
                  aria-pressed={color === c}
                  className={[
                    'h-9 w-9 rounded-full',
                    PERSONAL_COLOR_DOT[c],
                    color === c ? 'ring-2 ring-offset-2 ring-primary' : '',
                  ].join(' ')}
                />
              ))}
            </div>
          </div>

          {error && (
            <p role="alert" className="text-sm text-red-600">{error}</p>
          )}

          <div className="flex gap-3 pt-2">
            <button
              type="button"
              onClick={onClose}
              className="flex-1 h-[52px] rounded-btn border border-border text-text-primary font-semibold"
            >
              {labels.cancel}
            </button>
            <button
              type="button"
              onClick={submit}
              disabled={invalid || isPending}
              className="flex-1 h-[52px] rounded-btn bg-primary text-white font-semibold disabled:opacity-40"
            >
              {isPending ? labels.saving : labels.save}
            </button>
          </div>

          {editing && (
            <button
              type="button"
              onClick={() => setConfirmDelete(true)}
              className="h-[44px] text-sm font-semibold text-red-600"
            >
              {labels.delete}
            </button>
          )}
        </div>
      </div>

      {confirmDelete && (
        <div className="fixed inset-0 z-[60] flex items-center justify-center bg-black/50 px-8">
          <div role="alertdialog" aria-modal="true" className="w-full max-w-sm rounded-card bg-surface p-6">
            <p className="text-base font-bold text-text-primary">{labels.deleteConfirmTitle}</p>
            <p className="mt-2 text-sm text-text-secondary">{labels.deleteConfirmBody}</p>
            <div className="mt-5 flex gap-3">
              <button
                type="button"
                onClick={() => setConfirmDelete(false)}
                className="flex-1 h-[48px] rounded-btn border border-border font-semibold text-text-primary"
              >
                {labels.cancel}
              </button>
              <button
                type="button"
                onClick={remove}
                disabled={isPending}
                className="flex-1 h-[48px] rounded-btn bg-red-600 font-semibold text-white disabled:opacity-40"
              >
                {labels.delete}
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  )
}
