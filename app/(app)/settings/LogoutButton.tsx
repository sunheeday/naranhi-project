'use client'

import { useRouter } from 'next/navigation'
import { createSupabaseBrowserClient } from '@/lib/supabase/client'

export default function LogoutButton({ label }: { label: string }) {
  const router = useRouter()

  async function handleLogout() {
    const supabase = createSupabaseBrowserClient()
    await supabase.auth.signOut()
    router.push('/login')
  }

  return (
    <button
      onClick={handleLogout}
      className="w-full h-12 rounded-btn border border-border bg-surface text-text-secondary text-base font-semibold active:scale-[0.98] transition-transform"
    >
      {label}
    </button>
  )
}
