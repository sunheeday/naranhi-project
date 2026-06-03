import Link from 'next/link'
import { notFound } from 'next/navigation'
import { cookies } from 'next/headers'
import { isValidLocale, type Locale, defaultLocale } from '@/lib/i18n'
import { getNoticeDetail } from '@/lib/notices'
import NoticeCardSwiper, { type NoticeCard } from './NoticeCardSwiper'
import NoticeProcessingView from './NoticeProcessingView'
import NoticeErrorView from './NoticeErrorView'
import NoticeLocaleTranslationKickoff from './NoticeLocaleTranslationKickoff'

interface Props {
  params: Promise<{ id: string }>
}

export default async function NoticePage({ params }: Props) {
  const { id } = await params
  const cookieStore = await cookies()
  const cookieLocale = cookieStore.get('locale')?.value
  const locale: Locale = isValidLocale(cookieLocale) ? cookieLocale : defaultLocale
  const messages = (await import(`@/messages/${locale}.json`)).default

  const detail = await getNoticeDetail(id, locale)
  if (!detail) {
    notFound()
  }

  const backLabel = messages.notice_detail.back_to_list

  const Header = (
    <header className="sticky top-0 bg-surface border-b border-border px-4 py-3 flex items-center justify-between z-10">
      <Link href="/" className="flex items-center gap-2 text-text-secondary text-sm" aria-label={backLabel}>
        <span aria-hidden="true">←</span>
        <span>{backLabel}</span>
      </Link>
      <span className="text-sm text-text-secondary" aria-live="polite" />
    </header>
  )

  if (detail.status === 'pending' || detail.status === 'processing') {
    return (
      <main className="flex flex-col min-h-screen">
        {Header}
        <NoticeProcessingView
          noticeId={id}
          title={messages.notice_detail.processing_title}
          description={messages.notice_detail.processing_desc}
        />
      </main>
    )
  }

  if (detail.status === 'error') {
    return (
      <main className="flex flex-col min-h-screen">
        {Header}
        <NoticeErrorView
          noticeId={id}
          title={messages.notice_detail.error_title}
          description={messages.notice_detail.error_desc}
          errorMessage={detail.errorMessage}
          retryLabel={messages.notice_detail.retry}
          retryingLabel={messages.notice_detail.retrying}
        />
      </main>
    )
  }

  const md = messages.notice_detail

  // 소스별 카드: 본문 → 첨부…(정제본 렌더). 복잡한 첨부는 "원본 파일에서 보세요" 안내로 대체.
  const cards: NoticeCard[] = detail.sourceCards.map(source => ({
    type: 'source' as const,
    emoji: source.kind === 'body' ? md.intro_emoji : md.file_emoji,
    title: source.kind === 'body' ? md.body_title : source.filename || md.attachment_title,
    content: source.content,
    needsFile: source.needsFile,
    complexNotice: md.attachment_complex,
  }))

  // 맨 끝 원본 파일 카드(첨부가 하나라도 있을 때): 우리 Storage 사본을 미리보기/다운로드.
  if (detail.attachmentFiles.length > 0) {
    cards.push({
      type: 'file',
      emoji: md.file_emoji,
      title: md.file_title,
      files: detail.attachmentFiles.map(file => ({
        filename: file.filename,
        publicUrl: file.publicUrl,
        previewable: file.previewable,
      })),
      fileLabels: { preview: md.preview, download: md.download },
    })
  }

  // 예외(소스·첨부 모두 없음) 폴백.
  if (cards.length === 0) {
    cards.push({
      type: 'intro',
      emoji: md.intro_emoji,
      title: md.intro_title,
      summary: detail.summary ?? '',
    })
  }

  // 카드가 2개 이상이면 스와이프 힌트 표시.
  if (cards.length > 1) {
    for (const card of cards) card.hint = md.swipe_hint
  }

  return (
    <main className="flex flex-col min-h-screen">
      {Header}
      {!detail.hasLocaleTranslation ? (
        <NoticeLocaleTranslationKickoff noticeId={id} locale={locale} />
      ) : null}
      <NoticeCardSwiper
        noticeId={id}
        cards={cards}
        labels={{
          supplies: messages.notice_detail.supplies_badge,
          action: messages.notice_detail.action_badge,
          schedule: messages.notice_detail.schedule_badge,
        }}
      />
    </main>
  )
}
