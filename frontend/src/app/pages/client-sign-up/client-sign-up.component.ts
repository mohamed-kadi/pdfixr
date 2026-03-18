import { CommonModule } from '@angular/common';
import { Component } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';
import { ApiService } from '../../core/api.service';

type UiState = 'idle' | 'busy' | 'done' | 'fail';

@Component({
  selector: 'app-client-sign-up',
  standalone: true,
  imports: [CommonModule, FormsModule, RouterLink],
  templateUrl: './client-sign-up.component.html',
  styleUrl: './client-sign-up.component.css',
})
export class ClientSignUpComponent {
  email = '';
  statusMessage = 'Enter your work email to request account setup.';
  statusStyle: UiState = 'idle';
  isSubmitting = false;

  constructor(private readonly api: ApiService) {}

  submit(): void {
    const email = this.email.trim().toLowerCase();
    if (!this.isValidEmail(email)) {
      this.setStatus('Enter a valid email address.', 'fail');
      return;
    }

    this.isSubmitting = true;
    this.setStatus('Submitting account setup request...', 'busy');

    // Uses existing secure reset-request channel for invited accounts.
    this.api.requestPasswordReset({ email }).subscribe({
      next: () => {
        this.setStatus(
          'If your workspace has already invited this email, check your inbox for setup instructions.',
          'done'
        );
      },
      error: (error: unknown) => {
        this.setStatus(this.api.extractErrorMessage(error), 'fail');
      },
      complete: () => {
        this.isSubmitting = false;
      },
    });
  }

  private setStatus(message: string, style: UiState): void {
    this.statusMessage = message;
    this.statusStyle = style;
  }

  private isValidEmail(value: string): boolean {
    return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value);
  }
}
