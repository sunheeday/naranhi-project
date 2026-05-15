"use client";

import { createBrowserClient } from "@supabase/ssr";
import { getSupabaseBrowserConfig } from "./config";
import type { Database } from "@/types/database";

export function createSupabaseBrowserClient() {
  const { url, anonKey } = getSupabaseBrowserConfig();

  return createBrowserClient<Database>(url, anonKey);
}
