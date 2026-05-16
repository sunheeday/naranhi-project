export type Json = string | number | boolean | null | { [key: string]: Json } | Json[]

export type SupportedLocale = 'ko' | 'en' | 'zh' | 'vi' | 'ru' | 'ar' | 'fr' | 'id' | 'th'
export type NoticeSource = 'upload' | 'crawl' | 'manual'
export type NoticeStatus = 'pending' | 'processing' | 'done' | 'error'
export type CardType = 'supplies' | 'action' | 'schedule'
export type SchoolCrawlBoardKind = 'family_notice' | 'announcement_fallback' | 'unknown'

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
          child_id: string
          school_id: string | null
          source: NoticeSource
          title: string | null
          original_text: string | null
          summary_translations: { [locale: string]: string }
          storage_path: string | null
          status: NoticeStatus
          error_message: string | null
          created_by: string | null
          created_at: string
          updated_at: string
        }
        Insert: {
          id?: string
          child_id: string
          school_id?: string | null
          source: NoticeSource
          title?: string | null
          original_text?: string | null
          summary_translations?: { [locale: string]: string }
          storage_path?: string | null
          status?: NoticeStatus
          error_message?: string | null
          created_by?: string | null
          created_at?: string
          updated_at?: string
        }
        Update: {
          school_id?: string | null
          title?: string | null
          original_text?: string | null
          summary_translations?: { [locale: string]: string }
          storage_path?: string | null
          status?: NoticeStatus
          error_message?: string | null
          created_by?: string | null
          updated_at?: string
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
      document_files: {
        Row: {
          id: string
          notice_id: string | null
          storage_bucket: string
          storage_path: string
          mime_type: string | null
          created_by: string | null
          created_at: string
        }
        Insert: {
          id?: string
          notice_id?: string | null
          storage_bucket?: string
          storage_path: string
          mime_type?: string | null
          created_by?: string | null
          created_at?: string
        }
        Update: {
          notice_id?: string | null
          storage_bucket?: string
          storage_path?: string
          mime_type?: string | null
          created_by?: string | null
        }
        Relationships: []
      }
    }
    Views: {
      [_ in never]: never
    }
    Functions: {
      [_ in never]: never
    }
    Enums: {
      [_ in never]: never
    }
    CompositeTypes: {
      [_ in never]: never
    }
  }
}
