'use client'

import { useState, useTransition } from 'react'
import { useForm, useWatch } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'
import type { Locale } from '@/lib/i18n'
import { saveChildAndProfile } from './actions'
import SchoolSearchInput, { type SchoolPick } from './SchoolSearchInput'

const studentSchema = z.object({
  grade: z.number().int().min(1).max(6),
  classNo: z.number().int().min(1).max(20),
  childName: z.string().min(1, '아이 이름을 입력해주세요'),
})

type StudentForm = z.infer<typeof studentSchema>

function gradesFor(level: string): number[] {
  if (level.includes('중학교') || level.includes('고등학교')) return [1, 2, 3]
  return [1, 2, 3, 4, 5, 6]
}

function gradeLabel(level: string, grade: number, fallback: string): string {
  if (level.includes('중학교')) return `중${grade}`
  if (level.includes('고등학교')) return `고${grade}`
  return fallback.replace('{grade}', String(grade))
}

interface OnboardingMessages {
  step_of: string
  step1_title: string
  step1_placeholder: string
  step1_search_hint?: string
  step1_no_result?: string
  step1_searching?: string
  step1_search_error?: string
  step1_school_required?: string
  step2_title: string
  step2_grade: string
  step2_class: string
  step3_title: string
  step3_name_placeholder: string
  complete: string
}

interface Props {
  messages: OnboardingMessages
  locale: Locale
}

const CLASSES = Array.from({ length: 15 }, (_, i) => i + 1)

export default function OnboardingFlow({ messages, locale }: Props) {
  const [step, setStep] = useState(1)
  const [school, setSchool] = useState<SchoolPick | null>(null)
  const [step1Error, setStep1Error] = useState<string | null>(null)
  const [serverError, setServerError] = useState<string | null>(null)
  const [isPending, startTransition] = useTransition()

  const totalSteps = 2

  const studentForm = useForm<StudentForm>({
    resolver: zodResolver(studentSchema),
    defaultValues: { grade: 1, classNo: 1, childName: '' },
  })
  useWatch({ control: studentForm.control })

  function stepLabel(current: number) {
    return messages.step_of
      .replace('{current}', String(current))
      .replace('{total}', String(totalSteps))
  }

  function handleStep1Submit(e: React.FormEvent) {
    e.preventDefault()
    setStep(2)
  }

  function handleStudentSubmit(data: StudentForm) {
    if (!school || !school.schoolCode) return
    setServerError(null)
    startTransition(async () => {
      try {
        await saveChildAndProfile({
          schoolName: school.name,
          schoolAddress: school.address,
          schoolHomepageUrl: school.homepageUrl,
          neisOfficeCode: school.officeCode,
          neisSchoolCode: school.schoolCode,
          grade: data.grade,
          classNo: data.classNo,
          childName: data.childName,
          locale,
        })
      } catch (e) {
        setServerError(e instanceof Error ? e.message : '저장에 실패했습니다.')
      }
    })
  }

  const handleBack = () => setStep(s => s - 1)
  const schoolLevel = school?.level ?? ''

  return (
    <main className="flex flex-col min-h-screen px-6 pt-6 pb-24">
      <header className="flex items-center gap-4 mb-8">
        {step > 1 && (
          <button
            type="button"
            onClick={handleBack}
            aria-label="이전 단계"
            className="w-10 h-10 flex items-center justify-center text-text-secondary"
          >
            ←
          </button>
        )}
        <div className="flex gap-1.5 ms-auto" role="status" aria-label={stepLabel(step)}>
          {[1, 2].map(s => (
            <span
              key={s}
              className={`w-2 h-2 rounded-full transition-colors ${s <= step ? 'bg-primary' : 'bg-border'}`}
            />
          ))}
        </div>
        <span className="text-sm text-text-secondary">{stepLabel(step)}</span>
      </header>

      {step === 1 && (
        <form onSubmit={handleStep1Submit} className="flex flex-col gap-6">
          <div>
            <h1 className="text-xl font-bold text-text-primary">{messages.step1_title}</h1>
            {messages.step1_search_hint && (
              <p className="text-sm text-text-secondary mt-1">{messages.step1_search_hint}</p>
            )}
          </div>
          <SchoolSearchInput
            value={school}
            onSelect={s => {
              setSchool(s)
              setStep1Error(null)
            }}
            placeholder={messages.step1_placeholder}
            noResultLabel={messages.step1_no_result ?? '검색 결과가 없어요.'}
            searchingLabel={messages.step1_searching ?? '검색 중...'}
            errorLabel={messages.step1_search_error ?? '학교 검색에 실패했어요.'}
          />
          {step1Error && (
            <p role="alert" className="text-sm text-red-500 px-1">{step1Error}</p>
          )}
          <FixedNextButton label="다음 →" disabled={!school?.schoolCode} isPending={false} />
        </form>
      )}

      {step === 2 && (
        <form onSubmit={studentForm.handleSubmit(handleStudentSubmit)} className="flex flex-col gap-6">
          <h1 className="text-xl font-bold text-text-primary">{messages.step3_title}</h1>
          <div className="flex flex-col gap-3">
            <select
              {...studentForm.register('grade', { valueAsNumber: true })}
              aria-label="학년 선택"
              className="w-full h-[52px] px-4 rounded-btn border border-border bg-surface text-base text-text-primary focus:outline-none focus:border-primary appearance-none"
            >
              {gradesFor(schoolLevel).map(g => (
                <option key={g} value={g}>
                  {gradeLabel(schoolLevel, g, messages.step2_grade)}
                </option>
              ))}
            </select>
            <select
              {...studentForm.register('classNo', { valueAsNumber: true })}
              aria-label="반 선택"
              className="w-full h-[52px] px-4 rounded-btn border border-border bg-surface text-base text-text-primary focus:outline-none focus:border-primary appearance-none"
            >
              {CLASSES.map(c => (
                <option key={c} value={c}>
                  {messages.step2_class.replace('{class}', String(c))}
                </option>
              ))}
            </select>
            <input
              {...studentForm.register('childName')}
              type="text"
              placeholder={messages.step3_name_placeholder}
              aria-label={messages.step3_name_placeholder}
              className="w-full h-[52px] px-4 rounded-btn border border-border bg-surface text-base text-text-primary placeholder:text-text-disabled focus:outline-none focus:border-primary"
            />
            {studentForm.formState.errors.childName && (
              <p role="alert" className="text-sm text-red-500 px-1">
                {studentForm.formState.errors.childName.message}
              </p>
            )}
          </div>

          {serverError && (
            <p role="alert" className="text-sm text-red-500 px-1">{serverError}</p>
          )}

          <FixedNextButton label={messages.complete} disabled={false} isPending={isPending} />
        </form>
      )}
    </main>
  )
}

function FixedNextButton({
  label,
  disabled,
  isPending,
}: {
  label: string
  disabled: boolean
  isPending: boolean
}) {
  return (
    <div className="fixed bottom-0 inset-x-0 mx-auto w-full max-w-app px-6 pb-8 bg-canvas pt-4">
      <button
        type="submit"
        disabled={disabled || isPending}
        className="w-full h-12 rounded-btn bg-primary text-white text-base font-semibold shadow-btn-primary disabled:opacity-40 active:scale-[0.98] transition-transform"
      >
        {isPending ? '저장 중...' : label}
      </button>
    </div>
  )
}
