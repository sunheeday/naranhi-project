import 'server-only'

import type { SupabaseClient } from '@supabase/supabase-js'

import type { Database, PersonalScheduleColor } from '@/types/database'

export interface PersonalScheduleItem {
  id: string
  title: string
  /** 0=일 ~ 6=토 */
  dayOfWeek: number
  /** "HH:MM" */
  startTime: string
  endTime: string
  location: string | null
  memo: string | null
  color: PersonalScheduleColor
}

/** 자녀의 주간 반복 개인 일정.
 *
 *  RLS 가 본인 자녀로 스코프하므로 호출자는 세션이 붙은 클라이언트를 넘기면 된다.
 *  (기능명세서-자녀-개인일정.md 가 언급한 test-entry-bypass 목 데이터 경로는
 *   그 모듈이 이 저장소에 없어 넣지 않았다.) */
export async function fetchPersonalSchedulesForChild(
  client: SupabaseClient<Database>,
  childId: string,
): Promise<PersonalScheduleItem[]> {
  const { data, error } = await client
    .from('child_personal_schedules')
    .select('id, title, day_of_week, start_time, end_time, location, memo, color')
    .eq('child_id', childId)
    .order('day_of_week')
    .order('start_time')
  if (error) throw error

  return (data ?? []).map(row => ({
    id: row.id,
    title: row.title,
    dayOfWeek: row.day_of_week,
    startTime: row.start_time.slice(0, 5),
    endTime: row.end_time.slice(0, 5),
    location: row.location,
    memo: row.memo,
    color: row.color,
  }))
}
