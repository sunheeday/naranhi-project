export type Json = string | number | boolean | null | { [key: string]: Json } | Json[]

export type SupportedLocale = 'ko' | 'en' | 'zh' | 'vi' | 'ru' | 'ar' | 'fr' | 'id' | 'th'
export type NoticeStatus = 'pending' | 'processing' | 'done' | 'error'
export type CardType = 'supplies' | 'action' | 'schedule'
export type SchoolCrawlBoardKind = 'family_notice' | 'announcement_fallback' | 'unknown'
export type NoticeAiValidationStatus = 'passed' | 'human_review_required' | 'failed'

export interface Database {
  public: {
    Tables: {
      profiles: {
        Row: {
          id: string
          email: string | null
          display_name: string | null
          avatar_url: string | null
          locale: SupportedLocale
          native_language: SupportedLocale
          role: 'parent' | 'school_admin'
          created_at: string
          updated_at: string
        }
        Insert: {
          id: string
          email?: string | null
          display_name?: string | null
          avatar_url?: string | null
          locale?: SupportedLocale
          native_language?: SupportedLocale
          role?: 'parent' | 'school_admin'
          created_at?: string
          updated_at?: string
        }
        Update: {
          email?: string | null
          display_name?: string | null
          avatar_url?: string | null
          locale?: SupportedLocale
          native_language?: SupportedLocale
          role?: 'parent' | 'school_admin'
          updated_at?: string
        }
        Relationships: []
      }
      schools: {
        Row: {
          id: string
          name: string
          neis_office_code: string | null
          neis_school_code: string | null
          address: string | null
          homepage_url: string | null
          crawl_board_url: string | null
          crawl_board_kind: SchoolCrawlBoardKind
          crawl_status: string
          crawl_error_message: string | null
          crawl_result: Json
          crawl_last_checked_at: string | null
          created_at: string
          updated_at: string
        }
        Insert: {
          id?: string
          name: string
          neis_office_code?: string | null
          neis_school_code?: string | null
          address?: string | null
          homepage_url?: string | null
          crawl_board_url?: string | null
          crawl_board_kind?: SchoolCrawlBoardKind
          crawl_status?: string
          crawl_error_message?: string | null
          crawl_result?: Json
          crawl_last_checked_at?: string | null
          created_at?: string
          updated_at?: string
        }
        Update: {
          name?: string
          neis_office_code?: string | null
          neis_school_code?: string | null
          address?: string | null
          homepage_url?: string | null
          crawl_board_url?: string | null
          crawl_board_kind?: SchoolCrawlBoardKind
          crawl_status?: string
          crawl_error_message?: string | null
          crawl_result?: Json
          crawl_last_checked_at?: string | null
          updated_at?: string
        }
        Relationships: []
      }
      children: {
        Row: {
          id: string
          user_id: string
          school_id: string | null
          name: string
          school_name: string
          grade: number
          class_no: number | null
          neis_office_code: string | null
          neis_school_code: string | null
          created_at: string
        }
        Insert: {
          id?: string
          user_id: string
          school_id?: string | null
          name: string
          school_name: string
          grade: number
          class_no?: number | null
          neis_office_code?: string | null
          neis_school_code?: string | null
          created_at?: string
        }
        Update: {
          school_id?: string | null
          name?: string
          school_name?: string
          grade?: number
          class_no?: number | null
          neis_office_code?: string | null
          neis_school_code?: string | null
        }
        Relationships: []
      }
      notices: {
        Row: {
          id: string
          school_id: string
          title: string | null
          original_text: string | null
          source_post_uid: string | null
          detail_url: string | null
          crawl_result: Json
          extracted_content: Json | null
          status: NoticeStatus
          error_message: string | null
          extraction_attempts: number
          extraction_started_at: string | null
          extraction_next_run_at: string | null
          extraction_error_code: string | null
          created_at: string
          updated_at: string
        }
        Insert: {
          id?: string
          school_id: string
          title?: string | null
          original_text?: string | null
          source_post_uid?: string | null
          detail_url?: string | null
          crawl_result?: Json
          extracted_content?: Json | null
          status?: NoticeStatus
          error_message?: string | null
          extraction_attempts?: number
          extraction_started_at?: string | null
          extraction_next_run_at?: string | null
          extraction_error_code?: string | null
          created_at?: string
          updated_at?: string
        }
        Update: {
          school_id?: string
          title?: string | null
          original_text?: string | null
          source_post_uid?: string | null
          detail_url?: string | null
          crawl_result?: Json
          extracted_content?: Json | null
          status?: NoticeStatus
          error_message?: string | null
          extraction_attempts?: number
          extraction_started_at?: string | null
          extraction_next_run_at?: string | null
          extraction_error_code?: string | null
          updated_at?: string
        }
        Relationships: []
      }
      notice_ai_translations: {
        Row: {
          id: string
          notice_id: string
          target_language: string
          source_language: string
          source_text: string
          translated_text: string
          source_hard_facts: Json
          target_hard_facts: Json
          ingredient_identity_map: Json
          validation: Json
          metadata: Json
          raw_pipeline: Json
          validation_status: NoticeAiValidationStatus
          requires_admin_review: boolean
          admin_review_reason: string | null
          created_at: string
          updated_at: string
        }
        Insert: {
          id?: string
          notice_id: string
          target_language: string
          source_language?: string
          source_text: string
          translated_text: string
          source_hard_facts?: Json
          target_hard_facts?: Json
          ingredient_identity_map?: Json
          validation?: Json
          metadata?: Json
          raw_pipeline?: Json
          validation_status?: NoticeAiValidationStatus
          requires_admin_review?: boolean
          admin_review_reason?: string | null
          created_at?: string
          updated_at?: string
        }
        Update: {
          target_language?: string
          source_language?: string
          source_text?: string
          translated_text?: string
          source_hard_facts?: Json
          target_hard_facts?: Json
          ingredient_identity_map?: Json
          validation?: Json
          metadata?: Json
          raw_pipeline?: Json
          validation_status?: NoticeAiValidationStatus
          requires_admin_review?: boolean
          admin_review_reason?: string | null
          updated_at?: string
        }
        Relationships: []
      }
      notice_hides: {
        Row: {
          user_id: string
          notice_id: string
          hidden_at: string
        }
        Insert: {
          user_id: string
          notice_id: string
          hidden_at?: string
        }
        Update: {
          hidden_at?: string
        }
        Relationships: []
      }
      notice_cards: {
        Row: {
          id: string
          notice_id: string
          type: CardType
          content: Json
          order: number
          created_at: string
        }
        Insert: {
          id?: string
          notice_id: string
          type: CardType
          content: Json
          order?: number
          created_at?: string
        }
        Update: {
          content?: Json
          order?: number
        }
        Relationships: []
      }
      schedules: {
        Row: {
          id: string
          notice_id: string
          child_id: string
          title: string
          event_date: string
          location: string | null
          description: string | null
          gcal_event_id: string | null
          created_at: string
        }
        Insert: {
          id?: string
          notice_id: string
          child_id: string
          title: string
          event_date: string
          location?: string | null
          description?: string | null
          gcal_event_id?: string | null
          created_at?: string
        }
        Update: {
          title?: string
          event_date?: string
          location?: string | null
          description?: string | null
          gcal_event_id?: string | null
        }
        Relationships: []
      }
      meals: {
        Row: {
          id: string
          office_code: string
          school_code: string
          meal_date: string
          meal_type: number
          meal_type_name: string
          dishes: Json
          calories: string | null
          nutrients: Json | null
          origins: Json | null
          fetched_at: string
        }
        Insert: {
          id?: string
          office_code: string
          school_code: string
          meal_date: string
          meal_type: number
          meal_type_name: string
          dishes: Json
          calories?: string | null
          nutrients?: Json | null
          origins?: Json | null
          fetched_at?: string
        }
        Update: {
          dishes?: Json
          calories?: string | null
          nutrients?: Json | null
          origins?: Json | null
          fetched_at?: string
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
          p_limit?: number
          p_stale_minutes?: number
          p_notice_id?: string | null
          p_force?: boolean
        }
        Returns: Database['public']['Tables']['notices']['Row'][]
      }
    }
    Enums: {
      [_ in never]: never
    }
    CompositeTypes: {
      [_ in never]: never
    }
  }
}
