import { CommonModule } from '@angular/common';
import { Component } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { Router, RouterLink } from '@angular/router';
import { ApiService } from '../../core/api.service';
import { SessionService } from '../../core/session.service';

type UiState = 'idle' | 'busy' | 'done' | 'fail';

@Component({
  selector: 'app-admin-sign-in',
  standalone: true,
  imports: [CommonModule, FormsModule, RouterLink],
  templateUrl: './admin-sign-in.component.html',
  styleUrl: './admin-sign-in.component.css',
})
export class AdminSignInComponent {
  email = '';
  password = '';
  showPassword = false;

  statusMessage = 'Internal sign in required.';
  statusStyle: UiState = 'idle';
  isSubmitting = false;

  constructor(
    private readonly api: ApiService,
    private readonly session: SessionService,
    private readonly router: Router
  ) {}

  signIn(): void {
    const email = this.email.trim().toLowerCase();
    const password = this.password;

    if (!this.isValidEmail(email)) {
      this.setStatus('Enter a valid email address.', 'fail');
      return;
    }
    if (!password.trim()) {
      this.setStatus('Password is required.', 'fail');
      return;
    }

    this.isSubmitting = true;
    this.setStatus('Checking credentials...', 'busy');

    this.api
      .loginUser({
        email,
        password,
      })
      .subscribe({
        next: (response) => {
          if (response.user.role !== 'admin') {
            this.setStatus('This account is not an admin account.', 'fail');
            return;
          }
          this.session.clearClientSession();
          this.session.setAdminSession({
            email,
            token: response.token,
            expiresAt: response.expires_at,
          });
          this.setStatus('Admin access confirmed.', 'done');
          this.router.navigateByUrl('/admin/workspaces');
        },
        error: (error: unknown) => {
          this.setStatus(this.api.extractErrorMessage(error), 'fail');
        },
        complete: () => {
          this.isSubmitting = false;
        },
      });
  }

  toggleShowPassword(): void {
    this.showPassword = !this.showPassword;
  }

  private setStatus(message: string, style: UiState): void {
    this.statusMessage = message;
    this.statusStyle = style;
  }

  private isValidEmail(value: string): boolean {
    if (!value) {
      return false;
    }
    return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value);
  }
}
