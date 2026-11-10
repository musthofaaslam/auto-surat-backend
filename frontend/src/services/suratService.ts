import api from './api';
import type {
  SuratType,
  SuratRequestListItem,
  SuratRequestDetail,
  ChatThreadInitResponse,
  ChatSessionMessageResponse,
  ChatSessionDetailResponse,
  VerificationData,
} from '../types';

// Architectural Note:
// Centralized API facade for surat operations, separating network protocols
// and payload formatting from UI presentation layers.

export interface CreateSuratRequestParams {
  kode_surat: string;
  user_prompt_context: string;
  payload_data?: Record<string, any>;
  chosen_destination?: 'email' | 'telegram' | '';
  target_destination_address?: string;
  attachments?: File[];
}

export interface ApprovalActionParams {
  action: 'APPROVE' | 'REJECT';
  catatan?: string;
  final_approved_content?: string;
  final_status?: 'SENT' | 'PRINTED';
  alasan_penolakan?: string;
}

export const suratService = {
  async getSuratTypes(): Promise<SuratType[]> {
    const response = await api.get<SuratType[]>('/surat/types/');
    return response.data;
  },

  async createSuratRequest(params: CreateSuratRequestParams): Promise<any> {
    if (params.attachments && params.attachments.length > 0) {
      const formData = new FormData();
      formData.append('kode_surat', params.kode_surat);
      formData.append('user_prompt_context', params.user_prompt_context);
      if (params.payload_data) {
        formData.append('payload_data', JSON.stringify(params.payload_data));
      }
      if (params.chosen_destination) {
        formData.append('chosen_destination', params.chosen_destination);
      }
      if (params.target_destination_address) {
        formData.append('target_destination_address', params.target_destination_address);
      }
      params.attachments.forEach((file) => {
        formData.append('attachments', file);
      });

      const response = await api.post('/surat/request/', formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
      });
      return response.data;
    }

    const payload: Record<string, any> = {
      kode_surat: params.kode_surat,
      user_prompt_context: params.user_prompt_context,
      payload_data: params.payload_data || {},
    };
    if (params.chosen_destination) {
      payload.chosen_destination = params.chosen_destination;
    }
    if (params.target_destination_address) {
      payload.target_destination_address = params.target_destination_address;
    }

    const response = await api.post('/surat/request/', payload);
    return response.data;
  },

  async getSuratRequests(): Promise<SuratRequestListItem[]> {
    const response = await api.get<SuratRequestListItem[]>('/surat/requests/');
    return response.data;
  },

  async getSuratRequestDetail(id: number): Promise<SuratRequestDetail> {
    const response = await api.get<SuratRequestDetail>(`/surat/requests/${id}/`);
    return response.data;
  },

  async redraftSuratRequest(
    id: number,
    data: { additional_prompt_context: string; payload_data?: Record<string, any> }
  ): Promise<any> {
    const response = await api.post(`/surat/requests/${id}/re-draft/`, data);
    return response.data;
  },

  async submitApprovalAction(
    approvalId: number,
    params: ApprovalActionParams
  ): Promise<any> {
    const response = await api.post(`/surat/approval/${approvalId}/action/`, params);
    return response.data;
  },

  async verifySurat(token: string): Promise<VerificationData> {
    const response = await api.get<VerificationData>(`/surat/verify/${token}/`);
    return response.data;
  },

  async initChat(title?: string, documentType?: string | null): Promise<ChatThreadInitResponse> {
    const response = await api.post<ChatThreadInitResponse>('/surat/chat/init/', {
      title: title || 'Permohonan Surat Baru',
      document_type: documentType || null,
    });
    return response.data;
  },

  async getChatSession(threadId: string): Promise<ChatSessionDetailResponse> {
    const response = await api.get<ChatSessionDetailResponse>(`/surat/chat/${threadId}/`);
    return response.data;
  },

  async sendChatMessage(
    threadId: string,
    message: string,
    attachments?: File[]
  ): Promise<ChatSessionMessageResponse> {
    if (attachments && attachments.length > 0) {
      const formData = new FormData();
      formData.append('message', message);
      attachments.forEach((file) => formData.append('attachments', file));
      const response = await api.post<ChatSessionMessageResponse>(
        `/surat/chat/${threadId}/`,
        formData,
        { headers: { 'Content-Type': 'multipart/form-data' } }
      );
      return response.data;
    }
    const response = await api.post<ChatSessionMessageResponse>(
      `/surat/chat/${threadId}/`,
      { message }
    );
    return response.data;
  },
};

export default suratService;
