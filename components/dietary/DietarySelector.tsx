'use client'

import { DIETARY_RESTRICTIONS, RESTRICTION_EMOJI, type DietaryRestriction } from '@/lib/dietary'

export interface DietaryOptionLabels {
  name: string
  desc: string
}

export interface DietarySelectorLabels {
  section_title: string
  hint: string
  options: Record<string, DietaryOptionLabels>
}

interface Props {
  value: DietaryRestriction[]
  onChange: (next: DietaryRestriction[]) => void
  labels: DietarySelectorLabels
  /** 섹션 제목/힌트 헤더를 표시할지 (설정 화면에선 별도 헤더가 있어 끌 수 있음) */
  showHeader?: boolean
  disabled?: boolean
}

export default function DietarySelector({ value, onChange, labels, showHeader = true, disabled }: Props) {
  function toggle(key: DietaryRestriction) {
    if (disabled) return
    onChange(value.includes(key) ? value.filter(v => v !== key) : [...value, key])
  }

  return (
    <div className="flex flex-col gap-3">
      {showHeader && (
        <div>
          <h2 className="text-base font-bold text-text-primary">{labels.section_title}</h2>
          <p className="text-sm text-text-secondary mt-1">{labels.hint}</p>
        </div>
      )}
      <div className="flex flex-col gap-2">
        {DIETARY_RESTRICTIONS.map(key => {
          const opt = labels.options[key]
          const selected = value.includes(key)
          return (
            <button
              key={key}
              type="button"
              role="checkbox"
              aria-checked={selected}
              onClick={() => toggle(key)}
              disabled={disabled}
              className={[
                'flex items-center gap-3 w-full rounded-card border p-3 text-start transition-colors',
                selected
                  ? 'border-primary bg-primary-soft'
                  : 'border-border bg-surface',
                disabled ? 'opacity-50' : 'active:scale-[0.99]',
              ].join(' ')}
            >
              <span className="text-2xl leading-none shrink-0" aria-hidden>
                {RESTRICTION_EMOJI[key]}
              </span>
              <span className="min-w-0 flex-1">
                <span className="block text-sm font-semibold text-text-primary">{opt?.name ?? key}</span>
                {opt?.desc && (
                  <span className="block text-xs text-text-secondary mt-0.5">{opt.desc}</span>
                )}
              </span>
              <span
                className={[
                  'shrink-0 w-5 h-5 rounded-md border flex items-center justify-center text-white text-xs',
                  selected ? 'bg-primary border-primary' : 'border-border bg-surface',
                ].join(' ')}
                aria-hidden
              >
                {selected ? '✓' : ''}
              </span>
            </button>
          )
        })}
      </div>
    </div>
  )
}
