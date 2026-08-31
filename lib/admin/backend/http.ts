/** 어드민 API 공통 응답 헬퍼. */

import { NextResponse } from 'next/server'
import type { ZodError } from 'zod'

export function ok<T>(data: T, init?: number) {
  return NextResponse.json({ ok: true, data }, { status: init ?? 200 })
}

export function fail(error: string, status = 400) {
  return NextResponse.json({ ok: false, error }, { status })
}

export function invalid(err: ZodError) {
  const first = err.issues[0]
  return NextResponse.json(
    { ok: false, error: first?.message ?? 'invalid_request', issues: err.issues },
    { status: 422 },
  )
}

/** 저장소/서버 오류를 500으로 감싼다. */
export function serverError(e: unknown) {
  const message = e instanceof Error ? e.message : 'internal_error'
  return NextResponse.json({ ok: false, error: message }, { status: 500 })
}
