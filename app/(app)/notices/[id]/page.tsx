import Link from 'next/link'
import { notFound } from 'next/navigation'
import { cookies } from 'next/headers'
import { isRtl, isValidLocale, type Locale, defaultLocale } from '@/lib/i18n'
import {
  fetchTranslationJobStatus,
  getNoticeDetail,
  type NoticeCardDto,
  type TranslationJobStatus,
} from '@/lib/notices'
import type { CardType } from '@/types/database'
import NoticeCardSwiper, { type NoticeCard } from './NoticeCardSwiper'
import NoticeProcessingView from './NoticeProcessingView'
import NoticeErrorView from './NoticeErrorView'
import NoticeLocaleTranslationKickoff from './NoticeLocaleTranslationKickoff'
import NoticeTranslationRetryButton from './NoticeTranslationRetryButton'

interface Props {
  params: Promise<{ id: string }>
}

function asObject(content: unknown): Record<string, unknown> | null {
  if (content && typeof content === 'object' && !Array.isArray(content)) {
    return content as Record<string, unknown>
  }
  return null
}

function asText(value: unknown): string {
  return typeof value === 'string' ? value.trim() : ''
}

function mapCommonCard(type: CardType, content: unknown): NoticeCard | null {
  const obj = asObject(content)
  if (!obj) return null
  const rawItems = Array.isArray(obj.items) ? obj.items : []
  let items = rawItems
    .map(item => {
      if (typeof item === 'string') {
        const text = asText(item)
        return text ? { text } : null
      }
      const itemObj = asObject(item)
      if (!itemObj) return null
      const text = asText(itemObj.text)
      if (!text) return null
      const hint = asText(itemObj.hint)
      return hint ? { text, hint } : { text }
    })
    .filter((item): item is { text: string; hint?: string } => Boolean(item))
  if (items.length === 0 && type === 'schedule') {
    const date = asText(obj.date)
    const location = asText(obj.location)
    const description = asText(obj.description)
    const legacyItems = [
      date ? { text: date } : null,
      location ? { text: location } : null,
      description ? { text: description } : null,
    ].filter((item): item is { text: string } => Boolean(item))
    items = legacyItems
  }
  if (items.length === 0) return null
  return {
    type,
    items,
  }
}

function pickLocalized(content: unknown, locale: Locale): unknown {
  if (!content || typeof content !== 'object' || Array.isArray(content)) return content
  const c = content as Record<string, unknown>
  // jsonb { ko, zh, vi, en, ru, ar, fr, ... } 형태면 사용자 locale → ko fallback
  if (c.ko !== undefined || c[locale] !== undefined) {
    return c[locale] ?? c.ko ?? content
  }
  return content
}

// 팀 구조화 카드(해야할일/일정/준비물): notice_cards → 사용자 locale 적용 카드.
function mapCards(rows: NoticeCardDto[], locale: Locale): NoticeCard[] {
  const mapped: NoticeCard[] = []
  for (const r of rows) {
    const localized = pickLocalized(r.content, locale)
    const card = mapCommonCard(r.type, localized)
    if (card) mapped.push(card)
  }
  return mapped
}

