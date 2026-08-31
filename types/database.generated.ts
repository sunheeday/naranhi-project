export type Json =
  | string
  | number
  | boolean
  | null
  | { [key: string]: Json | undefined }
  | Json[]

export type Database = {
  // Allows to automatically instantiate createClient with right options
  // instead of createClient<Database, { PostgrestVersion: 'XX' }>(URL, KEY)
  __InternalSupabase: {
    PostgrestVersion: "14.5"
  }
  public: {
    Tables: {
      app_jobs: {
        Row: {
          attempts: number
          available_at: string
          created_at: string
          finished_at: string | null
          id: string
          job_key: string
          job_type: string
          last_error: string | null
          max_attempts: number
          payload: Json
          result: Json | null
          started_at: string | null
          status: string
          updated_at: string
        }
        Insert: {
          attempts?: number
          available_at?: string
          created_at?: string
          finished_at?: string | null
          id?: string
          job_key: string
          job_type: string
          last_error?: string | null
          max_attempts?: number
          payload?: Json
          result?: Json | null
          started_at?: string | null
          status?: string
          updated_at?: string
        }
        Update: {
          attempts?: number
          available_at?: string
          created_at?: string
          finished_at?: string | null
          id?: string
          job_key?: string
          job_type?: string
          last_error?: string | null
          max_attempts?: number
          payload?: Json
          result?: Json | null
          started_at?: string | null
          status?: string
          updated_at?: string
        }
        Relationships: []
      }
      children: {
        Row: {
          class_no: number | null
          created_at: string
          dietary_restrictions: string[]
          grade: number
          id: string
          name: string
          school_id: string | null
          user_id: string
        }
        Insert: {
          class_no?: number | null
          created_at?: string
          dietary_restrictions?: string[]
          grade: number
          id?: string
          name: string
          school_id?: string | null
          user_id: string
        }
        Update: {
          class_no?: number | null
          created_at?: string
          dietary_restrictions?: string[]
          grade?: number
          id?: string
          name?: string
          school_id?: string | null
          user_id?: string
        }
        Relationships: [
          {
            foreignKeyName: "children_school_id_fkey"
            columns: ["school_id"]
            isOneToOne: false
            referencedRelation: "schools"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "children_user_id_fkey"
            columns: ["user_id"]
            isOneToOne: false
            referencedRelation: "profiles"
            referencedColumns: ["id"]
          },
        ]
      }
      meals: {
        Row: {
          calories: string | null
          dishes: Json
          fetched_at: string
          id: string
          meal_date: string
          meal_type: number
          meal_type_name: string
          nutrients: Json | null
          office_code: string
          origins: Json | null
          school_code: string
        }
        Insert: {
          calories?: string | null
          dishes?: Json
          fetched_at?: string
          id?: string
          meal_date: string
          meal_type: number
          meal_type_name: string
          nutrients?: Json | null
          office_code: string
          origins?: Json | null
          school_code: string
        }
        Update: {
          calories?: string | null
          dishes?: Json
          fetched_at?: string
          id?: string
          meal_date?: string
          meal_type?: number
          meal_type_name?: string
          nutrients?: Json | null
          office_code?: string
          origins?: Json | null
          school_code?: string
        }
        Relationships: []
      }
      notice_ai_translations: {
        Row: {
          created_at: string
          id: string
          notice_id: string
          source_language: string
          target_language: string
          translated_location: string | null
          translated_text: string
          translated_title: string | null
          updated_at: string
          validation_status: string
        }
        Insert: {
          created_at?: string
          id?: string
          notice_id: string
          source_language?: string
          target_language: string
          translated_location?: string | null
          translated_text: string
          translated_title?: string | null
          updated_at?: string
          validation_status?: string
        }
        Update: {
          created_at?: string
          id?: string
          notice_id?: string
          source_language?: string
          target_language?: string
          translated_location?: string | null
          translated_text?: string
          translated_title?: string | null
          updated_at?: string
          validation_status?: string
        }
        Relationships: [
          {
            foreignKeyName: "notice_ai_translations_notice_id_fkey"
            columns: ["notice_id"]
            isOneToOne: false
            referencedRelation: "notices"
            referencedColumns: ["id"]
          },
        ]
      }
      notice_card_translations: {
        Row: {
          created_at: string
          id: string
          notice_card_id: string
          target_language: string
          translated_content: Json
          updated_at: string
        }
        Insert: {
          created_at?: string
          id?: string
          notice_card_id: string
          target_language: string
          translated_content?: Json
          updated_at?: string
        }
        Update: {
          created_at?: string
          id?: string
          notice_card_id?: string
          target_language?: string
          translated_content?: Json
          updated_at?: string
        }
        Relationships: [
          {
            foreignKeyName: "notice_card_translations_notice_card_id_fkey"
            columns: ["notice_card_id"]
            isOneToOne: false
            referencedRelation: "notice_cards"
            referencedColumns: ["id"]
          },
        ]
      }
      notice_cards: {
        Row: {
          content: Json
          created_at: string
          id: string
          notice_id: string
          order: number
          type: Database["public"]["Enums"]["notice_card_type"]
        }
        Insert: {
          content?: Json
          created_at?: string
          id?: string
          notice_id: string
          order?: number
          type: Database["public"]["Enums"]["notice_card_type"]
        }
        Update: {
          content?: Json
          created_at?: string
          id?: string
          notice_id?: string
          order?: number
          type?: Database["public"]["Enums"]["notice_card_type"]
        }
        Relationships: [
          {
            foreignKeyName: "notice_cards_notice_id_fkey"
            columns: ["notice_id"]
            isOneToOne: false
            referencedRelation: "notices"
            referencedColumns: ["id"]
          },
        ]
      }
      notice_hides: {
        Row: {
          hidden_at: string
          notice_id: string
          user_id: string
        }
        Insert: {
          hidden_at?: string
          notice_id: string
          user_id: string
        }
        Update: {
          hidden_at?: string
          notice_id?: string
          user_id?: string
        }
        Relationships: [
          {
            foreignKeyName: "notice_hides_notice_id_fkey"
            columns: ["notice_id"]
            isOneToOne: false
            referencedRelation: "notices"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "notice_hides_user_id_fkey"
            columns: ["user_id"]
            isOneToOne: false
            referencedRelation: "profiles"
            referencedColumns: ["id"]
          },
        ]
      }
      notices: {
        Row: {
          crawl_result: Json
          created_at: string
          detail_url: string | null
          due_date: string | null
          error_message: string | null
          event_dates: Json
          event_location: string | null
          extracted_content: Json | null
          extraction_attempts: number
          extraction_error_code: string | null
          extraction_next_run_at: string | null
          extraction_started_at: string | null
          id: string
          original_text: string | null
          school_id: string
          source_hard_facts: Json
          source_post_uid: string | null
          status: Database["public"]["Enums"]["notice_status"]
          title: string | null
          updated_at: string
        }
        Insert: {
          crawl_result?: Json
          created_at?: string
          detail_url?: string | null
          due_date?: string | null
          error_message?: string | null
          event_dates?: Json
          event_location?: string | null
          extracted_content?: Json | null
          extraction_attempts?: number
          extraction_error_code?: string | null
          extraction_next_run_at?: string | null
          extraction_started_at?: string | null
          id?: string
          original_text?: string | null
          school_id: string
          source_hard_facts?: Json
          source_post_uid?: string | null
          status?: Database["public"]["Enums"]["notice_status"]
          title?: string | null
          updated_at?: string
        }
        Update: {
          crawl_result?: Json
          created_at?: string
          detail_url?: string | null
          due_date?: string | null
          error_message?: string | null
          event_dates?: Json
          event_location?: string | null
          extracted_content?: Json | null
          extraction_attempts?: number
          extraction_error_code?: string | null
          extraction_next_run_at?: string | null
          extraction_started_at?: string | null
          id?: string
          original_text?: string | null
          school_id?: string
          source_hard_facts?: Json
          source_post_uid?: string | null
          status?: Database["public"]["Enums"]["notice_status"]
          title?: string | null
          updated_at?: string
        }
        Relationships: [
          {
            foreignKeyName: "notices_school_id_fkey"
            columns: ["school_id"]
            isOneToOne: false
            referencedRelation: "schools"
            referencedColumns: ["id"]
          },
        ]
      }
      profiles: {
        Row: {
          avatar_url: string | null
          created_at: string
          display_name: string | null
          email: string | null
          id: string
          locale: string
          native_language: string
          updated_at: string
        }
        Insert: {
          avatar_url?: string | null
          created_at?: string
          display_name?: string | null
          email?: string | null
          id: string
          locale?: string
          native_language?: string
          updated_at?: string
        }
        Update: {
          avatar_url?: string | null
          created_at?: string
          display_name?: string | null
          email?: string | null
          id?: string
          locale?: string
          native_language?: string
          updated_at?: string
        }
        Relationships: []
      }
      school_crawl_state: {
        Row: {
          board_watermarks: Json
          crawl_board_kind: string
          crawl_board_url: string | null
          crawl_error_message: string | null
          crawl_last_checked_at: string | null
          crawl_result: Json
          crawl_status: string
          created_at: string
          school_id: string
          updated_at: string
        }
        Insert: {
          board_watermarks?: Json
          crawl_board_kind?: string
          crawl_board_url?: string | null
          crawl_error_message?: string | null
          crawl_last_checked_at?: string | null
          crawl_result?: Json
          crawl_status?: string
          created_at?: string
          school_id: string
          updated_at?: string
        }
        Update: {
          board_watermarks?: Json
          crawl_board_kind?: string
          crawl_board_url?: string | null
          crawl_error_message?: string | null
          crawl_last_checked_at?: string | null
          crawl_result?: Json
          crawl_status?: string
          created_at?: string
          school_id?: string
          updated_at?: string
        }
        Relationships: [
          {
            foreignKeyName: "school_crawl_state_school_id_fkey"
            columns: ["school_id"]
            isOneToOne: true
            referencedRelation: "schools"
            referencedColumns: ["id"]
          },
        ]
      }
      school_events: {
        Row: {
          created_at: string
          description: string | null
          end_date: string | null
          event_date: string
          event_kinds: Json
          id: string
          location: string | null
          notice_id: string
          school_id: string
          source_language: string
          title: string
          updated_at: string
        }
        Insert: {
          created_at?: string
          description?: string | null
          end_date?: string | null
          event_date: string
          event_kinds?: Json
          id?: string
          location?: string | null
          notice_id: string
          school_id: string
          source_language?: string
          title: string
          updated_at?: string
        }
        Update: {
          created_at?: string
          description?: string | null
          end_date?: string | null
          event_date?: string
          event_kinds?: Json
          id?: string
          location?: string | null
          notice_id?: string
          school_id?: string
          source_language?: string
          title?: string
          updated_at?: string
        }
        Relationships: [
          {
            foreignKeyName: "school_events_notice_id_fkey"
            columns: ["notice_id"]
            isOneToOne: false
            referencedRelation: "notices"
            referencedColumns: ["id"]
          },
          {
            foreignKeyName: "school_events_school_id_fkey"
            columns: ["school_id"]
            isOneToOne: false
            referencedRelation: "schools"
            referencedColumns: ["id"]
          },
        ]
      }
      schools: {
        Row: {
          address: string | null
          crawl_board_kind: string
          crawl_board_url: string | null
          crawl_error_message: string | null
          crawl_last_checked_at: string | null
          crawl_result: Json
          crawl_status: string
          created_at: string
          homepage_url: string | null
          id: string
          name: string
          neis_office_code: string | null
          neis_school_code: string | null
          updated_at: string
        }
        Insert: {
          address?: string | null
          crawl_board_kind?: string
          crawl_board_url?: string | null
          crawl_error_message?: string | null
          crawl_last_checked_at?: string | null
          crawl_result?: Json
          crawl_status?: string
          created_at?: string
          homepage_url?: string | null
          id?: string
          name: string
          neis_office_code?: string | null
          neis_school_code?: string | null
          updated_at?: string
        }
        Update: {
          address?: string | null
          crawl_board_kind?: string
          crawl_board_url?: string | null
          crawl_error_message?: string | null
          crawl_last_checked_at?: string | null
          crawl_result?: Json
          crawl_status?: string
          created_at?: string
          homepage_url?: string | null
          id?: string
          name?: string
          neis_office_code?: string | null
          neis_school_code?: string | null
          updated_at?: string
        }
        Relationships: []
      }
      subject_translations: {
        Row: {
          created_at: string
          ko_subject: string
          locale: string
          translated: string
        }
        Insert: {
          created_at?: string
          ko_subject: string
          locale: string
          translated: string
        }
        Update: {
          created_at?: string
          ko_subject?: string
          locale?: string
          translated?: string
        }
        Relationships: []
      }
    }
    Views: {
      [_ in never]: never
    }
    Functions: {
      claim_notice_extractions: {
        Args: {
          p_force?: boolean
          p_limit?: number
          p_notice_id?: string
          p_stale_minutes?: number
        }
        Returns: {
          crawl_result: Json
          created_at: string
          detail_url: string | null
          due_date: string | null
          error_message: string | null
          event_dates: Json
          event_location: string | null
          extracted_content: Json | null
          extraction_attempts: number
          extraction_error_code: string | null
          extraction_next_run_at: string | null
          extraction_started_at: string | null
          id: string
          original_text: string | null
          school_id: string
          source_hard_facts: Json
          source_post_uid: string | null
          status: Database["public"]["Enums"]["notice_status"]
          title: string | null
          updated_at: string
        }[]
        SetofOptions: {
          from: "*"
          to: "notices"
          isOneToOne: false
          isSetofReturn: true
        }
      }
    }
    Enums: {
      notice_card_type: "supplies" | "action" | "schedule"
      notice_status: "pending" | "processing" | "done" | "error"
    }
    CompositeTypes: {
      [_ in never]: never
    }
  }
}

