import 'server-only'
import { cookies } from 'next/headers'

export function previewChildInfo() {
  return "민준 · 나란히초등학교 3-2";
}

export async function isUiPreviewEnabled() {
  if (process.env.NEXT_PUBLIC_UI_PREVIEW === 'true') {
    return true
  }

  const cookieStore = await cookies()
  return cookieStore.get('ui_preview')?.value === 'true'
}
