import 'server-only'

import type { SupabaseClient } from '@supabase/supabase-js'

import { defaultBellSchedule, type BellPeriod } from '@/lib/bell-schedule'
import type { Database } from '@/types/database'

/** 이 학교의 «쓸 수 있는» 교시 시각표를 돌려준다.
 *
 *  승인된 행(confirmed_at is not null)이 있으면 그것을 쓴다. 없으면 학교급 표준값을
 *  심고 그것을 돌려준다.
 *
 *  표준값은 심을 때 곧바로 승인 상태로 넣는다 — 추정치이긴 하나 사람이 확인할
 *  대상이 아니라 «확인할 것이 없어서» 쓰는 기본값이기 때문이다. 사람 승인을 기다리는
 *  것은 홈페이지에서 AI 가 읽어낸 행(source='homepage')뿐이다. 그쪽은 잘못 읽으면
 *  부모에게 틀린 하교 시각이 알림으로 나간다.
 *
 *  service_role 클라이언트를 받아야 한다 — 부모에게는 이 표의 INSERT 권한이 없다.
 */
export async function ensureBellSchedule(
  service: SupabaseClient<Database>,
  schoolId: string,
  schoolName: string,
): Promise<BellPeriod[]> {
  const { data, error } = await service
    .from('school_bell_schedules')
    .select('period, start_time, end_time')
    .eq('school_id', schoolId)
    .not('confirmed_at', 'is', null)
    .order('period')
  if (error) throw error

  if ((data ?? []).length > 0) {
    return (data ?? []).map(toBellPeriod)
  }

  const periods = defaultBellSchedule(schoolName)
  const now = new Date().toISOString()
  // 동시에 두 요청이 들어와도 먼저 넣은 쪽이 이기게 둔다(unique(school_id, period)).
  const { error: seedError } = await service
    .from('school_bell_schedules')
    .upsert(
      periods.map(p => ({
        school_id: schoolId,
        period: p.period,
        start_time: p.startTime,
        end_time: p.endTime,
        source: 'default' as const,
        confirmed_at: now,
      })),
      { onConflict: 'school_id,period', ignoreDuplicates: true },
    )
  // 시딩 실패가 화면을 막지는 않는다 — 계산에 쓸 표준값은 이미 손에 있다.
  if (seedError) {
    console.error('[bell-schedule] 표준값 시딩 실패:', seedError.message)
  }
  return periods
}

function toBellPeriod(row: { period: number; start_time: string; end_time: string }): BellPeriod {
  return {
    period: row.period,
    startTime: row.start_time.slice(0, 5),
    endTime: row.end_time.slice(0, 5),
  }
}
