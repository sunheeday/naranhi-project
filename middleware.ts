import { createServerClient } from '@supabase/ssr'
import { NextResponse, type NextRequest } from 'next/server'
import { appendNextParam } from './lib/auth/redirect'

const PUBLIC_PATHS = [
  '/demo',
  '/login',
  '/auth/callback',
  '/api/auth/dev-login',
  '/api/health',
  '/api/supabase/health',
  '/api/locale',
]

export async function middleware(request: NextRequest) {
  const isPreview = process.env.NEXT_PUBLIC_UI_PREVIEW === 'true'
    || request.cookies.get('ui_preview')?.value === 'true'

  if (isPreview) {
    return NextResponse.next({ request })
  }

  let response = NextResponse.next({ request })

  const supabase = createServerClient(
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

  const { data: { user } } = await supabase.auth.getUser()

  const pathname = request.nextUrl.pathname
  const isPublic = PUBLIC_PATHS.some((p) => pathname.startsWith(p))

  if (!user && !isPublic) {
    return NextResponse.redirect(
      new URL(appendNextParam('/login', `${pathname}${request.nextUrl.search}`), request.url)
    )
  }

  return response
}

export const config = {
  matcher: ['/((?!_next/static|_next/image|favicon.ico|icons|manifest.json).*)'],
}
