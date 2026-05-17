'use server'

import { revalidatePath } from 'next/cache'
import { createSupabaseServerClient, createSupabaseServiceClient } from '@/lib/supabase/server'

export async function deleteNotice(noticeId: string): Promise<{ ok: true } | { ok: false; error: string }> {
  const supabase = await createSupabaseServerClient()
  const { data: { user } } = await supabase.auth.getUser()
  if (!user) return { ok: false, error: '로그인이 필요합니다.' }

  const { data: notice } = await supabase
    .from('notices')
    .select('id, child_id, school_id, source')
    .eq('id', noticeId)
    .single()

  if (!notice) return { ok: false, error: '공지를 찾을 수 없어요.' }

  if (notice.source === 'crawl') {
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

  if (!notice.child_id) return { ok: false, error: '권한이 없어요.' }

  const { data: child } = await supabase
    .from('children')
    .select('id')
    .eq('id', notice.child_id)
    .eq('user_id', user.id)
    .single()

  if (!child) return { ok: false, error: '권한이 없어요.' }

  const serviceClient = await createSupabaseServiceClient()

  const { error } = await supabase.from('notices').delete().eq('id', noticeId)
  if (error) return { ok: false, error: error.message }

  await serviceClient.from('schedules').delete().eq('notice_id', noticeId)

  revalidatePath('/')
  revalidatePath('/calendar')
  return { ok: true }
}
