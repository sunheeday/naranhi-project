'use server'

import { revalidatePath } from 'next/cache'
import { createSupabaseServerClient } from '@/lib/supabase/server'
import { hideDemoNotice, isTestEntryBypassEnabled } from '@/lib/test-entry-bypass'

export async function deleteNotice(noticeId: string): Promise<{ ok: true } | { ok: false; error: string }> {
  const supabase = await createSupabaseServerClient()
  const { data: { user } } = await supabase.auth.getUser()
  if (!user) {
    // 시연 방문자: DB 가 아니라 그 사람 브라우저 쿠키에만 «숨김» 을 기억한다.
    if (!isTestEntryBypassEnabled()) return { ok: false, error: '로그인이 필요합니다.' }
    await hideDemoNotice(noticeId)
    revalidatePath('/')
    return { ok: true }
  }

  const { data: notice } = await supabase
    .from('notices')
    .select('id, school_id')
    .eq('id', noticeId)
    .single()

  if (!notice) return { ok: false, error: '공지를 찾을 수 없어요.' }
  if (!notice.school_id) return { ok: false, error: '학교 공지 정보가 올바르지 않아요.' }

  const { data: child } = await supabase
    .from('children')
    .select('id')
    .eq('user_id', user.id)
    .eq('school_id', notice.school_id)
    .limit(1)
    .maybeSingle()

  if (!child) return { ok: false, error: '권한이 없어요.' }

  const { error: hideError } = await supabase
    .from('notice_hides')
    .upsert(
      {
        user_id: user.id,
        notice_id: notice.id,
      },
      { onConflict: 'user_id,notice_id' }
    )

  if (hideError) return { ok: false, error: hideError.message }
  revalidatePath('/')
  return { ok: true }
}
