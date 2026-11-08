// Architectural Note:
// Defining strict TypeScript models matching the Django REST Framework (DRF) serializers
// ensures end-to-end type safety, eliminating runtime undefined errors and easing refactoring.

export type UserRole = 'STUDENT' | 'LECTURER' | 'STAFF' | 'ADMIN';

export type MainViewType = 'dashboard' | 'buat-surat' | 'verify';

export type SuratStatusCode =
  | 'SUBMITTED'
  | 'REVISION_REQUIRED'
  | 'PENDING_APPROVAL'
  | 'IN_REVIEW'
  | 'APPROVED'
  | 'REJECTED'
  | 'PROCESSED'
  | 'SENT'
  | 'PRINTED'
  | 'FAILED';

export interface User {
  id: number;
  nama: string;
  nip_nim: string;
  role: UserRole;
  profile?: {
    nim?: string;
    prodi?: string;
    fakultas?: string;
    user_id?: number;
  };
}

export interface AuthResponse {
  message: string;
  refresh: string;
  access: string;
  user: User;
}

export interface SuratType {
  kode_surat: string;
  nama_surat: string;
  kategori: string;
  is_auto_approval: boolean;
  template_path?: string;
}

export interface DynamicFieldDef {
  type: 'string' | 'date' | 'number';
  field: string;
  label: string;
  description: string;
}

export interface SuratAttachment {
  id: number;
  nama_dokumen: string;
  file_url: string;
  mime_type: string;
  created_at: string;
}

export interface TteSignature {
  id: number;
  signer_name: string;
  signer_nip: string | null;
  hash_document: string;
  token: string;
  created_at: string;
}

export interface SuratApproval {
  id: number;
  step_order: number;
  approver: number;
  approver_name: string | null;
  approver_nip: string | null;
  status: 'WAITING' | 'PENDING' | 'APPROVED' | 'REJECTED';
  catatan: string | null;
  created_at: string;
}

export interface SuratAuditLog {
  id: number;
  action_id: string;
  action: string;
  created_at: string;
}

export interface SuratRequestListItem {
  id: number;
  nim_mahasiswa: string;
  nama_mahasiswa: string;
  kode_surat: string;
  nama_surat: string;
  kategori: string;
  nomor_surat_resmi: string | null;
  status: SuratStatusCode;
  created_at: string;
}

export interface SuratRequestDetail {
  id: number;
  nim_mahasiswa: string;
  nama_mahasiswa: string;
  prodi_mahasiswa: string;
  fakultas_mahasiswa: string;
  kode_surat: string;
  nama_surat: string;
  nomor_surat_resmi: string | null;
  status: SuratStatusCode;
  payload_data: Record<string, any>;
  user_prompt_context: string;
  ai_original_draft: string | null;
  final_approved_content: string | null;
  self_critique_score: number | null;
  revision_notes: string[] | string | null;
  file_pdf_url: string | null;
  qr_verification_code: string | null;
  created_at: string;
  attachments: SuratAttachment[];
  approvals: SuratApproval[];
  signatures: TteSignature[];
  audit_logs: SuratAuditLog[];
  chosen_destination?: 'email' | 'telegram' | null;
  target_destination_address?: string | null;
}

export interface ChatThreadInitResponse {
  status: string;
  message: string;
  thread_id: string;
  title: string;
  document_type: string | null;
  created_at: string;
}

export interface ChatSessionMessageResponse {
  status: 'success' | 'ready_to_draft' | 'error';
  state: 'COLLECTING_SLOTS' | 'READY_TO_DRAFT' | 'CANCELLED' | 'EXPIRED';
  reply: string;
  detected_intent?: string;
  kode_surat?: string;
  is_waiting_for_switch_confirmation?: boolean;
  collected_slots?: Record<string, any>;
  required_fields?: DynamicFieldDef[];
}

export interface VerificationData {
  status: 'VALID' | 'INVALID';
  message: string;
  detail_surat?: {
    nomor_surat_resmi: string | null;
    jenis_surat: string;
    kategori: string;
    tanggal_terbit: string;
  };
  mahasiswa?: {
    nim: string;
    nama: string;
    prodi: string;
    fakultas: string;
  };
  tte_info?: {
    hash_sha256: string;
    penandatangan: string;
    tanggal_ttd: string;
  };
}

