export type BillingStatus = 'trialing' | 'active' | 'past_due' | 'canceled' | 'inactive';
export type JobStatus = 'queued' | 'processing' | 'completed' | 'failed';
export type BillingEventStatus = 'received' | 'processed' | 'ignored' | 'failed';
export type UserRole = 'admin' | 'client';
export type JobType = 'font_fix' | 'compress';

export interface WorkspaceInfoResponse {
  id: string;
  name: string;
  plan_name: string;
  monthly_job_limit: number;
  billing_status: BillingStatus;
  api_key_prefix: string;
  current_period_start: string;
  current_period_jobs: number;
  remaining_jobs: number;
  created_at: string;
}

export interface ClientLoginRequest {
  email: string;
  access_code: string;
}

export interface ClientLoginResponse {
  token: string;
  token_type: string;
  expires_at: string;
  workspace: WorkspaceInfoResponse;
}

export interface AdminLoginRequest {
  email: string;
  admin_code: string;
}

export interface AdminLoginResponse {
  token: string;
  token_type: string;
  expires_at: string;
  admin_email: string;
}

export interface AuthSecurityBackendStatusResponse {
  configured_backend: string;
  active_backend: string;
  details: Record<string, string | number | boolean | null>;
}

export interface UserResponse {
  id: string;
  email: string;
  role: UserRole;
  workspace_id: string | null;
  is_active: boolean;
  created_at: string;
}

export interface UserLoginRequest {
  email: string;
  password: string;
}

export interface UserLoginResponse {
  token: string;
  token_type: string;
  expires_at: string;
  user: UserResponse;
}

export interface PasswordResetRequestPayload {
  email: string;
}

export interface PasswordResetRequestResponse {
  status: string;
  message: string;
  reset_token: string | null;
  expires_at: string | null;
}

export interface PasswordResetConfirmRequest {
  token: string;
  new_password: string;
}

export interface PasswordResetConfirmResponse {
  status: string;
  message: string;
}

export interface UserCreateRequest {
  email: string;
  password: string;
  role: UserRole;
  workspace_id: string | null;
  is_active: boolean;
}

export interface UserUpdateRequest {
  role: UserRole;
  workspace_id: string | null;
  is_active: boolean;
}

export interface UserPasswordResetRequest {
  new_password: string;
}

export interface WorkspaceCreateRequest {
  name: string;
  plan_name: string;
  monthly_job_limit: number | null;
}

export interface WorkspaceCreateResponse {
  id: string;
  name: string;
  plan_name: string;
  monthly_job_limit: number;
  api_key: string;
  api_key_prefix: string;
  created_at: string;
}

export interface WorkspacePlanUpdateRequest {
  plan_name: string;
  monthly_job_limit: number | null;
  billing_status: BillingStatus;
}

export interface JobResponse {
  id: string;
  workspace_id: string;
  status: JobStatus;
  job_type: JobType;
  original_filename: string;
  input_size_bytes: number | null;
  output_size_bytes: number | null;
  size_reduction_percent: number | null;
  attempt_count: number;
  max_attempts: number;
  next_retry_at: string | null;
  created_at: string;
  updated_at: string;
  output_ready: boolean;
  error_message: string | null;
  download_url: string | null;
}

export interface JobListResponse {
  items: JobResponse[];
}

export interface AuditLogResponse {
  id: number;
  workspace_id: string | null;
  actor_type: string;
  actor_id: string;
  action: string;
  resource_type: string;
  resource_id: string | null;
  details: Record<string, unknown>;
  created_at: string;
}

export interface AuditLogListResponse {
  items: AuditLogResponse[];
}

export interface BillingEventResponse {
  id: string;
  provider: string;
  provider_event_id: string;
  event_type: string;
  workspace_id: string | null;
  status: BillingEventStatus;
  error_message: string | null;
  payload: Record<string, unknown>;
  processed_at: string | null;
  created_at: string;
}

export interface BillingEventListResponse {
  items: BillingEventResponse[];
}
