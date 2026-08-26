import { cookies } from 'next/headers'
import { redirect } from 'next/navigation'
import BrandHeader from '@/components/brand/BrandHeader'
import { defaultLocale, isValidLocale, type Locale } from '@/lib/i18n'
import { getLatestChildForUser } from '@/lib/server-cache'
import { createSupabaseServerClient } from '@/lib/supabase/server'
import CameraUploadForm, { type CameraUploadLabels } from './CameraUploadForm'

const cameraFallback: CameraUploadLabels = {
  ocrTab: 'OCR',
  messageTab: '메시지 번역',
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
  swipeHint: '옆으로 넘겨서 다른 카드를 확인해 보세요.',
  messageCardTitle: '선생님께 보낼 말 자동 번역',
  messageCardBody: '학부모가 보내고 싶은 문장을 입력하면 한국어로 자연스럽게 번역해 드려요.',
  messagePlaceholder: '보내고 싶은 문장을 입력해 주세요.',
  messageTranslate: '한국어로 번역',
  messageTranslating: '한국어로 번역 중...',
  messageTranslatedTitle: '한국어로 번역된 문장',
  messageCopy: '복사',
  messageCopied: '복사됨',
  messageError: '메시지 번역에 실패했어요. 잠시 후 다시 시도해주세요.',
}

function labelsFor(messages: any): CameraUploadLabels {
  const camera = messages.camera ?? {}
  return {
    ocrTab: camera.ocr_tab ?? cameraFallback.ocrTab,
    messageTab: camera.message_tab ?? cameraFallback.messageTab,
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
    swipeHint: camera.swipe_hint ?? cameraFallback.swipeHint,
    messageCardTitle: camera.message_card_title ?? cameraFallback.messageCardTitle,
    messageCardBody: camera.message_card_body ?? cameraFallback.messageCardBody,
    messagePlaceholder: camera.message_placeholder ?? cameraFallback.messagePlaceholder,
    messageTranslate: camera.message_translate ?? cameraFallback.messageTranslate,
    messageTranslating: camera.message_translating ?? cameraFallback.messageTranslating,
    messageTranslatedTitle: camera.message_translated_title ?? cameraFallback.messageTranslatedTitle,
    messageCopy: camera.message_copy ?? cameraFallback.messageCopy,
    messageCopied: camera.message_copied ?? cameraFallback.messageCopied,
    messageError: camera.message_error ?? cameraFallback.messageError,
  }
}

export default async function CameraPage() {
  const cookieStore = await cookies()
  const cookieLocale = cookieStore.get('locale')?.value
  const locale: Locale = isValidLocale(cookieLocale) ? cookieLocale : defaultLocale
  const messages = (await import(`@/messages/${locale}.json`)).default

  const supabase = await createSupabaseServerClient()
  const { data: { user } } = await supabase.auth.getUser()
  if (!user) redirect('/login')

  const child = await getLatestChildForUser(user.id)

  if (!child) redirect('/onboarding')

  const childId = child.id
  const childLabel = `${child.school_name} ${child.grade}-${child.class_no ?? ''}`

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
