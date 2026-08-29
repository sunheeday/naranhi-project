import AdminLoginForm from './AdminLoginForm'

/** 유일한 미인증 관리자 경로. (protected) 그룹 밖에 두어야 이중 방어 레이아웃의
 *  세션 검사에 걸리지 않는다. middleware 의 adminGate 도 이 경로만 예외로 통과시킨다. */
export default function AdminLoginPage() {
  return (
    <main className="flex min-h-screen flex-col items-center justify-center gap-6 p-6">
      <h1 className="text-lg font-semibold">나란히 운영 콘솔</h1>
      <AdminLoginForm />
    </main>
  )
}
