import { NextResponse, type NextRequest } from 'next/server'
import { publicOrigin } from '@/lib/request-origin'

export async function GET(request: NextRequest) {
  const next = new URL('/login', publicOrigin(request))
  const response = NextResponse.redirect(next)

  response.cookies.set('ui_preview', '', {
    path: '/',
    maxAge: 0,
    sameSite: 'lax',
  })

  return response
}