export default async function NoticePage({ params }: Props) {
  const { id } = await params
  const cookieStore = await cookies()
  const cookieLocale = cookieStore.get('locale')?.value
  const locale: Locale = isValidLocale(cookieLocale) ? cookieLocale : defaultLocale
  const messages = (await import(`@/messages/${locale}.json`)).default

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

  const detail = await getNoticeDetail(id, locale)
  if (!detail) {
    notFound()
  }

  if (detail.status === 'pending' || detail.status === 'processing') {
    return (
      <main className="flex flex-col min-h-screen">
        {Header}
        <NoticeProcessingView
          title={messages.notice_detail.processing_title}
          description={messages.notice_detail.processing_desc}
          progressLabel={messages.common.loading}
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
          retryFailedLabel={messages.common.error_generic}
        />
      </main>
    )
  }

  const md = messages.notice_detail

  // 번역이 아직 없으면 잡 상태를 조회해 '준비중'과 '실패(재시도 안내)'를 가른다.
  // 본문·카드는 어차피 한국어로 폴백 표시되므로 배너만 상태를 알려주면 된다.
  const translationJobStatus: TranslationJobStatus =
    !detail.hasLocaleTranslation && locale !== 'ko'
      ? await fetchTranslationJobStatus(id, locale)
      : 'none'

  // 카드 순서: 요약 → 구조화(해야할일/일정/준비물) → 본문/첨부 정제본 → 원본 파일.
  const cards: NoticeCard[] = []

  // 1) 맨 앞 요약 카드: '이 공지가 무엇인지' 자연어 요약(사용자 locale로 번역됨).
  if (detail.hasSummary && detail.summary?.trim()) {
    cards.push({
      type: 'intro',
      emoji: md.intro_emoji,
      title: md.summary_title,
      summary: detail.summary,
    })
  }

  // 2) 팀 구조화 카드(notice_cards): 해야 할 일 / 일정 / 준비물.
  cards.push(...mapCards(detail.cards, locale))

  // 3) 소스별 카드: 본문 → 첨부…(정제본). 복잡한 첨부는 "원본 파일에서 보세요" 안내로 대체.
  for (const source of detail.sourceCards) {
    cards.push({
      type: 'source',
      emoji: source.kind === 'body' ? md.intro_emoji : md.file_emoji,
      title: source.kind === 'body' ? md.body_title : source.filename || md.attachment_title,
      content: source.content,
      needsFile: source.needsFile,
      complexNotice: md.attachment_complex,
    })
  }

  // 4) 맨 끝 원본 파일 카드(첨부가 하나라도 있을 때): 우리 Storage 사본을 미리보기/다운로드.
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

  // 예외(요약·구조화·소스·첨부 모두 없음) 폴백.
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
      {locale !== 'ko' ? (
        <NoticeLocaleTranslationKickoff
          noticeId={id}
          locale={locale}
          hasLocaleTranslation={detail.hasLocaleTranslation}
          translationFailed={translationJobStatus === 'failed'}
        />
      ) : null}
      {!detail.hasLocaleTranslation && locale !== 'ko' ? (
        translationJobStatus === 'failed' ? (
          <div className="px-4 pt-4">
            <div className="mx-auto max-w-app rounded-card border border-rose-200 bg-rose-50 px-4 py-4 shadow-soft">
              <div className="flex items-center justify-between gap-3">
                <p className="text-sm font-semibold text-ink">
                  {messages.home.translation_failed_banner}
                </p>
                <NoticeTranslationRetryButton
                  noticeId={id}
                  locale={locale}
                  label={messages.notice_detail.retry}
                  busyLabel={messages.notice_detail.retrying}
                />
              </div>
            </div>
          </div>
        ) : (
          <div className="px-4 pt-4">
            <div className="mx-auto max-w-app rounded-card border border-sky-200 bg-[linear-gradient(135deg,#F8FCFF_0%,#EEF7FF_100%)] px-4 py-4 shadow-soft">
              <div className="flex flex-col gap-2">
                <div className="flex items-center justify-between gap-3">
                  <p className="text-sm font-semibold text-ink">
                    {messages.home.translation_pending_banner}
                  </p>
                  <span className="shrink-0 text-xs font-bold text-primary">
                    {messages.common.loading}
                  </span>
                </div>
                <div className="h-3 overflow-hidden rounded-full bg-sky-100">
                  <div className="h-full w-[58%] rounded-full bg-[linear-gradient(90deg,#1FB6FF_0%,#2F80ED_100%)] animate-pulse" />
                </div>
              </div>
            </div>
          </div>
        )
      ) : null}
      <NoticeCardSwiper
        noticeId={id}
        cards={cards}
        isRtl={isRtl(locale)}
        labels={{
          supplies: messages.notice_detail.supplies_badge,
          action: messages.notice_detail.action_badge,
          schedule: messages.notice_detail.schedule_badge,
          defaultTitle: messages.notice_detail.intro_title,
          swipeHint: messages.notice_detail.swipe_hint,
        }}
      />
    </main>
  )
}
