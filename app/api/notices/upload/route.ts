import { NextResponse } from "next/server";

export async function POST() {
  return NextResponse.json(
    { error: "upload_not_available" },
    { status: 501 }
  );
}
