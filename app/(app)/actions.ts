'use server'

import { revalidatePath } from 'next/cache'
import { createSupabaseServerClient, createSupabaseServiceClient } from '@/lib/supabase/server'

export async function deleteNotice(noticeId: string): Promise<{ ok: true } | { ok: false; error: string }> {
  const supabase = await createSupabaseServerClient()
  const { data: { user } } = await supabase.auth.getUser()
  if (!user) return { ok: false, error: '로그인이 필요합니다.' }

  const { data: notice } = await supabase
    .from('notices')
    .select('id, child_id, children!inner(user_id)')
    .eq('id', noticeId)
    .single()

  if (!notice) return { ok: false, error: '공지를 찾을 수 없어요.' }

  const childRel = (notice as unknown as { children: { user_id: string } | { user_id: string }[] }).children
  const ownerId = Array.isArray(childRel) ? childRel[0]?.user_id : childRel?.user_id
  if (ownerId !== user.id) return { ok: false, error: '권한이 없어요.' }

  const serviceClient = await createSupabaseServiceClient()

  const { error } = await supabase.from('notices').delete().eq('id', noticeId)
  if (error) return { ok: false, error: error.message }

  await serviceClient.from('schedules').delete().eq('notice_id', noticeId)

  revalidatePath('/')
  revalidatePath('/calendar')
  return { ok: true }
}
