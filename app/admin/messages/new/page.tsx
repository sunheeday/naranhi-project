'use client'

import { useState } from 'react'
import { useRouter } from 'next/navigation'
import AdminHeader from '@/components/admin/AdminHeader'
import { Field, TextInput, TextArea, ChipSelect, PrimaryButton } from '@/components/admin/AdminForm'
import { useAdminActions, AUDIENCE_LABEL, type Audience } from '@/lib/admin/store'

const AUDIENCE_OPTIONS: { value: Audience; label: string }[] = [
  { value: 'all', label: '전체 학부모' },
  { value: 'class', label: '개별 학부모' },
]

const TEMPLATES = [
  { label: '준비물 안내', title: '내일 준비물 안내', body: '안녕하세요. 내일 필요한 준비물을 안내드립니다.\n\n· ' },
  { label: '제출 요청', title: '제출물 확인 부탁드립니다', body: '안녕하세요. 아직 제출되지 않은 항목이 있어 확인 부탁드립니다.\n\n· ' },
  { label: '안부 인사', title: '오늘 학교생활 안내', body: '안녕하세요. 오늘 우리 아이 학교생활을 전해드립니다.\n\n' },
]

export default function NewMessagePage() {
  const router = useRouter()
  const { addMessage } = useAdminActions()

  const [audience, setAudience] = useState<Audience>('all')
  const [recipient, setRecipient] = useState('')
  const [title, setTitle] = useState('')
  const [body, setBody] = useState('')

  const effectiveRecipient = audience === 'all' ? AUDIENCE_LABEL.all : recipient.trim()
  const canSubmit =
    title.trim().length > 0 && body.trim().length > 0 && (audience === 'all' || recipient.trim().length > 0)

  function handleSubmit() {
    if (!canSubmit) return
    addMessage({
      title: title.trim(),
      body: body.trim(),
      audience,
      recipient: effectiveRecipient || AUDIENCE_LABEL.all,
    })
    router.push('/admin/messages')
  }

  return (
    <main className="flex min-h-screen flex-col pb-32">
      <AdminHeader title="메시지 작성" subtitle="학부모님께 소식 전하기" back="/admin/messages" />

      <form
        className="flex flex-col gap-5 px-5 pt-5"
        onSubmit={(e) => {
          e.preventDefault()
          handleSubmit()
        }}
      >
        <Field label="받는 대상">
          <ChipSelect options={AUDIENCE_OPTIONS} value={audience} onChange={setAudience} />
        </Field>

        {audience === 'class' ? (
          <Field label="받는 분" hint="학생 또는 보호자 이름">
            <TextInput
              value={recipient}
              onChange={(e) => setRecipient(e.target.value)}
              placeholder="예) 이민준 학부모"
            />
          </Field>
        ) : null}

        <Field label="빠른 시작" hint="템플릿 선택">
          <div className="flex flex-wrap gap-2">
            {TEMPLATES.map((t) => (
              <button
                key={t.label}
                type="button"
                onClick={() => {
                  setTitle(t.title)
                  setBody(t.body)
                }}
                className="rounded-pill border border-hairline bg-surface px-3.5 py-1.5 text-xs font-semibold text-body active:bg-surface-soft"
              >
                {t.label}
              </button>
            ))}
          </div>
        </Field>

        <Field label="제목">
          <TextInput
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            placeholder="예) 내일 준비물 안내"
            maxLength={60}
          />
        </Field>

        <Field label="내용">
          <TextArea
            value={body}
            onChange={(e) => setBody(e.target.value)}
            placeholder="학부모님께 전할 메시지를 적어주세요."
            rows={8}
          />
        </Field>

        <p className="rounded-md bg-primary-soft px-4 py-3 text-xs leading-relaxed text-body">
          💡 나란히에서는 학부모님이 설정한 언어로 메시지를 자동 번역해 전달해요. 짧고 명확한 문장이 번역에 좋아요.
        </p>
      </form>

      <div className="fixed bottom-14 inset-x-0 mx-auto w-full max-w-app border-t border-hairline-soft bg-canvas px-5 py-3 pb-safe">
        <PrimaryButton type="button" onClick={handleSubmit} disabled={!canSubmit}>
          메시지 보내기
        </PrimaryButton>
      </div>
    </main>
  )
}
