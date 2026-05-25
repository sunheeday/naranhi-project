import { createServerClient } from '@supabase/ssr'
import { NextResponse, type NextRequest } from 'next/server'
import type { Database } from '@/types/database'
import { safeNextPath } from '@/lib/auth/redirect'

export async function POST(request: NextRequest) {
  if (process.env.NODE_ENV === 'production' || process.env.DEV_LOGIN_ENABLED !== 'true') {
    return NextResponse.json({ ok: false, error: 'dev_login_disabled' }, { status: 404 })
  }

  const email = process.env.DEV_LOGIN_EMAIL
  const password = process.env.DEV_LOGIN_PASSWORD
  if (!email || !password) {
    return NextResponse.json({ ok: false, error: 'dev_login_not_configured' }, { status: 503 })
  }

  const body = await request.json().catch(() => null)
  const next = safeNextPath(body?.next)
  const response = NextResponse.json({ ok: true, next })

  const supabase = createServerClient<Database>(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY!,
    {
      cookies: {
        getAll() {
          return request.cookies.getAll()
        },
        setAll(cookiesToSet) {
          cookiesToSet.forEach(({ name, value, options }) => {
            request.cookies.set(name, value)
            response.cookies.set(name, value, options)
          })
        },
      },
    }
  )

  const { error } = await supabase.auth.signInWithPassword({ email, password })
  if (error) {
    return NextResponse.json({ ok: false, error: 'dev_login_failed' }, { status: 401 })
  }

  return response
}
