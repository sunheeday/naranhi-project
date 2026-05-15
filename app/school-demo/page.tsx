import Link from "next/link";
import { redirect } from "next/navigation";
import { createSupabaseServerClient } from "@/lib/supabase/server";
import UploadForm from "./UploadForm";

export default async function SchoolDemoPage() {
  const supabase = await createSupabaseServerClient();
  const {
    data: { user }
  } = await supabase.auth.getUser();

  if (!user) redirect("/login");

  const { data: child } = await supabase
    .from("children")
    .select("id, name, school_name")
    .eq("user_id", user.id)
    .order("created_at", { ascending: false })
    .limit(1)
    .maybeSingle();

  if (!child) redirect("/onboarding");

  return (
    <main className="flex flex-col min-h-screen">
      <header className="sticky top-0 bg-surface border-b border-border px-4 py-3 flex items-center gap-3 z-10">
        <Link href="/" className="text-text-secondary text-sm" aria-label="나가기">
          <span aria-hidden="true">←</span> 나가기
        </Link>
        <span className="text-xs text-text-secondary">학교 관리자 데모</span>
      </header>

      <div className="flex flex-col gap-6 px-6 pt-8 pb-12">
        <div>
          <h1 className="text-lg font-bold text-text-primary">가정통신문 업로드</h1>
          <p className="text-sm text-text-secondary mt-1">
            {child.name} · {child.school_name}
          </p>
        </div>

        <UploadForm childId={child.id} />
      </div>
    </main>
  );
}
