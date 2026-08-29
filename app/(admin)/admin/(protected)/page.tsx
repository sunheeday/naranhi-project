import { notFound } from 'next/navigation'
import { AdminUnauthorizedError, requireAdminSession } from '@/lib/admin/session'

export const dynamic = 'force-dynamic'

/** requireAdminSession() 은 상태코드 없는 AdminUnauthorizedError 만 던진다 — 여기서
 *  403 이 아니라 404 로 매핑한다(403은 「있지만 권한 없음」을 흘려 관리자 URL의
 *  존재를 알려준다). 정상 경로에서는 상위 (protected)/layout.tsx 가 이미
 *  getAdminSession() 으로 걸러내므로 이 catch 는 레이아웃 통과 이후 세션이
 *  폐기되는 경합(레이스) 등 방어적 상황에만 발동한다. */
export default async function AdminDashboardPage() {
  let session
  try {
    session = await requireAdminSession()
  } catch (error) {
    if (error instanceof AdminUnauthorizedError) {
      notFound()
    }
    throw error
  }

  return (
    <main className="flex flex-col gap-2">
      <h1 className="text-lg font-semibold">운영 대시보드</h1>
      <p className="text-sm text-slate-400">
        {session.displayName ?? session.username} · 세션 만료 {session.expiresAt}
      </p>
    </main>
  )
}
