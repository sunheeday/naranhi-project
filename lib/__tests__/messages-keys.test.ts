// 9개 언어 파일의 «키 집합»이 서로 같은지 본다.
// 키가 하나라도 빠지면 그 언어에서 undefined 가 렌더된다 — 화면에 빈칸으로 나가고
// 빌드도 타입검사도 잡아주지 않는 종류의 사고다.
import { test } from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync, readdirSync } from 'node:fs'
import { join } from 'node:path'

const DIR = join(process.cwd(), 'messages')
const LOCALES = ['ko', 'en', 'zh', 'vi', 'ru', 'ar', 'fr', 'id', 'th']

function flatten(value: unknown, prefix = ''): string[] {
  if (value === null || typeof value !== 'object' || Array.isArray(value)) return [prefix]
  return Object.entries(value as Record<string, unknown>)
    .flatMap(([k, v]) => flatten(v, prefix ? `${prefix}.${k}` : k))
}

function keysOf(locale: string): Set<string> {
  const raw = readFileSync(join(DIR, `${locale}.json`), 'utf-8')
  return new Set(flatten(JSON.parse(raw)))
}

test('messages 디렉터리에 기대한 9개 언어가 모두 있다', () => {
  const found = readdirSync(DIR)
    .filter(f => f.endsWith('.json'))
    .map(f => f.replace('.json', ''))
    .sort()
  assert.deepEqual(found, [...LOCALES].sort())
})

/** 사업 G 이전부터 비어 있던 자리. 이 테스트를 처음 붙였을 때(2026-08-30) 발견했고,
 *  사업 G 와 무관하므로 이번 범위에서 채우지 않았다. 여기에 «잠가» 두면 새 누락은
 *  실패로 잡히고 기존 6개만 통과한다. 채우고 나면 이 목록을 지운다. */
const KNOWN_GAPS: Record<string, string[]> = {
  zh: ['home.delete', 'home.deleting', 'home.delete_confirm_title', 'home.delete_confirm_body',
       'login.language_title', 'login.language_body'],
  vi: ['home.delete', 'home.deleting', 'home.delete_confirm_title', 'home.delete_confirm_body'],
  fr: ['login.language_title', 'login.language_body'],
  id: ['login.language_title', 'login.language_body'],
  th: ['login.language_title', 'login.language_body'],
}

test('9개 언어의 키 집합이 ko 와 같다 (기존 누락 6개 제외)', () => {
  const base = keysOf('ko')
  for (const locale of LOCALES) {
    if (locale === 'ko') continue
    const other = keysOf(locale)
    const allowed = new Set(KNOWN_GAPS[locale] ?? [])
    const missing = [...base].filter(k => !other.has(k) && !allowed.has(k))
    const extra = [...other].filter(k => !base.has(k))
    // 채워졌는데 목록에 남아 있으면 목록이 낡은 것이다 — 그것도 알려 준다.
    const stale = [...allowed].filter(k => other.has(k))
    assert.deepEqual(missing, [], `${locale}: ko 에 있는데 없는 키`)
    assert.deepEqual(extra, [], `${locale}: ko 에 없는데 있는 키`)
    assert.deepEqual(stale, [], `${locale}: KNOWN_GAPS 가 낡았다 — 목록에서 지울 것`)
  }
})

test('사업 G 가 더한 키가 9개 언어에 모두 있다', () => {
  const required = [
    'calendar.dismissal',
    'calendar.personal_section',
    'calendar.personal_add',
    'calendar.personal_delete_confirm_body',
    'calendar.personal_err_time_order',
    'settings.bell_title',
    'settings.bell_help',
    'settings.bell_label',
    'settings.bell_error',
  ]
  for (const locale of LOCALES) {
    const keys = keysOf(locale)
    for (const key of required) {
      assert.ok(keys.has(key), `${locale} 에 ${key} 없음`)
    }
  }
})

test('빈 문자열 값이 없다', () => {
  for (const locale of LOCALES) {
    const raw = JSON.parse(readFileSync(join(DIR, `${locale}.json`), 'utf-8'))
    const walk = (v: unknown, path: string): void => {
      if (typeof v === 'string') {
        assert.notEqual(v.trim(), '', `${locale}: ${path} 가 빈 문자열`)
        return
      }
      if (Array.isArray(v)) return v.forEach((item, i) => walk(item, `${path}[${i}]`))
      if (v && typeof v === 'object') {
        for (const [k, item] of Object.entries(v)) walk(item, path ? `${path}.${k}` : k)
      }
    }
    walk(raw, '')
  }
})
