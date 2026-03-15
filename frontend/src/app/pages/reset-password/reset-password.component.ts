import { CommonModule } from '@angular/common';
import { Component, OnInit } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { ApiService } from '../../core/api.service';

type UiState = 'idle' | 'busy' | 'done' | 'fail';

@Component({
  selector: 'app-reset-password',
  standalone: true,
  imports: [CommonModule, FormsModule, RouterLink],
  templateUrl: './reset-password.component.html',
  styleUrl: './reset-password.component.css',
})
export class ResetPasswordComponent implements OnInit {
  token = '';
  newPassword = '';
  confirmPassword = '';

  statusMessage = 'Enter your reset token and your new password.';
  statusStyle: UiState = 'idle';
  isSubmitting = false;

  constructor(
    private readonly route: ActivatedRoute,
    private readonly router: Router,
    private readonly api: ApiService
  ) {}

  ngOnInit(): void {
    const tokenFromQuery = this.route.snapshot.queryParamMap.get('token');
    if (tokenFromQuery) {
      this.token = tokenFromQuery;
    }
  }

  submit(): void {
    const token = this.token.trim();
    if (!token || token.length < 20) {
      this.setStatus('Reset token is required.', 'fail');
      return;
    }

    if (this.newPassword.trim().length < 8) {
      this.setStatus('New password must be at least 8 characters.', 'fail');
      return;
    }

    if (this.newPassword !== this.confirmPassword) {
      this.setStatus('Passwords do not match.', 'fail');
      return;
    }

    this.isSubmitting = true;
    this.setStatus('Applying new password...', 'busy');

    this.api
      .confirmPasswordReset({
        token,
        new_password: this.newPassword,
      })
      .subscribe({
        next: (response) => {
          this.setStatus(response.message, 'done');
          this.newPassword = '';
          this.confirmPassword = '';
        },
        error: (error: unknown) => {
          this.setStatus(this.api.extractErrorMessage(error), 'fail');
        },
        complete: () => {
          this.isSubmitting = false;
        },
      });
  }

  backToSignIn(): void {
    this.router.navigateByUrl('/sign-in');
  }

  private setStatus(message: string, style: UiState): void {
    this.statusMessage = message;
    this.statusStyle = style;
  }
}
