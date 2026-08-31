/** 관리자 셸. 학부모 레이아웃(app/(app)/layout.tsx)을 상속하지 않는다 —
 *  BottomNav·번역 배너 같은 학부모 UI 가 관리자 화면에 섞이면 안 되고,
 *  나중에 별도 서비스로 떼어낼 때 잘라낼 경계가 여기여야 한다. */
export default function AdminShellLayout({ children }: { children: React.ReactNode }) {
  return <div className="min-h-screen bg-slate-950 text-slate-100">{children}</div>
}
