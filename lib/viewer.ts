import 'server-only'

import type { SupabaseClient } from '@supabase/supabase-js'

import { createSupabaseServerClient, createSupabaseServiceClient } from '@/lib/supabase/server'
import {
  ensureTestBypassChild,
  ensureTestBypassChildren,
  isTestEntryBypassEnabled,
} from '@/lib/test-entry-bypass'
import {
  getChildrenForUser,
  getLatestChildForUser,
  type CachedChildSummary,
} from '@/lib/server-cache'
import type { Database } from '@/types/database'

/** 지금 들어온 사람.
 *  - 진짜 로그인한 부모: 자기 자녀와 자기 권한의 DB 연결을 쓴다.
 *  - 시연(TEST_ENTRY_BYPASS) 방문자: 로그인이 없다. 자녀는 쿠키로 만든 «각자 화면» 객체이고,
 *    공지 같은 공용 자료는 서버 권한으로 읽는다. */
export interface Viewer {
  demo: boolean
  /** 진짜 로그인한 부모의 id. 시연이면 null. 사용자별 DB 자료(숨김 목록 등)는 이 값이 있을 때만 읽는다. */
  userId: string | null
  /** 캐시 키. 시연 방문자는 모두 같은 값이다. */
  key: string
  /** 공지 등을 읽는 DB 연결. */
  supabase: SupabaseClient<Database>
  latestChild(): Promise<CachedChildSummary | null>
  children(): Promise<CachedChildSummary[]>
}

/** «로그인했나?» 를 묻던 자리를 이 함수로 바꾼다.
 *
 *  진짜 로그인이 항상 먼저다 — 스위치가 켜져 있어도 로그인한 사람은 자기 자녀를 본다.
 *  로그인이 없고 스위치도 꺼져 있으면 null 을 돌려주고, 부르는 쪽이 예전처럼 /login 으로 보낸다.
 *  그래서 스위치가 꺼져 있으면 동작이 이 함수를 넣기 전과 똑같다. */
export async function getViewer(): Promise<Viewer | null> {
  const supabase = await createSupabaseServerClient()
  const { data: { user } } = await supabase.auth.getUser()

  if (user) {
    return {
      demo: false,
      userId: user.id,
      key: user.id,
      supabase,
      latestChild: () => getLatestChildForUser(user.id),
      children: () => getChildrenForUser(user.id),
    }
  }

  if (!isTestEntryBypassEnabled()) return null

  return {
    demo: true,
    userId: null,
    key: 'demo',
    supabase: createSupabaseServiceClient(),
    latestChild: () => ensureTestBypassChild(),
    children: () => ensureTestBypassChildren(),
  }
}
