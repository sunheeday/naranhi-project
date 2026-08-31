import type { Metadata } from 'next'
import AdminBottomNav from '@/components/admin/AdminBottomNav'

export const metadata: Metadata = {
  title: '나란히 선생님',
  description: '학교(선생님)용 어드민 데모',
}

export default function AdminLayout({ children }: { children: React.ReactNode }) {
  return (
    <>
      {children}
      <AdminBottomNav />
    </>
  )
}
