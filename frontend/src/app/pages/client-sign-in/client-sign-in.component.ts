import { CommonModule } from '@angular/common';
import { Component, OnInit } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { ApiService } from '../../core/api.service';
import { JobType } from '../../core/models';
import { SessionService } from '../../core/session.service';

type UiState = 'idle' | 'busy' | 'done' | 'fail';

@Component({
  selector: 'app-client-sign-in',
  standalone: true,
  imports: [CommonModule, FormsModule, RouterLink],
  templateUrl: './client-sign-in.component.html',
  styleUrl: './client-sign-in.component.css',
})
export class ClientSignInComponent implements OnInit {
  email = '';
  password = '';
  showPassword = false;

  statusMessage = 'Enter your credentials to continue.';
  statusStyle: UiState = 'idle';
  isSubmitting = false;
  requestedOperation: JobType | null = null;
  requestedOperationLabel: string | null = null;

  constructor(
    private readonly api: ApiService,
    private readonly session: SessionService,
    private readonly router: Router,
    private readonly route: ActivatedRoute
  ) {}

  ngOnInit(): void {
    this.requestedOperation = this.readRequestedOperation();
    if (this.requestedOperation) {
      this.requestedOperationLabel = this.jobTypeLabel(this.requestedOperation);
      this.setStatus(`Sign in to try ${this.requestedOperationLabel}.`, 'idle');
    }
  }

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
          if (response.user.role !== 'client') {
            this.setStatus('This account is not a client account.', 'fail');
            return;
          }
          this.session.clearAdminSession();
          this.session.setClientSession({
            email,
            token: response.token,
            expiresAt: response.expires_at,
          });
          this.setStatus('Signed in successfully.', 'done');
          this.router.navigate(['/portal'], {
            queryParams: this.requestedOperation ? { operation: this.requestedOperation } : undefined,
          });
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

  private readRequestedOperation(): JobType | null {
    const raw = this.route.snapshot.queryParamMap.get('operation');
    if (raw === 'font_fix' || raw === 'compress' || raw === 'merge' || raw === 'split') {
      return raw;
    }
    return null;
  }

  private jobTypeLabel(type: JobType): string {
    if (type === 'font_fix') {
      return 'Fix Form Fields';
    }
    if (type === 'compress') {
      return 'Compress PDF';
    }
    if (type === 'merge') {
      return 'Merge PDFs';
    }
    return 'Split PDF';
  }

  private isValidEmail(value: string): boolean {
    if (!value) {
      return false;
    }
    return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value);
  }
}
