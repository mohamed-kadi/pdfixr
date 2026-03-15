import { CommonModule } from '@angular/common';
import { Component } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';
import { ApiService } from '../../core/api.service';

type UiState = 'idle' | 'busy' | 'done' | 'fail';

@Component({
  selector: 'app-forgot-password',
  standalone: true,
  imports: [CommonModule, FormsModule, RouterLink],
  templateUrl: './forgot-password.component.html',
  styleUrl: './forgot-password.component.css',
})
export class ForgotPasswordComponent {
  email = '';
  statusMessage = 'Enter your account email and submit.';
  statusStyle: UiState = 'idle';
  isSubmitting = false;

  resetToken: string | null = null;
  resetExpiresAt: string | null = null;
  resetLink: string | null = null;

  constructor(private readonly api: ApiService) {}

  submit(): void {
    const email = this.email.trim().toLowerCase();
    if (!this.isValidEmail(email)) {
      this.setStatus('Enter a valid email address.', 'fail');
      return;
    }

    this.isSubmitting = true;
    this.setStatus('Submitting reset request...', 'busy');
    this.resetToken = null;
    this.resetExpiresAt = null;
    this.resetLink = null;

    this.api.requestPasswordReset({ email }).subscribe({
      next: (response) => {
        this.setStatus(response.message, 'done');
        if (response.reset_token) {
          this.resetToken = response.reset_token;
          this.resetExpiresAt = response.expires_at;
          this.resetLink = this.buildResetLink(response.reset_token);
        }
      },
      error: (error: unknown) => {
        this.setStatus(this.api.extractErrorMessage(error), 'fail');
      },
      complete: () => {
        this.isSubmitting = false;
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

  private setStatus(message: string, style: UiState): void {
    this.statusMessage = message;
    this.statusStyle = style;
  }

  private buildResetLink(token: string): string {
    if (typeof window === 'undefined') {
      return `/reset-password?token=${encodeURIComponent(token)}`;
    }
    return `${window.location.origin}/reset-password?token=${encodeURIComponent(token)}`;
  }

  private isValidEmail(value: string): boolean {
    return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value);
  }
}
