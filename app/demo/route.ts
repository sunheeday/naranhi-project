import { NextResponse, type NextRequest } from 'next/server'
import { publicOrigin } from '@/lib/request-origin'

export async function GET(request: NextRequest) {
  const next = new URL('/', publicOrigin(request))
  const response = NextResponse.redirect(next)

  response.cookies.set('ui_preview', 'true', {
    path: '/',
    maxAge: 60 * 60 * 24 * 7,
    sameSite: 'lax',
  })
  response.cookies.set('locale', 'ar', {
    path: '/',
    maxAge: 60 * 60 * 24 * 7,
    sameSite: 'lax',
  })

  return response
}
