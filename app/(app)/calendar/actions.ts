'use server'

import { revalidatePath } from 'next/cache'

import { createSupabaseServerClient } from '@/lib/supabase/server'
import type { PersonalScheduleColor } from '@/types/database'

const COLORS: readonly PersonalScheduleColor[] = ['blue', 'green', 'orange', 'purple', 'pink']
const HHMM = /^([01]\d|2[0-3]):[0-5]\d$/

export interface PersonalScheduleInput {
  childId: string
  title: string
  dayOfWeek: number
  startTime: string
  endTime: string
  location?: string
  memo?: string
  color?: string
}

interface Normalized {
  title: string
  day_of_week: number
  start_time: string
  end_time: string
  location: string | null
  memo: string | null
  color: PersonalScheduleColor
}

/** DB CHECK 와 같은 규칙을 서버에서도 본다. 화면·서버·DB 3중 검증이다. */
function normalize(input: PersonalScheduleInput): Normalized {
  const title = input.title.trim()
  if (!title) throw new Error('일정 제목을 입력해 주세요.')
  if (title.length > 60) throw new Error('일정 제목이 너무 길어요.')
  if (!HHMM.test(input.startTime) || !HHMM.test(input.endTime)) {
    throw new Error('시간 형식이 올바르지 않아요.')
  }
  if (input.startTime >= input.endTime) throw new Error('종료 시간이 시작 시간보다 빨라요.')
  if (!Number.isInteger(input.dayOfWeek) || input.dayOfWeek < 0 || input.dayOfWeek > 6) {
    throw new Error('요일을 다시 선택해 주세요.')
  }
  const color = (input.color ?? 'blue') as PersonalScheduleColor
  return {
    title,
    day_of_week: input.dayOfWeek,
    start_time: input.startTime,
    end_time: input.endTime,
    location: input.location?.trim() || null,
    memo: input.memo?.trim() || null,
    color: COLORS.includes(color) ? color : 'blue',
  }
}

async function requireUser() {
  const supabase = await createSupabaseServerClient()
  const { data: { user }, error } = await supabase.auth.getUser()
  if (error || !user) throw new Error('로그인이 필요합니다.')
  return { supabase, user }
}

export async function createPersonalSchedule(input: PersonalScheduleInput): Promise<void> {
  const row = normalize(input)
  const { supabase, user } = await requireUser()

  // create 는 child_id 를 클라이언트에서 받으므로 RLS(with check) 에 더해 여기서도
  // 소유권을 명시적으로 확인한다 — 위조된 child_id 가 오면 여기서 먼저 걸린다.
  const { data: child, error: childError } = await supabase
    .from('children')
    .select('id')
    .eq('id', input.childId)
    .eq('user_id', user.id)
    .maybeSingle()
  if (childError) throw new Error(`자녀 조회 실패: ${childError.message}`)
  if (!child) throw new Error('권한이 없어요.')

  const { error } = await supabase
    .from('child_personal_schedules')
    .insert({ child_id: input.childId, ...row })
  if (error) throw new Error('일정 저장에 실패했어요.')

  revalidatePath('/calendar')
}

export async function updatePersonalSchedule(
  input: PersonalScheduleInput & { id: string },
): Promise<void> {
  const row = normalize(input)
  const { supabase } = await requireUser()

  // 소유권은 RLS using 절이 보장한다 — 남의 자녀 일정이면 0행이 갱신된다.
  const { data, error } = await supabase
    .from('child_personal_schedules')
    .update(row)
    .eq('id', input.id)
    .select('id')
  if (error) throw new Error('일정 저장에 실패했어요.')
  if ((data ?? []).length === 0) throw new Error('권한이 없어요.')

  revalidatePath('/calendar')
}

export async function deletePersonalSchedule(id: string): Promise<void> {
  const { supabase } = await requireUser()

  const { data, error } = await supabase
    .from('child_personal_schedules')
    .delete()
    .eq('id', id)
    .select('id')
  if (error) throw new Error('일정 삭제에 실패했어요.')
  if ((data ?? []).length === 0) throw new Error('권한이 없어요.')

  revalidatePath('/calendar')
}
