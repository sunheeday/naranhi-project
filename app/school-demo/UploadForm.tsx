"use client";

import { useRef, useState } from "react";

const ALLOWED_TYPES = ["image/jpeg", "image/png", "image/webp", "application/pdf"];

export default function UploadForm({ childId }: { childId: string }) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [noticeId, setNoticeId] = useState<string | null>(null);
  const [isUploading, setUploading] = useState(false);

  function handleFile(nextFile: File) {
    if (!ALLOWED_TYPES.includes(nextFile.type)) {
      setError("PDF 또는 이미지 파일만 업로드할 수 있어요.");
      return;
    }
    if (nextFile.size > 10 * 1024 * 1024) {
      setError("파일 크기는 10MB 이하여야 합니다.");
      return;
    }
    setError(null);
    setNoticeId(null);
    setFile(nextFile);
  }

  async function handleUpload() {
    if (!file || isUploading) return;

    setUploading(true);
    setError(null);

    try {
      const formData = new FormData();
      formData.append("file", file);
      formData.append("childId", childId);

      const response = await fetch("/api/notices/upload", {
        method: "POST",
        body: formData
      });
      const body = await response.json().catch(() => ({}));

      if (!response.ok) {
        throw new Error(body.error ?? "업로드에 실패했어요.");
      }

      setNoticeId(body.noticeId);
    } catch (uploadError) {
      setError(uploadError instanceof Error ? uploadError.message : "오류가 발생했어요.");
    } finally {
      setUploading(false);
    }
  }

  return (
    <div className="flex flex-col gap-5">
      <div
        onDrop={event => {
          event.preventDefault();
          const dropped = event.dataTransfer.files[0];
          if (dropped) handleFile(dropped);
        }}
        onDragOver={event => event.preventDefault()}
        className="border-2 border-dashed border-border rounded-card bg-surface p-6 flex flex-col items-center gap-3 text-center"
      >
        <span className="text-4xl" aria-hidden="true">📄</span>
        <p className="text-sm text-text-secondary">
          {file ? file.name : "파일을 끌어다 놓거나 선택해 주세요."}
        </p>
        <button
          type="button"
          onClick={() => inputRef.current?.click()}
          className="px-5 h-11 rounded-btn border border-border bg-surface text-sm font-semibold text-text-primary"
        >
          파일 선택
        </button>
        <input
          ref={inputRef}
          type="file"
          accept=".pdf,.jpg,.jpeg,.png,.webp"
          className="hidden"
          onChange={event => {
            const selected = event.target.files?.[0];
            if (selected) handleFile(selected);
          }}
        />
      </div>

      {error && <p role="alert" className="text-sm text-red-500">{error}</p>}
      {noticeId && (
        <p role="status" className="text-sm text-card-supply bg-card-supply-bg rounded-btn px-4 py-3">
          업로드 완료. 공지 ID: {noticeId}
        </p>
      )}

      <button
        type="button"
        disabled={!file || isUploading}
        onClick={handleUpload}
        className="w-full h-12 rounded-btn bg-primary text-white text-base font-semibold disabled:opacity-40"
      >
        {isUploading ? "업로드 중..." : "업로드하기"}
      </button>
    </div>
  );
}
