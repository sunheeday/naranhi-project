import { NextResponse } from 'next/server'

export async function GET(request: Request) {
  const next = new URL('/', request.url)
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
