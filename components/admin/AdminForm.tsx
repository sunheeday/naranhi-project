'use client'

import type { ReactNode } from 'react'

/** 라벨 + 필드 래퍼 */
export function Field({
  label,
  hint,
  children,
}: {
  label: string
  hint?: string
  children: ReactNode
}) {
  return (
    <label className="flex flex-col gap-1.5">
      <span className="text-sm font-semibold text-ink">
        {label}
        {hint ? <span className="ml-1.5 text-xs font-normal text-muted">{hint}</span> : null}
      </span>
      {children}
    </label>
  )
}

export function TextInput(props: React.InputHTMLAttributes<HTMLInputElement>) {
  return (
    <input
      {...props}
      className={`w-full rounded-md border border-hairline bg-surface px-4 py-3 text-base text-ink outline-none transition focus:border-primary focus:ring-2 focus:ring-primary-soft placeholder:text-muted-soft ${props.className ?? ''}`}
    />
  )
}

export function TextArea(props: React.TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return (
    <textarea
      {...props}
      className={`w-full resize-none rounded-md border border-hairline bg-surface px-4 py-3 text-base leading-relaxed text-ink outline-none transition focus:border-primary focus:ring-2 focus:ring-primary-soft placeholder:text-muted-soft ${props.className ?? ''}`}
    />
  )
}

interface Option<T extends string> {
  value: T
  label: string
}

/** 칩 형태의 단일 선택 (카테고리, 대상 등) */
export function ChipSelect<T extends string>({
  options,
  value,
  onChange,
}: {
  options: Option<T>[]
  value: T
  onChange: (value: T) => void
}) {
  return (
    <div className="flex flex-wrap gap-2">
      {options.map((opt) => {
        const active = opt.value === value
        return (
          <button
            key={opt.value}
            type="button"
            onClick={() => onChange(opt.value)}
            className={`rounded-pill border px-4 py-2 text-sm font-semibold transition ${
              active
                ? 'border-primary bg-primary text-on-primary shadow-btn-primary'
                : 'border-hairline bg-surface text-body active:bg-surface-soft'
            }`}
          >
            {opt.label}
          </button>
        )
      })}
    </div>
  )
}

/** 하단 고정 기본 액션 버튼 */
export function PrimaryButton({
  children,
  disabled,
  onClick,
  type = 'button',
}: {
  children: ReactNode
  disabled?: boolean
  onClick?: () => void
  type?: 'button' | 'submit'
}) {
  return (
    <button
      type={type}
      onClick={onClick}
      disabled={disabled}
      className="w-full rounded-btn bg-primary py-3.5 text-base font-bold text-on-primary shadow-btn-primary transition active:bg-primary-active disabled:opacity-40 disabled:shadow-none"
    >
      {children}
    </button>
  )
}
