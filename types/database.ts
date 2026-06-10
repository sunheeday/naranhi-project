export type Json = string | number | boolean | null | { [key: string]: Json } | Json[]

export type SupportedLocale = 'ko' | 'en' | 'zh' | 'vi' | 'ru' | 'ar' | 'fr' | 'id' | 'th'
export type NoticeStatus = 'pending' | 'processing' | 'done' | 'error'
export type CardType = 'supplies' | 'action' | 'schedule'
export type SchoolCrawlBoardKind = 'family_notice' | 'announcement_fallback' | 'unknown'
export type NoticeAiValidationStatus = 'passed' | 'failed'

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
          created_at?: string
          updated_at?: string
        }
        Update: {
          email?: string | null
          display_name?: string | null
          avatar_url?: string | null
          locale?: SupportedLocale
          native_language?: SupportedLocale
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
      school_crawl_state: {
        Row: {
          school_id: string
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
          school_id: string
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
          grade: number
          class_no: number | null
          created_at: string
        }
        Insert: {
          id?: string
          user_id: string
          school_id?: string | null
          name: string
          grade: number
          class_no?: number | null
          created_at?: string
        }
        Update: {
          school_id?: string | null
          name?: string
          grade?: number
          class_no?: number | null
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
          /** 제출/행동 마감일 (YYYY-MM-DD). LLM이 추출한 가장 이른 deadline. 없으면 null */
          due_date: string | null
          /** 공지에서 추출된 행사/마감 관련 날짜 목록(YYYY-MM-DD 배열) */
          event_dates: Json
          /** 공지에서 추출된 대표 장소 */
          event_location: string | null
          /** 한국어 기준 canonical hard facts */
          source_hard_facts: Json
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
          due_date?: string | null
          event_dates?: Json
          event_location?: string | null
          source_hard_facts?: Json
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
          due_date?: string | null
          event_dates?: Json
          event_location?: string | null
          source_hard_facts?: Json
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
          translated_title: string | null
          translated_location: string | null
          translated_text: string
          validation_status: NoticeAiValidationStatus
          created_at: string
          updated_at: string
        }
        Insert: {
          id?: string
          notice_id: string
          target_language: string
          source_language?: string
          translated_title?: string | null
          translated_location?: string | null
          translated_text: string
          validation_status?: NoticeAiValidationStatus
          created_at?: string
          updated_at?: string
        }
        Update: {
          target_language?: string
          source_language?: string
          translated_title?: string | null
          translated_location?: string | null
          translated_text?: string
          validation_status?: NoticeAiValidationStatus
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
      notice_card_translations: {
        Row: {
          id: string
          notice_card_id: string
          target_language: string
          translated_content: Json
          created_at: string
          updated_at: string
        }
        Insert: {
          id?: string
          notice_card_id: string
          target_language: string
          translated_content?: Json
          created_at?: string
          updated_at?: string
        }
        Update: {
          notice_card_id?: string
          target_language?: string
          translated_content?: Json
          updated_at?: string
        }
        Relationships: []
      }
      school_events: {
        Row: {
          id: string
          school_id: string
          notice_id: string
          title: string
          event_date: string
          event_kinds: Json
          location: string | null
          description: string | null
          source_language: string
          created_at: string
          updated_at: string
        }
        Insert: {
          id?: string
          school_id: string
          notice_id: string
          title: string
          event_date: string
          event_kinds?: Json
          location?: string | null
          description?: string | null
          source_language?: string
          created_at?: string
          updated_at?: string
        }
        Update: {
          school_id?: string
          notice_id?: string
          title?: string
          event_date?: string
          event_kinds?: Json
          location?: string | null
          description?: string | null
          source_language?: string
          updated_at?: string
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
