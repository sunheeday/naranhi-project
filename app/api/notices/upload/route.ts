import { NextResponse, type NextRequest } from "next/server";
import { createSupabaseServerClient, createSupabaseServiceClient } from "@/lib/supabase/server";

const ALLOWED_TYPES = ["image/jpeg", "image/png", "image/webp", "application/pdf"] as const;
const MAX_BYTES = 10 * 1024 * 1024;

export async function POST(request: NextRequest) {
  const supabase = await createSupabaseServerClient();
  const {
    data: { user },
    error: authError
  } = await supabase.auth.getUser();

  if (authError || !user) {
    return NextResponse.json({ error: "unauthorized" }, { status: 401 });
  }

  const formData = await request.formData();
  const file = formData.get("file");
  const childId = formData.get("childId");

  if (!(file instanceof File)) {
    return NextResponse.json({ error: "file이 필요합니다." }, { status: 400 });
  }
  if (typeof childId !== "string") {
    return NextResponse.json({ error: "childId가 필요합니다." }, { status: 400 });
  }
  if (!ALLOWED_TYPES.includes(file.type as (typeof ALLOWED_TYPES)[number])) {
    return NextResponse.json({ error: "지원하지 않는 파일 형식입니다." }, { status: 400 });
  }
  if (file.size > MAX_BYTES) {
    return NextResponse.json({ error: "파일 크기는 10MB 이하여야 합니다." }, { status: 400 });
  }

  const { data: child } = await supabase
    .from("children")
    .select("id")
    .eq("id", childId)
    .eq("user_id", user.id)
    .single();

  if (!child) {
    return NextResponse.json({ error: "접근 권한이 없습니다." }, { status: 403 });
  }

  const serviceClient = createSupabaseServiceClient();
  const { data: notice, error: noticeError } = await serviceClient
    .from("notices")
    .insert({
      child_id: child.id,
      source: "upload",
      status: "pending",
      created_by: user.id
    })
    .select("id")
    .single();

  if (noticeError || !notice) {
    return NextResponse.json({ error: "공지 생성 실패" }, { status: 500 });
  }

  const extension = file.type === "application/pdf" ? "pdf" : file.type.split("/")[1];
  const storagePath = `${user.id}/${notice.id}.${extension}`;
  const bytes = await file.arrayBuffer();

  const { error: uploadError } = await serviceClient.storage
    .from("notice-originals")
    .upload(storagePath, bytes, {
      contentType: file.type,
      upsert: false
    });

  if (uploadError) {
    await serviceClient
      .from("notices")
      .update({ status: "error", error_message: uploadError.message })
      .eq("id", notice.id);
    return NextResponse.json({ error: "Storage 업로드 실패" }, { status: 500 });
  }

  await serviceClient
    .from("notices")
    .update({ storage_path: storagePath })
    .eq("id", notice.id);

  return NextResponse.json({
    noticeId: notice.id,
    status: "pending"
  });
}
