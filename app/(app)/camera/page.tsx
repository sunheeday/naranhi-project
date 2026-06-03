import { cookies } from 'next/headers'
import { redirect } from 'next/navigation'
import BrandHeader from '@/components/brand/BrandHeader'
import { defaultLocale, isValidLocale, type Locale } from '@/lib/i18n'
import { createSupabaseServerClient } from '@/lib/supabase/server'
import { isUiPreviewEnabled } from '@/lib/ui-preview'
import CameraUploadForm, { type CameraUploadLabels } from './CameraUploadForm'

const cameraFallback: CameraUploadLabels = {
  eyebrow: '가정통신문 촬영',
  title: '하이클래스 담임선생님 공지, 카카오톡 공지를 사진으로 넣어주세요',
  subtitle: '안내문을 촬영하거나 캡처된 이미지로 선택하면, 번역해드릴게요.',
  tipsTitle: '잘 인식되는 촬영 팁',
  tips: [
    '문서 네 모서리가 보이게 찍어주세요.',
    '그림자가 적은 밝은 곳이 좋아요.',
    '글자가 흔들리면 다시 촬영해 주세요.',
  ],
  chooseImage: '사진 선택',
  retake: '다시 선택',
  submit: 'OCR·번역하기',
  uploading: '인식 및 번역 중...',
  ready: '선택 완료',
  empty: '카메라로 촬영하거나 앨범에서 이미지를 선택할 수 있어요.',
  formatError: '이미지 파일만 업로드할 수 있어요.',
  sizeError: '파일 크기는 10MB 이하여야 합니다.',
  uploadError: 'OCR 또는 번역에 실패했어요. 잠시 후 다시 시도해주세요.',
  success: 'OCR과 번역이 완료됐어요.',
  extractedTitle: '추출된 원문',
  translatedTitle: '번역 결과',
  unreadableWarning: '사진의 글자를 충분히 읽지 못했어요. 더 밝고 선명하게 다시 촬영해 주세요.',
}

function labelsFor(messages: any): CameraUploadLabels {
  const camera = messages.camera ?? {}
  return {
    eyebrow: camera.eyebrow ?? cameraFallback.eyebrow,
    title: camera.title ?? cameraFallback.title,
    subtitle: camera.subtitle ?? cameraFallback.subtitle,
    tipsTitle: camera.tips_title ?? cameraFallback.tipsTitle,
    tips: camera.tips ?? cameraFallback.tips,
    chooseImage: camera.choose_image ?? cameraFallback.chooseImage,
    retake: camera.retake ?? cameraFallback.retake,
    submit: camera.submit ?? cameraFallback.submit,
    uploading: camera.uploading ?? cameraFallback.uploading,
    ready: camera.ready ?? cameraFallback.ready,
    empty: camera.empty ?? cameraFallback.empty,
    formatError: camera.error_format ?? cameraFallback.formatError,
    sizeError: camera.error_size ?? cameraFallback.sizeError,
    uploadError: camera.error_upload ?? cameraFallback.uploadError,
    success: camera.success ?? cameraFallback.success,
    extractedTitle: camera.extracted_title ?? cameraFallback.extractedTitle,
    translatedTitle: camera.translated_title ?? cameraFallback.translatedTitle,
    unreadableWarning: camera.unreadable_warning ?? cameraFallback.unreadableWarning,
  }
}

export default async function CameraPage() {
  const cookieStore = await cookies()
  const cookieLocale = cookieStore.get('locale')?.value
  const locale: Locale = isValidLocale(cookieLocale) ? cookieLocale : defaultLocale
  const messages = (await import(`@/messages/${locale}.json`)).default

  let childId = 'preview-child'
  let childLabel = ''

  if (isUiPreviewEnabled()) {
    childLabel = '나란히초등학교 3-2'
  } else {
    const supabase = await createSupabaseServerClient()
    const { data: { user } } = await supabase.auth.getUser()
    if (!user) redirect('/login')

    const { data: child } = await supabase
      .from('children')
      .select('id, school_name, grade, class_no')
      .eq('user_id', user.id)
      .order('created_at', { ascending: false })
      .limit(1)
      .maybeSingle()

    if (!child) redirect('/onboarding')

    childId = child.id
    childLabel = `${child.school_name} ${child.grade}-${child.class_no ?? ''}`
  }

  return (
    <main className="flex min-h-screen flex-col pb-24">
      <BrandHeader
        title={messages.camera?.nav_title ?? messages.nav.camera ?? '촬영'}
        subtitle={childLabel || undefined}
        character="standingPaper"
      />
      <CameraUploadForm childId={childId} labels={labelsFor(messages)} />
    </main>
  )
}
