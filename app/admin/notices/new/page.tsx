'use client'

import { useState } from 'react'
import { useRouter } from 'next/navigation'
import AdminHeader from '@/components/admin/AdminHeader'
import { Field, TextInput, TextArea, ChipSelect, PrimaryButton } from '@/components/admin/AdminForm'
import { useAdminActions, type NoticeCategory, type Audience } from '@/lib/admin/store'

const CATEGORY_OPTIONS: { value: NoticeCategory; label: string }[] = [
  { value: 'letter', label: '가정통신문' },
  { value: 'notice', label: '알림' },
  { value: 'meal', label: '급식' },
  { value: 'event', label: '행사' },
]

const AUDIENCE_OPTIONS: { value: Audience; label: string }[] = [
  { value: 'class', label: '우리 반' },
  { value: 'all', label: '전체 학부모' },
]

export default function NewNoticePage() {
  const router = useRouter()
  const { addNotice } = useAdminActions()

  const [title, setTitle] = useState('')
  const [body, setBody] = useState('')
  const [category, setCategory] = useState<NoticeCategory>('letter')
  const [audience, setAudience] = useState<Audience>('class')
  const [pinned, setPinned] = useState(false)

  const canSubmit = title.trim().length > 0 && body.trim().length > 0

  function handleSubmit() {
    if (!canSubmit) return
    addNotice({ title: title.trim(), body: body.trim(), category, audience, pinned })
    router.push('/admin/notices')
  }

  return (
    <main className="flex min-h-screen flex-col pb-32">
      <AdminHeader title="공지 등록" subtitle="가정통신문·알림 작성" back="/admin/notices" />

      <form
        className="flex flex-col gap-5 px-5 pt-5"
        onSubmit={(e) => {
          e.preventDefault()
          handleSubmit()
        }}
      >
        <Field label="분류">
          <ChipSelect options={CATEGORY_OPTIONS} value={category} onChange={setCategory} />
        </Field>

        <Field label="받는 대상">
          <ChipSelect options={AUDIENCE_OPTIONS} value={audience} onChange={setAudience} />
        </Field>

        <Field label="제목">
          <TextInput
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            placeholder="예) 9월 현장체험학습 안내"
            maxLength={60}
          />
        </Field>

        <Field label="내용" hint="학부모님께 전달할 내용을 적어주세요">
          <TextArea
            value={body}
            onChange={(e) => setBody(e.target.value)}
            placeholder={'준비물, 일정, 제출 기한 등을 안내해 주세요.'}
            rows={9}
          />
        </Field>

        <button
          type="button"
          onClick={() => setPinned((v) => !v)}
          className="flex items-center justify-between rounded-card border border-hairline bg-surface px-4 py-3.5"
        >
          <span className="flex flex-col text-left">
            <span className="text-sm font-semibold text-ink">상단 고정 📌</span>
            <span className="text-xs text-muted">중요한 공지를 목록 맨 위에 표시해요.</span>
          </span>
          <span
            className={`relative h-6 w-11 shrink-0 rounded-full transition ${pinned ? 'bg-primary' : 'bg-surface-strong'}`}
          >
            <span
              className={`absolute top-0.5 h-5 w-5 rounded-full bg-white shadow transition-all ${
                pinned ? 'left-[22px]' : 'left-0.5'
              }`}
            />
          </span>
        </button>
      </form>

      <div className="fixed bottom-14 inset-x-0 mx-auto w-full max-w-app border-t border-hairline-soft bg-canvas px-5 py-3 pb-safe">
        <PrimaryButton type="button" onClick={handleSubmit} disabled={!canSubmit}>
          공지 등록하기
        </PrimaryButton>
      </div>
    </main>
  )
}
