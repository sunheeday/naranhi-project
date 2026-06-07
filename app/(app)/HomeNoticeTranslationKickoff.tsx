'use client'

import { useEffect } from 'react'
import type { Locale } from '@/lib/i18n'
import { requestNoticeTranslations, syncPendingNoticeTranslationBatch } from '@/lib/notice-translation-batch'

interface Props {
  locale: Locale
  noticeIds: string[]
}

export default function HomeNoticeTranslationKickoff({ locale, noticeIds }: Props) {
  useEffect(() => {
    if (locale === 'ko') return
    syncPendingNoticeTranslationBatch(locale, noticeIds)
    void requestNoticeTranslations(noticeIds, locale)
  }, [locale, noticeIds])

  return null
}
