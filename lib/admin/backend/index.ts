/**
 * 어드민 저장소 팩토리.
 *
 * 환경변수 `ADMIN_BACKEND`로 구현을 고른다.
 *   - (미설정) 또는 'memory' → 인메모리(기본, DB 불필요)
 *   - 'supabase'            → Supabase(admin_* 테이블). docs/admin-backend.md 참고.
 *
 * API 라우트 핸들러는 항상 `getAdminRepository()`만 호출하므로, DB 연동은 이 파일 한 곳의
 * 분기(그리고 환경변수)만으로 전환된다.
 */

import type { AdminRepository } from './repository'
import { MemoryAdminRepository } from './memory-repository'

let cached: AdminRepository | null = null

export function getAdminRepository(): AdminRepository {
  if (cached) return cached

  const backend = (process.env.ADMIN_BACKEND ?? 'memory').toLowerCase()

  if (backend === 'supabase') {
    // 지연 로딩: 실제로 선택될 때만 Supabase 모듈을 불러온다.
    // (require는 번들에 supabase 구현이 항상 포함되지 않도록 하는 목적)
    const { SupabaseAdminRepository } = require('./supabase-repository') as typeof import('./supabase-repository')
    cached = new SupabaseAdminRepository()
  } else {
    cached = new MemoryAdminRepository()
  }

  return cached
}

export type { AdminRepository } from './repository'
