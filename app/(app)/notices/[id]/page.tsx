import Link from 'next/link'
import { notFound } from 'next/navigation'
import { cookies } from 'next/headers'
import { isValidLocale, type Locale, defaultLocale } from '@/lib/i18n'
import { getNoticeDetail, type NoticeCardDto } from '@/lib/notices'
import { isUiPreviewEnabled } from '@/lib/ui-preview'
import type { CardType } from '@/types/database'
import NoticeCardSwiper, { type NoticeCard } from './NoticeCardSwiper'
import NoticeProcessingView from './NoticeProcessingView'
import NoticeErrorView from './NoticeErrorView'
import NoticeLocaleTranslationKickoff from './NoticeLocaleTranslationKickoff'

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
  const items = rawItems
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

// UI 프리뷰 전용 샘플 카드뉴스 (홈의 previewNotices()의 id와 1:1 매칭)
function previewNoticeCards(id: string): NoticeCard[] | null {
  switch (id) {
    case 'preview-action':
      return [
        {
          type: 'intro',
          emoji: '📄',
          title: '가정통신문',
          summary:
            '3학년 봄 현장체험학습을 안내드립니다.\n자녀의 안전한 체험학습을 위해 참가 동의서를 기한 내에 제출해 주세요.\n아래 카드를 옆으로 넘기면 해야 할 일과 일정을 확인할 수 있어요.',
          hint: '카드를 옆으로 넘겨 보세요',
        },
        {
          type: 'action',
          items: [
            { text: '참가 동의서 제출', hint: '4월 18일(금)까지 담임 선생님께 제출' },
            { text: '체험학습비 25,000원 납부', hint: '4월 16일 스쿨뱅킹 자동 출금' },
          ],
        },
        {
          type: 'schedule',
          items: [
            { text: '현장체험학습일: 4월 25일(금)', hint: '09:00 출발 ~ 16:00 학교 도착' },
            { text: '장소: 국립과천과학관', hint: '우천 시 4월 29일(화)로 순연' },
          ],
        },
      ]
    case 'preview-supplies':
      return [
        {
          type: 'intro',
          emoji: '📄',
          title: '가정통신문',
          summary:
            '봄 소풍을 안내드립니다.\n즐거운 하루를 위해 아래 준비물을 미리 챙겨 주세요.',
          hint: '카드를 옆으로 넘겨 보세요',
        },
        {
          type: 'supplies',
          items: [
            { text: '도시락과 물', hint: '음료는 1개까지, 유리병은 가져오지 않아요' },
            { text: '편한 옷차림과 운동화' },
            { text: '돗자리', hint: '모둠당 1개, 모둠 대표 학생이 준비' },
            { text: '개인 비상약', hint: '필요한 학생만 준비' },
          ],
        },
        {
          type: 'schedule',
          items: [{ text: '소풍 날짜: 5월 2일(금)', hint: '09:00 ~ 14:00' }],
        },
      ]
    case 'preview-info':
      // 단순 안내(소식): 학부모가 따로 할 일은 없고 알아두면 되는 공지
      return [
        {
          type: 'intro',
          emoji: '📰',
          title: '학교 안내',
          summary:
            '4월 학사일정과 휴업일을 안내드립니다.\n특별히 준비하거나 제출할 것은 없으니 일정만 확인해 주세요.\n• 4월 10일(목) 재량휴업일\n• 4월 30일(수) 단축수업(13:00 하교)',
        },
      ]
    default:
      return null
  }
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

  // UI 프리뷰: DB 없이 샘플 카드뉴스를 바로 보여준다.
  if (await isUiPreviewEnabled()) {
    const previewCards = previewNoticeCards(id)
    if (id === 'preview-schedule') {
      // 분석 중 화면을 demonstrate (홈에서 '분석 중' 배지로 노출되는 공지)
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
    if (previewCards) {
      return (
        <main className="flex flex-col min-h-screen">
          {Header}
          <NoticeCardSwiper
            noticeId={id}
            cards={previewCards}
            labels={{
              supplies: messages.notice_detail.supplies_badge,
              action: messages.notice_detail.action_badge,
              schedule: messages.notice_detail.schedule_badge,
            }}
          />
        </main>
      )
    }
  }

  const detail = await getNoticeDetail(id, locale)
  if (!detail) {
    notFound()
  }

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
