import { CommonModule } from '@angular/common';
import { Component, OnDestroy, OnInit } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { Router, RouterLink } from '@angular/router';
import { ApiService } from '../../core/api.service';
import { SessionService } from '../../core/session.service';

type UiState = 'idle' | 'busy' | 'done' | 'fail';

interface SignInFeature {
  tag: string;
  title: string;
  description: string;
}

@Component({
  selector: 'app-client-sign-in',
  standalone: true,
  imports: [CommonModule, FormsModule, RouterLink],
  templateUrl: './client-sign-in.component.html',
  styleUrl: './client-sign-in.component.css',
})
export class ClientSignInComponent implements OnInit, OnDestroy {
  email = '';
  password = '';
  showPassword = false;

  statusMessage = 'Enter your credentials to continue.';
  statusStyle: UiState = 'idle';
  isSubmitting = false;

  activeFeatureIndex = 0;
  readonly features: SignInFeature[] = [
    {
      tag: 'Form Quality',
      title: 'Consistent cross-viewer output',
      description: 'Standardize complex PDF forms for more predictable behavior across major viewers.',
    },
    {
      tag: 'Processing',
      title: 'Background job pipeline',
      description: 'Submit files once and follow real-time status updates from queue to completion.',
    },
    {
      tag: 'Delivery',
      title: 'Fast download workflow',
      description: 'Access finalized files from a clean recent-jobs history designed for repeat work.',
    },
    {
      tag: 'Usage',
      title: 'Live workspace capacity',
      description: 'Track monthly usage and remaining processing capacity directly in the portal.',
    },
    {
      tag: 'Access',
      title: 'Built-in account recovery',
      description: 'Reset access quickly with the integrated password recovery flow when needed.',
    },
  ];

  private carouselTimer: ReturnType<typeof setInterval> | null = null;

  constructor(
    private readonly api: ApiService,
    private readonly session: SessionService,
    private readonly router: Router
  ) {}

  ngOnInit(): void {
    this.startCarousel();
  }

  ngOnDestroy(): void {
    this.stopCarousel();
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
          this.router.navigateByUrl('/');
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

  previousFeature(): void {
    if (this.features.length === 0) {
      return;
    }
    this.activeFeatureIndex = (this.activeFeatureIndex - 1 + this.features.length) % this.features.length;
    this.restartCarousel();
  }

  nextFeature(): void {
    if (this.features.length === 0) {
      return;
    }
    this.activeFeatureIndex = (this.activeFeatureIndex + 1) % this.features.length;
    this.restartCarousel();
  }

  goToFeature(index: number): void {
    if (index < 0 || index >= this.features.length) {
      return;
    }
    this.activeFeatureIndex = index;
    this.restartCarousel();
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

  private startCarousel(): void {
    this.stopCarousel();
    this.carouselTimer = setInterval(() => {
      if (this.features.length === 0) {
        return;
      }
      this.activeFeatureIndex = (this.activeFeatureIndex + 1) % this.features.length;
    }, 4500);
  }

  private stopCarousel(): void {
    if (!this.carouselTimer) {
      return;
    }
    clearInterval(this.carouselTimer);
    this.carouselTimer = null;
  }

  private restartCarousel(): void {
    this.startCarousel();
  }
}
