import { HttpClient, HttpErrorResponse, HttpHeaders } from '@angular/common/http';
import { Injectable } from '@angular/core';
import { Observable } from 'rxjs';
import {
  AdminLoginRequest,
  AdminLoginResponse,
  AuthSecurityBackendStatusResponse,
  AuditLogListResponse,
  BillingEventListResponse,
  ClientLoginRequest,
  ClientLoginResponse,
  JobListResponse,
  JobResponse,
  JobType,
  PdfInspectResponse,
  PasswordResetConfirmRequest,
  PasswordResetConfirmResponse,
  PasswordResetRequestPayload,
  PasswordResetRequestResponse,
  UserCreateRequest,
  UserLoginRequest,
  UserLoginResponse,
  UserPasswordResetRequest,
  UserResponse,
  UserUpdateRequest,
  WorkspaceCreateRequest,
  WorkspaceCreateResponse,
  WorkspaceInfoResponse,
  WorkspacePlanUpdateRequest,
} from './models';

type RuntimeConfigWindow = Window & { PDF_SAAS_API_BASE?: unknown };

@Injectable({ providedIn: 'root' })
export class ApiService {
  private readonly baseUrl = this.resolveBaseUrl();

  constructor(private readonly http: HttpClient) {}

  extractErrorMessage(error: unknown): string {
    if (error instanceof HttpErrorResponse) {
      const payload = error.error;
      if (typeof payload === 'string' && payload.trim()) {
        return payload;
      }

      if (payload && typeof payload === 'object') {
        const detail = (payload as Record<string, unknown>)['detail'];
        if (typeof detail === 'string' && detail.trim()) {
          return detail;
        }
        if (Array.isArray(detail) && detail.length > 0) {
          const parts = detail.map((item) => {
            if (typeof item === 'string') {
              return item;
            }
            if (item && typeof item === 'object') {
              const msg = (item as Record<string, unknown>)['msg'];
              if (typeof msg === 'string') {
                return msg;
              }
            }
            return JSON.stringify(item);
          });
          return parts.join(', ');
        }
      }

      if (error.message) {
        return error.message;
      }
    }

    if (error instanceof Error) {
      return error.message;
    }
    return 'Request failed.';
  }

  loginClient(payload: ClientLoginRequest): Observable<ClientLoginResponse> {
    return this.http.post<ClientLoginResponse>(`${this.baseUrl}/auth/client/login`, payload);
  }

  loginAdmin(payload: AdminLoginRequest): Observable<AdminLoginResponse> {
    return this.http.post<AdminLoginResponse>(`${this.baseUrl}/auth/admin/login`, payload);
  }

  loginUser(payload: UserLoginRequest): Observable<UserLoginResponse> {
    return this.http.post<UserLoginResponse>(`${this.baseUrl}/auth/login`, payload);
  }

  requestPasswordReset(payload: PasswordResetRequestPayload): Observable<PasswordResetRequestResponse> {
    return this.http.post<PasswordResetRequestResponse>(`${this.baseUrl}/auth/password-reset/request`, payload);
  }

  confirmPasswordReset(payload: PasswordResetConfirmRequest): Observable<PasswordResetConfirmResponse> {
    return this.http.post<PasswordResetConfirmResponse>(`${this.baseUrl}/auth/password-reset/confirm`, payload);
  }

  getWorkspace(authToken: string): Observable<WorkspaceInfoResponse> {
    return this.http.get<WorkspaceInfoResponse>(`${this.baseUrl}/me/workspace`, {
      headers: this.authHeaders(authToken),
    });
  }

  listJobs(authToken: string, limit = 25): Observable<JobListResponse> {
    return this.http.get<JobListResponse>(`${this.baseUrl}/jobs?limit=${limit}`, {
      headers: this.authHeaders(authToken),
    });
  }

  getJob(authToken: string, jobId: string): Observable<JobResponse> {
    return this.http.get<JobResponse>(`${this.baseUrl}/jobs/${jobId}`, {
      headers: this.authHeaders(authToken),
    });
  }

  inspectPdf(authToken: string, file: File): Observable<PdfInspectResponse> {
    const formData = new FormData();
    formData.append('file', file, file.name);
    return this.http.post<PdfInspectResponse>(`${this.baseUrl}/pdf/inspect`, formData, {
      headers: this.authHeaders(authToken),
    });
  }

  createJob(
    authToken: string,
    files: File[],
    jobType: JobType = 'font_fix',
    jobOptions?: Record<string, unknown>
  ): Observable<JobResponse> {
    const formData = new FormData();
    if (jobType === 'merge') {
      files.forEach((file) => {
        formData.append('files', file, file.name);
      });
    } else if (files.length > 0) {
      formData.append('file', files[0], files[0].name);
    }
    formData.append('job_type', jobType);
    if (jobOptions && Object.keys(jobOptions).length > 0) {
      formData.append('job_options', JSON.stringify(jobOptions));
    }
    return this.http.post<JobResponse>(`${this.baseUrl}/jobs`, formData, {
      headers: this.authHeaders(authToken),
    });
  }

