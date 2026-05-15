export type Json =
  | string
  | number
  | boolean
  | null
  | { [key: string]: Json | undefined }
  | Json[];

export type Database = {
  public: {
    Tables: {
      profiles: {
        Row: {
          id: string;
          display_name: string | null;
          native_language: string;
          role: "parent" | "school_admin";
          created_at: string;
          updated_at: string;
        };
        Insert: {
          id: string;
          display_name?: string | null;
          native_language?: string;
          role?: "parent" | "school_admin";
          created_at?: string;
          updated_at?: string;
        };
        Update: {
          display_name?: string | null;
          native_language?: string;
          role?: "parent" | "school_admin";
          updated_at?: string;
        };
      };
      notices: {
        Row: {
          id: string;
          school_id: string | null;
          title: string;
          source_language: string;
          source_url: string | null;
          raw_text: string | null;
          analysis_status: "pending" | "processing" | "completed" | "failed";
          created_by: string | null;
          created_at: string;
          updated_at: string;
        };
        Insert: {
          id?: string;
          school_id?: string | null;
          title: string;
          source_language?: string;
          source_url?: string | null;
          raw_text?: string | null;
          analysis_status?: "pending" | "processing" | "completed" | "failed";
          created_by?: string | null;
          created_at?: string;
          updated_at?: string;
        };
        Update: {
          title?: string;
          source_language?: string;
          source_url?: string | null;
          raw_text?: string | null;
          analysis_status?: "pending" | "processing" | "completed" | "failed";
          updated_at?: string;
        };
      };
    };
    Views: Record<string, never>;
    Functions: Record<string, never>;
    Enums: Record<string, never>;
    CompositeTypes: Record<string, never>;
  };
};
