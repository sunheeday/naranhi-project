import { NextResponse } from 'next/server'

export async function GET(request: Request) {
  const next = new URL('/login', request.url)
  const response = NextResponse.redirect(next)

  response.cookies.set('ui_preview', '', {
    path: '/',
    maxAge: 0,
    sameSite: 'lax',
  })

  return response
}
