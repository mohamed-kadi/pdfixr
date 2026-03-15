import { CommonModule } from '@angular/common';
import { Component, OnInit } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { Router } from '@angular/router';
import { ApiService } from '../../core/api.service';
import { UserResponse, UserRole } from '../../core/models';
import { SessionService } from '../../core/session.service';

type UiStatus = 'idle' | 'done' | 'fail';

interface AdminUserRow extends UserResponse {
  editRole: UserRole;
  editWorkspaceId: string;
  editIsActive: boolean;
  resetPassword: string;
}

@Component({
  selector: 'app-admin-users',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './admin-users.component.html',
  styleUrl: './admin-users.component.css',
})
export class AdminUsersComponent implements OnInit {
  readonly userRoleOptions: readonly UserRole[] = ['client', 'admin'];

  statusMessage = 'User management ready.';
  statusStyle: UiStatus = 'idle';

  createUserEmail = '';
  createUserPassword = '';
  createUserRole: UserRole = 'client';
  createUserWorkspaceId = '';
  createUserIsActive = true;
  createUserMessage = 'No user created yet.';
  createUserStyle: UiStatus = 'idle';

  users: AdminUserRow[] = [];

  loading = false;
  creatingUser = false;
  savingUserId: string | null = null;
  resettingUserId: string | null = null;

  constructor(
    private readonly api: ApiService,
    private readonly session: SessionService,
    private readonly router: Router
  ) {}

  ngOnInit(): void {
    this.refreshUsers();
  }

  refreshUsers(): void {
    const authToken = this.requireAdminToken();
    if (!authToken) {
      return;
    }

    this.loading = true;
    this.api.listUsers(authToken).subscribe({
      next: (users) => {
        this.users = users.map((user) => this.toEditableUser(user));
        this.setStatus('Users refreshed.', 'done');
      },
      error: (error: unknown) => {
        this.setStatus(this.api.extractErrorMessage(error), 'fail');
      },
      complete: () => {
        this.loading = false;
      },
    });
  }

  createUser(): void {
    const authToken = this.requireAdminToken();
    if (!authToken) {
      this.setCreateUserMessage('Session expired. Sign in again.', 'fail');
      return;
    }

    const email = this.createUserEmail.trim().toLowerCase();
    const password = this.createUserPassword;
    const workspaceId = this.createUserWorkspaceId.trim();

    if (!email || !this.isValidEmail(email)) {
      this.setCreateUserMessage('Valid email is required.', 'fail');
      return;
    }
    if (password.trim().length < 8) {
      this.setCreateUserMessage('Password must be at least 8 characters.', 'fail');
      return;
    }
    if (this.createUserRole === 'client' && !workspaceId) {
      this.setCreateUserMessage('Client user requires workspace id.', 'fail');
      return;
    }

    this.creatingUser = true;
    this.api
      .createUser(authToken, {
        email,
        password,
        role: this.createUserRole,
        workspace_id: this.createUserRole === 'client' ? workspaceId : null,
        is_active: this.createUserIsActive,
      })
      .subscribe({
        next: (user) => {
          this.createUserEmail = '';
          this.createUserPassword = '';
          this.createUserWorkspaceId = '';
          this.createUserRole = 'client';
          this.createUserIsActive = true;
          this.setCreateUserMessage(`User ${user.email} created.`, 'done');
          this.refreshUsers();
        },
        error: (error: unknown) => {
          this.setCreateUserMessage(this.api.extractErrorMessage(error), 'fail');
        },
        complete: () => {
          this.creatingUser = false;
        },
      });
  }

  saveUser(user: AdminUserRow): void {
    const authToken = this.requireAdminToken();
    if (!authToken) {
      this.setStatus('Session expired. Sign in again.', 'fail');
      return;
    }

    const workspaceId = user.editWorkspaceId.trim();
    if (user.editRole === 'client' && !workspaceId) {
      this.setStatus('Client users require a workspace id.', 'fail');
      return;
    }

    this.savingUserId = user.id;
    this.api
      .updateUser(authToken, user.id, {
        role: user.editRole,
        workspace_id: user.editRole === 'client' ? workspaceId : null,
        is_active: user.editIsActive,
      })
      .subscribe({
        next: (updated) => {
          user.role = updated.role;
          user.workspace_id = updated.workspace_id;
          user.is_active = updated.is_active;
          user.editRole = updated.role;
          user.editWorkspaceId = updated.workspace_id ?? '';
          user.editIsActive = updated.is_active;
          this.setStatus(`User ${updated.email} updated.`, 'done');
        },
        error: (error: unknown) => {
          this.setStatus(this.api.extractErrorMessage(error), 'fail');
        },
        complete: () => {
          this.savingUserId = null;
        },
      });
  }

  resetUserPassword(user: AdminUserRow): void {
    const authToken = this.requireAdminToken();
    if (!authToken) {
      this.setStatus('Session expired. Sign in again.', 'fail');
      return;
    }

    const newPassword = user.resetPassword;
    if (newPassword.trim().length < 8) {
      this.setStatus('New password must be at least 8 characters.', 'fail');
      return;
    }

    this.resettingUserId = user.id;
    this.api
      .resetUserPassword(authToken, user.id, { new_password: newPassword })
      .subscribe({
        next: (updated) => {
          user.resetPassword = '';
          this.setStatus(`Password reset for ${updated.email}.`, 'done');
        },
        error: (error: unknown) => {
          this.setStatus(this.api.extractErrorMessage(error), 'fail');
        },
        complete: () => {
          this.resettingUserId = null;
        },
      });
  }

  formatDate(value: string | null): string {
    if (!value) {
      return '-';
    }
    const dt = new Date(value);
    if (Number.isNaN(dt.getTime())) {
      return value;
    }
    return dt.toLocaleString();
  }

  isSavingUser(userId: string): boolean {
    return this.savingUserId === userId;
  }

  isResettingUser(userId: string): boolean {
    return this.resettingUserId === userId;
  }

  trackByUserId(_: number, user: UserResponse): string {
    return user.id;
  }

  private toEditableUser(user: UserResponse): AdminUserRow {
    return {
      ...user,
      editRole: user.role,
      editWorkspaceId: user.workspace_id ?? '',
      editIsActive: user.is_active,
      resetPassword: '',
    };
  }

  private setStatus(message: string, style: UiStatus): void {
    this.statusMessage = message;
    this.statusStyle = style;
  }

  private setCreateUserMessage(message: string, style: UiStatus): void {
    this.createUserMessage = message;
    this.createUserStyle = style;
  }

  private requireAdminToken(): string | null {
    const token = this.session.getAdminSession()?.token.trim() ?? '';
    if (token) {
      return token;
    }

    this.setStatus('Session expired. Please sign in again.', 'fail');
    this.session.clearAdminSession();
    this.router.navigateByUrl('/admin/sign-in');
    return null;
  }

  private isValidEmail(value: string): boolean {
    return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value);
  }
}
