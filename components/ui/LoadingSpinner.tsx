'use client'

interface Props {
  className?: string
  label?: string
  size?: 'sm' | 'md' | 'lg'
}

const SIZE_CLASS: Record<NonNullable<Props['size']>, string> = {
  sm: 'h-5 w-5 border-2',
  md: 'h-10 w-10 border-[3px]',
  lg: 'h-14 w-14 border-4',
}

export default function LoadingSpinner({
  className = '',
  label,
  size = 'md',
}: Props) {
  return (
    <div
      className={[
        'rounded-full border-sky-200 border-t-primary animate-spin',
        SIZE_CLASS[size],
        className,
      ].join(' ')}
      role={label ? 'status' : undefined}
      aria-label={label}
    />
  )
}
