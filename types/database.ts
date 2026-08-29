// 테이블·컬럼 정의의 정본은 types/database.generated.ts 이며, 그 파일은
// `npm run gen:types` 로만 갱신한다 — 손으로 고치지 않는다.
//
// 아래 5개 유니언은 이 파일에 남긴다. NoticeStatus/CardType은 실측 결과
// notices.status/notice_cards.type이 실제 Postgres enum(notice_status,
// notice_card_type)이라 gen types도 동일한 리터럴 유니언을 내지만, DTO 경계에서
// 쓰는 이름을 이 파일 하나로 모아두기 위해 재선언한다. SupportedLocale·
// SchoolCrawlBoardKind·NoticeAiValidationStatus는 DB가 text + CHECK라 gen
// types가 string을 내므로 여기서 값 도메인을 좁혀 제공한다.
// 전 저장소가 '@/types/database'를 import하므로 경로는 그대로 둔다.
import type { Database as GeneratedDatabase } from './database.generated'

export type { Json } from './database.generated'
import type { Json } from './database.generated'

// admin_users/admin_sessions/admin_audit_log 테이블과 admin_verify_password/
// admin_set_password 함수(0038_admin_console_auth.sql)는 운영 DB에 아직
// 적용되지 않아 `npm run gen:types`가 이 스키마를 못 본다(linked 대상이 운영이고,
// 로컬 인프라 기동·운영 마이그레이션 적용은 이 작업 범위 밖). 0038이 운영에
// 적용되고 gen:types를 다시 돌리면 database.generated.ts가 이 셋을 직접 내므로
// 이 보강 블록은 지우고 위 import에서 그대로 재수출하면 된다.
//
// 필드 타입은 0038_admin_console_auth.sql의 실제 컬럼 정의에서 그대로 옮겼다.
// Relationships는 Postgres 기본 FK 이름 규칙(<table>_<column>_fkey)을 따른다.
type GeneratedPublicSchema = GeneratedDatabase['public']

export type Database = Omit<GeneratedDatabase, 'public'> & {
  public: Omit<GeneratedPublicSchema, 'Tables' | 'Functions'> & {
    Tables: GeneratedPublicSchema['Tables'] & {
      admin_users: {
        Row: {
          id: string
          username: string
          password_hash: string
          display_name: string | null
          is_active: boolean
          totp_secret: string | null
          failed_attempts: number
          locked_until: string | null
          last_login_at: string | null
          created_at: string
          updated_at: string
        }
        Insert: {
          id?: string
          username: string
          password_hash: string
          display_name?: string | null
          is_active?: boolean
          totp_secret?: string | null
          failed_attempts?: number
          locked_until?: string | null
          last_login_at?: string | null
          created_at?: string
          updated_at?: string
        }
        Update: {
          id?: string
          username?: string
          password_hash?: string
          display_name?: string | null
          is_active?: boolean
          totp_secret?: string | null
          failed_attempts?: number
          locked_until?: string | null
          last_login_at?: string | null
          created_at?: string
          updated_at?: string
        }
        Relationships: []
      }
      admin_sessions: {
        Row: {
          id: string
          admin_user_id: string
          token_hash: string
          expires_at: string
          revoked_at: string | null
          created_at: string
        }
        Insert: {
          id?: string
          admin_user_id: string
          token_hash: string
          expires_at: string
          revoked_at?: string | null
          created_at?: string
        }
        Update: {
          id?: string
          admin_user_id?: string
          token_hash?: string
          expires_at?: string
          revoked_at?: string | null
          created_at?: string
        }
        Relationships: [
          {
            foreignKeyName: "admin_sessions_admin_user_id_fkey"
            columns: ["admin_user_id"]
            isOneToOne: false
            referencedRelation: "admin_users"
            referencedColumns: ["id"]
          },
        ]
      }
      admin_audit_log: {
        Row: {
          id: string
          admin_user_id: string | null
          action: string
          target: string | null
          detail: Json
          created_at: string
        }
        Insert: {
          id?: string
          admin_user_id?: string | null
          action: string
          target?: string | null
          detail?: Json
          created_at?: string
        }
        Update: {
          id?: string
          admin_user_id?: string | null
          action?: string
          target?: string | null
          detail?: Json
          created_at?: string
        }
        Relationships: [
          {
            foreignKeyName: "admin_audit_log_admin_user_id_fkey"
            columns: ["admin_user_id"]
            isOneToOne: false
            referencedRelation: "admin_users"
            referencedColumns: ["id"]
          },
        ]
      }
    }
    Functions: GeneratedPublicSchema['Functions'] & {
      // outcome은 SQL에서 text로 선언돼 실제 gen types도 string을 낸다(리터럴
      // 유니언이 아니다) — 값 도메인은 0038_admin_console_auth.sql 주석 참고.
      admin_verify_password: {
        Args: {
          p_password: string
          p_username: string
        }
        Returns: {
          admin_user_id: string | null
          display_name: string | null
          outcome: string
        }[]
      }
      admin_set_password: {
        Args: {
          p_display_name?: string | null
          p_password: string
          p_username: string
        }
        Returns: string
      }
    }
  }
}

export type SupportedLocale = 'ko' | 'en' | 'zh' | 'vi' | 'ru' | 'ar' | 'fr' | 'id' | 'th'
export type NoticeStatus = 'pending' | 'processing' | 'done' | 'error'
export type CardType = 'supplies' | 'action' | 'schedule'
export type SchoolCrawlBoardKind = 'family_notice' | 'announcement_fallback' | 'unknown'
/** 0005:14-15 의 CHECK 는 세 값이지만 코드가 쓰는 것은 둘뿐이고, 운영 155행이 전부 'passed' 다.
 *  Task 13 이 DB CHECK 를 이 둘로 좁힌다. */
export type NoticeAiValidationStatus = 'passed' | 'failed'
/** app_jobs.status는 DB에서 text라 gen types가 string을 낸다 — 실제 값 도메인만 좁혀 제공. */
export type AppJobStatus = 'queued' | 'processing' | 'completed' | 'failed'
