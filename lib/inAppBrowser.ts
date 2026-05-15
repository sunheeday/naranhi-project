/**
 * 인앱 브라우저(WebView) 감지 및 외부 브라우저 전환 유틸.
 *
 * Google OAuth가 2021년부터 embedded WebView에서의 로그인을 전면 차단(403 disallowed_useragent)하기 때문에,
 * 카카오톡·인스타·페북 등에서 링크를 열면 로그인이 막힌다. 이를 우회하기 위해 앱별 URL 스킴으로 외부 브라우저를
 * 강제로 띄운다.
 */

export type InAppBrowserName =
  | 'kakaotalk'
  | 'line'
  | 'naver'
  | 'instagram'
  | 'facebook'
  | 'daum'
  | 'other'

export interface InAppBrowserDetection {
  isInApp: boolean
  name: InAppBrowserName | null
  /** 해당 앱이 외부 브라우저 전환 스킴을 지원하는지 */
  canOpenExternal: boolean
}

export function detectInAppBrowser(userAgent?: string): InAppBrowserDetection {
  if (typeof window === 'undefined' && !userAgent) {
    return { isInApp: false, name: null, canOpenExternal: false }
  }
  const ua = (userAgent ?? window.navigator.userAgent).toLowerCase()

  if (ua.includes('kakaotalk')) {
    return { isInApp: true, name: 'kakaotalk', canOpenExternal: true }
  }
  if (ua.includes(' line/') || ua.includes(' line ')) {
    return { isInApp: true, name: 'line', canOpenExternal: true }
  }
  if (ua.includes('naver(inapp') || ua.includes('naver;')) {
    return { isInApp: true, name: 'naver', canOpenExternal: true }
  }
  if (ua.includes('daumapps')) {
    return { isInApp: true, name: 'daum', canOpenExternal: false }
  }
  if (ua.includes('instagram')) {
    return { isInApp: true, name: 'instagram', canOpenExternal: false }
  }
  if (ua.includes('fban') || ua.includes('fbav') || ua.includes('fb_iab')) {
    return { isInApp: true, name: 'facebook', canOpenExternal: false }
  }

  // Android WebView: Chrome이 WebView로 임베드되면 UA에 '; wv)' 토큰이 붙는다.
  if (ua.includes('; wv)')) {
    return { isInApp: true, name: 'other', canOpenExternal: false }
  }

  return { isInApp: false, name: null, canOpenExternal: false }
}

/**
 * 현재 URL을 외부 브라우저로 열 수 있으면 리다이렉트를 수행하고 true를 반환한다.
 * 외부 전환이 불가능하면 false를 반환하고 호출자가 수동 안내를 보여주도록 한다.
 */
export function openInExternalBrowser(detection: InAppBrowserDetection, targetUrl: string): boolean {
  if (!detection.isInApp || !detection.canOpenExternal) return false

  switch (detection.name) {
    case 'kakaotalk': {
      window.location.href = `kakaotalk://web/openExternal?url=${encodeURIComponent(targetUrl)}`
      return true
    }
    case 'line': {
      // 라인은 현재 URL 뒤에 openExternalBrowser=1 쿼리를 붙이면 자동 외부 전환
      const url = new URL(targetUrl)
      url.searchParams.set('openExternalBrowser', '1')
      window.location.href = url.toString()
      return true
    }
    case 'naver': {
      window.location.href = `naversearchapp://inappbrowser?url=${encodeURIComponent(targetUrl)}&target=new&version=6`
      return true
    }
    default:
      return false
  }
}