type DatabaseWithoutInternals = Omit<Database, "__InternalSupabase">

type DefaultSchema = DatabaseWithoutInternals[Extract<keyof Database, "public">]

export type Tables<
  DefaultSchemaTableNameOrOptions extends
    | keyof (DefaultSchema["Tables"] & DefaultSchema["Views"])
    | { schema: keyof DatabaseWithoutInternals },
  TableName extends DefaultSchemaTableNameOrOptions extends {
    schema: keyof DatabaseWithoutInternals
  }
    ? keyof (DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Tables"] &
        DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Views"])
    : never = never,
> = DefaultSchemaTableNameOrOptions extends {
  schema: keyof DatabaseWithoutInternals
}
  ? (DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Tables"] &
      DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Views"])[TableName] extends {
      Row: infer R
    }
    ? R
    : never
  : DefaultSchemaTableNameOrOptions extends keyof (DefaultSchema["Tables"] &
        DefaultSchema["Views"])
    ? (DefaultSchema["Tables"] &
        DefaultSchema["Views"])[DefaultSchemaTableNameOrOptions] extends {
        Row: infer R
      }
      ? R
      : never
    : never

export type TablesInsert<
  DefaultSchemaTableNameOrOptions extends
    | keyof DefaultSchema["Tables"]
    | { schema: keyof DatabaseWithoutInternals },
  TableName extends DefaultSchemaTableNameOrOptions extends {
    schema: keyof DatabaseWithoutInternals
  }
    ? keyof DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Tables"]
    : never = never,
> = DefaultSchemaTableNameOrOptions extends {
  schema: keyof DatabaseWithoutInternals
}
  ? DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Tables"][TableName] extends {
      Insert: infer I
    }
    ? I
    : never
  : DefaultSchemaTableNameOrOptions extends keyof DefaultSchema["Tables"]
    ? DefaultSchema["Tables"][DefaultSchemaTableNameOrOptions] extends {
        Insert: infer I
      }
      ? I
      : never
    : never