  downloadJob(authToken: string, jobId: string): Observable<Blob> {
    return this.http.get(`${this.baseUrl}/jobs/${jobId}/download`, {
      headers: this.authHeaders(authToken),
      responseType: 'blob',
    });
  }

  listWorkspaces(authToken: string): Observable<WorkspaceInfoResponse[]> {
    return this.http.get<WorkspaceInfoResponse[]>(`${this.baseUrl}/workspaces`, {
      headers: this.authHeaders(authToken),
    });
  }

  createWorkspace(authToken: string, payload: WorkspaceCreateRequest): Observable<WorkspaceCreateResponse> {
    return this.http.post<WorkspaceCreateResponse>(`${this.baseUrl}/workspaces`, payload, {
      headers: this.authHeaders(authToken),
    });
  }

  updateWorkspacePlan(
    authToken: string,
    workspaceId: string,
    payload: WorkspacePlanUpdateRequest
  ): Observable<WorkspaceInfoResponse> {
    return this.http.patch<WorkspaceInfoResponse>(`${this.baseUrl}/workspaces/${workspaceId}/plan`, payload, {
      headers: this.authHeaders(authToken),
    });
  }

  listBillingEvents(authToken: string, limit = 50): Observable<BillingEventListResponse> {
    return this.http.get<BillingEventListResponse>(`${this.baseUrl}/billing/events?limit=${limit}`, {
      headers: this.authHeaders(authToken),
    });
  }

  listAuditLogs(authToken: string, limit = 50): Observable<AuditLogListResponse> {
    return this.http.get<AuditLogListResponse>(`${this.baseUrl}/audit/logs?limit=${limit}`, {
      headers: this.authHeaders(authToken),
    });
  }

  getAuthSecurityBackendStatus(authToken: string): Observable<AuthSecurityBackendStatusResponse> {
    return this.http.get<AuthSecurityBackendStatusResponse>(`${this.baseUrl}/auth/security/backend`, {
      headers: this.authHeaders(authToken),
    });
  }

  listUsers(authToken: string): Observable<UserResponse[]> {
    return this.http.get<UserResponse[]>(`${this.baseUrl}/users`, {
      headers: this.authHeaders(authToken),
    });
  }

  createUser(authToken: string, payload: UserCreateRequest): Observable<UserResponse> {
    return this.http.post<UserResponse>(`${this.baseUrl}/users`, payload, {
      headers: this.authHeaders(authToken),
    });
  }

  updateUser(authToken: string, userId: string, payload: UserUpdateRequest): Observable<UserResponse> {
    return this.http.patch<UserResponse>(`${this.baseUrl}/users/${userId}`, payload, {
      headers: this.authHeaders(authToken),
    });
  }

  resetUserPassword(authToken: string, userId: string, payload: UserPasswordResetRequest): Observable<UserResponse> {
    return this.http.post<UserResponse>(`${this.baseUrl}/users/${userId}/reset-password`, payload, {
      headers: this.authHeaders(authToken),
    });
  }

  private authHeaders(authToken: string): HttpHeaders {
    const trimmed = authToken.trim();
    if (!trimmed) {
      return new HttpHeaders();
    }
    return new HttpHeaders({ Authorization: `Bearer ${trimmed}` });
  }

  private resolveBaseUrl(): string {
    const override = this.runtimeBaseOverride();
    if (override) {
      return override;
    }

    if (typeof window !== 'undefined') {
      const host = window.location.hostname;
      const port = window.location.port;
      const isLocal = host === 'localhost' || host === '127.0.0.1';
      const isAngularDevPort = port === '4200' || port === '4201';
      if (isLocal && isAngularDevPort) {
        return 'http://localhost:8000/api/v1';
      }
      return `${window.location.origin}/api/v1`;
    }

    return 'http://localhost:8000/api/v1';
  }

  private runtimeBaseOverride(): string | null {
    if (typeof window === 'undefined') {
      return null;
    }

    const fromWindow = (window as RuntimeConfigWindow).PDF_SAAS_API_BASE;
    if (typeof fromWindow === 'string' && fromWindow.trim()) {
      return fromWindow.trim().replace(/\/$/, '');
    }

    try {
      const fromStorage = window.localStorage.getItem('pdf_saas_api_base');
      if (fromStorage && fromStorage.trim()) {
        return fromStorage.trim().replace(/\/$/, '');
      }
    } catch {
      return null;
    }

    return null;
  }
}
