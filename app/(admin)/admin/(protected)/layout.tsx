import { redirect } from 'next/navigation'
import { getAdminSession } from '@/lib/admin/session'

/** 이중 방어 ②. middleware(adminGate)는 쿠키 «존재» 만 봤다 — 위조·만료·폐기된
 *  쿠키는 여기서 걸린다. 이 레이아웃 아래에 놓인 모든 페이지가 자동으로 검사를 받는다.
 *
 *  여기서는 getAdminSession()(null 반환)을 쓴다 — 페이지 내비게이션이므로 미인증
 *  판정 결과는 /admin/login 리다이렉트가 맞다(존재 자체를 숨겨야 하는 API 응답과
 *  다르다: 로그인 페이지는 애초에 공개 진입점이다). requireAdminSession()이 던지는
 *  AdminUnauthorizedError → 404 매핑은 API 라우트·개별 페이지의 몫이다. */
export default async function AdminProtectedLayout({
  children,
}: {
  children: React.ReactNode
}) {
  const session = await getAdminSession()
  if (!session) {
    redirect('/admin/login')
  }

  return (
    <div className="mx-auto flex min-h-screen w-full max-w-6xl flex-col gap-4 p-6">
      <header className="flex items-center justify-between border-b border-slate-800 pb-3">
        <nav className="flex gap-4 text-sm">
          <a href="/admin">대시보드</a>
          <a href="/admin/jobs">잡 큐</a>
          <a href="/admin/schools">학교 수집</a>
          <a href="/admin/schedulers">스케줄러</a>
          <a href="/admin/notices">공지 검수</a>
          <a href="/admin/reviews">번역 검토</a>
          <a href="/admin/runs">실행 이력</a>
        </nav>
        <form action="/api/admin/logout" method="post">
          <span className="mr-3 text-xs text-slate-400">
            {session.displayName ?? session.username}
          </span>
          <button type="submit" className="text-sm underline">로그아웃</button>
        </form>
      </header>
      {children}
    </div>
  )
}