export type TablesUpdate<
  DefaultSchemaTableNameOrOptions extends
    | keyof DefaultSchema["Tables"]
    | { schema: keyof DatabaseWithoutInternals },
  TableName extends DefaultSchemaTableNameOrOptions extends {
    schema: keyof DatabaseWithoutInternals
  }
    ? keyof DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Tables"]
    : never = never,
> = DefaultSchemaTableNameOrOptions extends {
  schema: keyof DatabaseWithoutInternals
}
  ? DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Tables"][TableName] extends {
      Update: infer U
    }
    ? U
    : never
  : DefaultSchemaTableNameOrOptions extends keyof DefaultSchema["Tables"]
    ? DefaultSchema["Tables"][DefaultSchemaTableNameOrOptions] extends {
        Update: infer U
      }
      ? U
      : never
    : never

export type Enums<
  DefaultSchemaEnumNameOrOptions extends
    | keyof DefaultSchema["Enums"]
    | { schema: keyof DatabaseWithoutInternals },
  EnumName extends DefaultSchemaEnumNameOrOptions extends {
    schema: keyof DatabaseWithoutInternals
  }
    ? keyof DatabaseWithoutInternals[DefaultSchemaEnumNameOrOptions["schema"]]["Enums"]
    : never = never,
> = DefaultSchemaEnumNameOrOptions extends {
  schema: keyof DatabaseWithoutInternals
}
  ? DatabaseWithoutInternals[DefaultSchemaEnumNameOrOptions["schema"]]["Enums"][EnumName]
  : DefaultSchemaEnumNameOrOptions extends keyof DefaultSchema["Enums"]
    ? DefaultSchema["Enums"][DefaultSchemaEnumNameOrOptions]
    : never

export type CompositeTypes<
  PublicCompositeTypeNameOrOptions extends
    | keyof DefaultSchema["CompositeTypes"]
    | { schema: keyof DatabaseWithoutInternals },
  CompositeTypeName extends PublicCompositeTypeNameOrOptions extends {
    schema: keyof DatabaseWithoutInternals
  }
    ? keyof DatabaseWithoutInternals[PublicCompositeTypeNameOrOptions["schema"]]["CompositeTypes"]
    : never = never,
> = PublicCompositeTypeNameOrOptions extends {
  schema: keyof DatabaseWithoutInternals
}
  ? DatabaseWithoutInternals[PublicCompositeTypeNameOrOptions["schema"]]["CompositeTypes"][CompositeTypeName]
  : PublicCompositeTypeNameOrOptions extends keyof DefaultSchema["CompositeTypes"]
    ? DefaultSchema["CompositeTypes"][PublicCompositeTypeNameOrOptions]
    : never

export const Constants = {
  public: {
    Enums: {
      notice_card_type: ["supplies", "action", "schedule"],
      notice_status: ["pending", "processing", "done", "error"],
    },
  },
} as const
