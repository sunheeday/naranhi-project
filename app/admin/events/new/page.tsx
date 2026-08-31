'use client'

import { useState } from 'react'
import { useRouter } from 'next/navigation'
import AdminHeader from '@/components/admin/AdminHeader'
import { Field, TextInput, TextArea, ChipSelect, PrimaryButton } from '@/components/admin/AdminForm'
import { useAdminActions, type EventType, type Audience } from '@/lib/admin/store'

const TYPE_OPTIONS: { value: EventType; label: string }[] = [
  { value: 'event', label: '행사' },
  { value: 'exam', label: '시험' },
  { value: 'deadline', label: '제출 마감' },
  { value: 'holiday', label: '방학·휴일' },
]

const AUDIENCE_OPTIONS: { value: Audience; label: string }[] = [
  { value: 'class', label: '우리 반' },
  { value: 'all', label: '전체 학부모' },
]

export default function NewEventPage() {
  const router = useRouter()
  const { addEvent } = useAdminActions()

  const [title, setTitle] = useState('')
  const [date, setDate] = useState('')
  const [time, setTime] = useState('')
  const [type, setType] = useState<EventType>('event')
  const [audience, setAudience] = useState<Audience>('class')
  const [memo, setMemo] = useState('')

  const canSubmit = title.trim().length > 0 && date.length > 0

  function handleSubmit() {
    if (!canSubmit) return
    addEvent({ title: title.trim(), date, time, type, audience, memo: memo.trim() })
    router.push('/admin/events')
  }

  return (
    <main className="flex min-h-screen flex-col pb-32">
      <AdminHeader title="일정 등록" subtitle="행사·시험·제출 마감" back="/admin/events" />

      <form
        className="flex flex-col gap-5 px-5 pt-5"
        onSubmit={(e) => {
          e.preventDefault()
          handleSubmit()
        }}
      >
        <Field label="종류">
          <ChipSelect options={TYPE_OPTIONS} value={type} onChange={setType} />
        </Field>

        <Field label="일정 제목">
          <TextInput
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            placeholder="예) 현장체험학습 (서울대공원)"
            maxLength={60}
          />
        </Field>

        <div className="flex gap-3">
          <div className="flex-1">
            <Field label="날짜">
              <TextInput type="date" value={date} onChange={(e) => setDate(e.target.value)} />
            </Field>
          </div>
          <div className="flex-1">
            <Field label="시간" hint="선택">
              <TextInput type="time" value={time} onChange={(e) => setTime(e.target.value)} />
            </Field>
          </div>
        </div>

        <Field label="받는 대상">
          <ChipSelect options={AUDIENCE_OPTIONS} value={audience} onChange={setAudience} />
        </Field>

        <Field label="메모" hint="선택">
          <TextArea
            value={memo}
            onChange={(e) => setMemo(e.target.value)}
            placeholder="준비물, 장소, 유의사항 등"
            rows={4}
          />
        </Field>
      </form>

      <div className="fixed bottom-14 inset-x-0 mx-auto w-full max-w-app border-t border-hairline-soft bg-canvas px-5 py-3 pb-safe">
        <PrimaryButton type="button" onClick={handleSubmit} disabled={!canSubmit}>
          일정 등록하기
        </PrimaryButton>
      </div>
    </main>
  )
}
