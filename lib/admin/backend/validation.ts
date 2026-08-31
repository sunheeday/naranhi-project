/**
 * 어드민 API 요청 본문 검증 스키마(zod).
 * 라우트 핸들러에서 입력을 신뢰하기 전에 반드시 통과시킨다.
 */

import { z } from 'zod'
import { NOTICE_CATEGORIES, EVENT_TYPES, AUDIENCES } from '@/lib/admin/types'

const category = z.enum(NOTICE_CATEGORIES as [string, ...string[]])
const eventType = z.enum(EVENT_TYPES as [string, ...string[]])
const audience = z.enum(AUDIENCES as [string, ...string[]])

export const noticeInputSchema = z.object({
  title: z.string().trim().min(1, '제목을 입력해 주세요.').max(120),
  body: z.string().trim().min(1, '내용을 입력해 주세요.').max(5000),
  category,
  audience,
  pinned: z.boolean().default(false),
})

export const eventInputSchema = z.object({
  title: z.string().trim().min(1, '일정 제목을 입력해 주세요.').max(120),
  date: z.string().regex(/^\d{4}-\d{2}-\d{2}$/, '날짜 형식이 올바르지 않습니다.'),
  time: z
    .string()
    .regex(/^([01]\d|2[0-3]):[0-5]\d$/, '시간 형식이 올바르지 않습니다.')
    .or(z.literal(''))
    .default(''),
  type: eventType,
  audience,
  memo: z.string().trim().max(2000).default(''),
})

export const messageInputSchema = z.object({
  title: z.string().trim().min(1, '제목을 입력해 주세요.').max(120),
  body: z.string().trim().min(1, '내용을 입력해 주세요.').max(5000),
  audience,
  recipient: z.string().trim().min(1, '받는 대상을 입력해 주세요.').max(120),
})

export const pinPatchSchema = z.object({
  pinned: z.boolean(),
})
