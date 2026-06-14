'use client'

import Image from 'next/image'
import { useEffect, useRef, useState } from 'react'

const ALLOWED_TYPES = ['image/jpeg', 'image/png', 'image/webp', 'image/heic', 'image/heif']
const MAX_SIZE_BYTES = 10 * 1024 * 1024

export interface CameraUploadLabels {
  ocrTab: string
  messageTab: string
  eyebrow: string
  title: string
  subtitle: string
  tipsTitle: string
  tips: string[]
  chooseImage: string
  retake: string
  submit: string
  uploading: string
  ready: string
  empty: string
  formatError: string
  sizeError: string
  uploadError: string
  success: string
  extractedTitle: string
  translatedTitle: string
  unreadableWarning: string
  swipeHint: string
  messageCardTitle: string
  messageCardBody: string
  messagePlaceholder: string
  messageTranslate: string
  messageTranslating: string
  messageTranslatedTitle: string
  messageCopy: string
  messageCopied: string
  messageError: string
}

interface UploadResult {
  extractedText: string
  translatedText: string
  isReadable: boolean
  warnings: string[]
}

export default function CameraUploadForm({
  childId,
  labels,
}: {
  childId: string
  labels: CameraUploadLabels
}) {
  const inputRef = useRef<HTMLInputElement>(null)
  const previewUrlRef = useRef<string | null>(null)
  const [file, setFile] = useState<File | null>(null)
  const [previewUrl, setPreviewUrl] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [result, setResult] = useState<UploadResult | null>(null)
  const [isUploading, setUploading] = useState(false)
  const [draftMessage, setDraftMessage] = useState('')
  const [translatedMessage, setTranslatedMessage] = useState('')
  const [messageError, setMessageError] = useState<string | null>(null)
  const [isTranslatingMessage, setIsTranslatingMessage] = useState(false)
  const [copied, setCopied] = useState(false)
  const [activeTab, setActiveTab] = useState<'ocr' | 'message'>('ocr')

  useEffect(() => {
    return () => {
      if (previewUrlRef.current) {
        URL.revokeObjectURL(previewUrlRef.current)
      }
    }
  }, [])

  function handleFile(nextFile: File) {
    if (!ALLOWED_TYPES.includes(nextFile.type)) {
      setError(labels.formatError)
      return
    }

    if (nextFile.size > MAX_SIZE_BYTES) {
      setError(labels.sizeError)
      return
    }

    if (previewUrlRef.current) {
      URL.revokeObjectURL(previewUrlRef.current)
    }

    const nextPreviewUrl = URL.createObjectURL(nextFile)
    previewUrlRef.current = nextPreviewUrl
    setPreviewUrl(nextPreviewUrl)
    setFile(nextFile)
    setError(null)
    setResult(null)
  }

  async function handleSubmit() {
    if (!file || isUploading) return

    setUploading(true)
    setError(null)
    setResult(null)

    try {
      const formData = new FormData()
      formData.append('file', file)
      formData.append('childId', childId)

      const response = await fetch('/api/notices/upload', {
        method: 'POST',
        body: formData,
      })
      const body = await response.json().catch(() => ({}))

      if (!response.ok) {
        throw new Error(typeof body.error === 'string' ? body.error : labels.uploadError)
      }

      setResult({
        extractedText: typeof body.extractedText === 'string' ? body.extractedText : '',
        translatedText: typeof body.translatedText === 'string' ? body.translatedText : '',
        isReadable: body.ocr?.is_readable !== false,
        warnings: Array.isArray(body.ocr?.warnings)
          ? body.ocr.warnings.filter((item: unknown): item is string => typeof item === 'string')
          : [],
      })
    } catch (uploadError) {
      setError(uploadError instanceof Error ? uploadError.message : labels.uploadError)
    } finally {
      setUploading(false)
    }
  }

  async function handleTranslateMessage() {
    const nextMessage = draftMessage.trim()
    if (!nextMessage || isTranslatingMessage) return

    setIsTranslatingMessage(true)
    setMessageError(null)
    setTranslatedMessage('')
    setCopied(false)

    try {
      const response = await fetch('/api/camera/translate-message', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: nextMessage }),
      })
      const body = await response.json().catch(() => ({}))
      if (!response.ok) {
        throw new Error(typeof body.error === 'string' ? body.error : labels.messageError)
      }
      setTranslatedMessage(typeof body.translatedText === 'string' ? body.translatedText : '')
    } catch (translationError) {
      setMessageError(translationError instanceof Error ? translationError.message : labels.messageError)
    } finally {
      setIsTranslatingMessage(false)
    }
  }

  async function handleCopy() {
    if (!translatedMessage.trim()) return
    try {
      await navigator.clipboard.writeText(translatedMessage)
      setCopied(true)
      window.setTimeout(() => setCopied(false), 1800)
    } catch {
      setCopied(false)
    }
  }

  return (
    <section className="flex flex-1 flex-col gap-5 px-6 pt-6">
      <div className="flex gap-2 rounded-2xl bg-primary-soft p-1">
        <button
          type="button"
          onClick={() => setActiveTab('ocr')}
          aria-pressed={activeTab === 'ocr'}
          className={`flex-1 rounded-xl px-4 py-2.5 text-sm font-bold transition ${
            activeTab === 'ocr' ? 'bg-surface text-ink shadow-soft' : 'text-primary-active'
          }`}
        >
          {labels.ocrTab}
        </button>
        <button
          type="button"
          onClick={() => setActiveTab('message')}
          aria-pressed={activeTab === 'message'}
          className={`flex-1 rounded-xl px-4 py-2.5 text-sm font-bold transition ${
            activeTab === 'message' ? 'bg-surface text-ink shadow-soft' : 'text-primary-active'
          }`}
        >
          {labels.messageTab}
        </button>
      </div>

      {activeTab === 'ocr' ? (
        <div className="rounded-2xl bg-primary-soft p-5 shadow-card">
          <p className="text-xs font-bold uppercase tracking-[0.12em] text-primary-active">{labels.eyebrow}</p>
          <h2 className="mt-2 text-2xl font-extrabold text-ink text-readable" style={{ letterSpacing: '-0.02em' }}>
            {labels.title}
          </h2>
          <p className="mt-2 text-sm text-body text-readable">{labels.subtitle}</p>
        </div>
      ) : null}

      {activeTab === 'ocr' ? (
        <>
          <div className="rounded-card border border-hairline bg-surface p-4 shadow-soft">
            <button
              type="button"
              aria-label={file ? labels.retake : labels.chooseImage}
              onClick={() => inputRef.current?.click()}
              className="relative flex min-h-[260px] w-full flex-col items-center justify-center overflow-hidden rounded-card border-2 border-dashed border-primary/35 bg-canvas text-center active:bg-primary-soft"
            >
              {previewUrl ? (
                <Image src={previewUrl} alt="" fill className="object-contain" unoptimized />
              ) : (
                <div className="flex flex-col items-center gap-3 px-6">
                  <span className="flex h-16 w-16 items-center justify-center rounded-full bg-primary text-white shadow-btn-primary">
                    <CameraGlyph />
                  </span>
                  <p className="text-sm font-semibold text-ink">{labels.chooseImage}</p>
                  <p className="text-xs text-muted text-readable">{labels.empty}</p>
                </div>
              )}
            </button>

            <input
              ref={inputRef}
              type="file"
              accept="image/*"
              className="hidden"
              onChange={event => {
                const selected = event.target.files?.[0]
                if (selected) handleFile(selected)
                event.currentTarget.value = ''
              }}
            />

            <div className="mt-4 flex items-center justify-between gap-3">
              <div className="min-w-0">
                <p className="truncate text-sm font-semibold text-ink">
                  {file ? file.name : labels.chooseImage}
                </p>
                {file ? <p className="text-xs text-success">{labels.ready}</p> : null}
              </div>
              <button
                type="button"
                onClick={() => inputRef.current?.click()}
                className="h-10 shrink-0 rounded-btn border border-border bg-surface px-4 text-sm font-semibold text-ink"
              >
                {file ? labels.retake : labels.chooseImage}
              </button>
            </div>
          </div>

          <div className="rounded-card bg-brand-sun-soft p-4">
            <h3 className="text-sm font-bold text-ink">{labels.tipsTitle}</h3>
            <ul className="mt-2 flex flex-col gap-1.5 text-sm text-body">
              {labels.tips.map(tip => (
                <li key={tip} className="text-readable">• {tip}</li>
              ))}
            </ul>
          </div>

          {error ? (
            <p role="alert" className="rounded-btn border border-red-200 bg-red-50 px-4 py-3 text-sm text-error">
              {error}
            </p>
          ) : null}

          <section className="rounded-card bg-cat-supply-bg p-4 text-sm text-cat-supply">
            {result ? (
              <div role="status" className="flex flex-col gap-3">
                <p className="font-bold">{labels.success}</p>
                {!result.isReadable ? (
                  <p className="rounded-btn bg-white/70 px-3 py-2 text-error">{labels.unreadableWarning}</p>
                ) : null}
                {result.warnings.length > 0 ? (
                  <p className="text-xs text-readable">{result.warnings.join(' ')}</p>
                ) : null}
                <div>
                  <h3 className="text-xs font-bold uppercase tracking-[0.08em]">{labels.extractedTitle}</h3>
                  <p className="mt-1 whitespace-pre-wrap text-sm text-ink text-readable">
                    {result.extractedText || '-'}
                  </p>
                </div>
                <div>
                  <h3 className="text-xs font-bold uppercase tracking-[0.08em]">{labels.translatedTitle}</h3>
                  <p className="mt-1 whitespace-pre-wrap text-sm text-ink text-readable">
                    {result.translatedText || '-'}
                  </p>
                </div>
              </div>
            ) : (
              <div className="flex min-h-[220px] flex-col justify-center gap-3">
                <p className="font-bold">{labels.extractedTitle}</p>
                <p className="text-readable text-sm text-ink">{labels.swipeHint}</p>
              </div>
            )}
          </section>
        </>
      ) : (
        <section className="rounded-card border border-hairline bg-surface p-4 shadow-soft">
          <div className="flex flex-col gap-3">
            <div>
              <h3 className="text-base font-bold text-ink">{labels.messageCardTitle}</h3>
              <p className="mt-1 text-sm text-body text-readable">{labels.messageCardBody}</p>
            </div>

            <textarea
              value={draftMessage}
              onChange={event => setDraftMessage(event.target.value)}
              placeholder={labels.messagePlaceholder}
              className="min-h-[132px] w-full rounded-card border border-border bg-canvas px-4 py-3 text-sm text-ink outline-none placeholder:text-muted focus:border-primary"
            />

            <button
              type="button"
              disabled={!draftMessage.trim() || isTranslatingMessage}
              onClick={handleTranslateMessage}
              className="h-11 rounded-btn bg-primary text-sm font-bold text-on-primary shadow-btn-primary disabled:opacity-40 disabled:shadow-none"
            >
              {isTranslatingMessage ? labels.messageTranslating : labels.messageTranslate}
            </button>

            {messageError ? (
              <p role="alert" className="rounded-btn border border-red-200 bg-red-50 px-3 py-2 text-sm text-error">
                {messageError}
              </p>
            ) : null}

            <div className="rounded-card bg-primary-soft p-4">
              <div className="flex items-center justify-between gap-3">
                <h4 className="text-xs font-bold uppercase tracking-[0.08em] text-primary-active">
                  {labels.messageTranslatedTitle}
                </h4>
                <button
                  type="button"
                  onClick={handleCopy}
                  disabled={!translatedMessage.trim()}
                  className="rounded-btn border border-border bg-surface px-3 py-1.5 text-xs font-semibold text-ink disabled:opacity-40"
                >
                  {copied ? labels.messageCopied : labels.messageCopy}
                </button>
              </div>
              <p className="mt-2 whitespace-pre-wrap text-sm text-ink text-readable">
                {translatedMessage || '-'}
              </p>
            </div>
          </div>
        </section>
      )}

      <button
        type="button"
        disabled={!file || isUploading}
        onClick={handleSubmit}
        className="mt-auto h-12 w-full rounded-btn bg-primary text-base font-bold text-on-primary shadow-btn-primary disabled:opacity-40 disabled:shadow-none"
      >
        {isUploading ? labels.uploading : labels.submit}
      </button>
    </section>
  )
}

function CameraGlyph() {
  return (
    <svg width="30" height="30" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
      <path d="M9 3 7.17 5H5c-1.1 0-2 .9-2 2v11c0 1.1.9 2 2 2h14c1.1 0 2-.9 2-2V7c0-1.1-.9-2-2-2h-2.17L15 3H9zm3 15a5 5 0 1 1 0-10 5 5 0 0 1 0 10zm0-2.1a2.9 2.9 0 1 0 0-5.8 2.9 2.9 0 0 0 0 5.8z"/>
    </svg>
  )
}
