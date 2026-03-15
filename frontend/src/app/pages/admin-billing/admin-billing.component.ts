import { CommonModule } from '@angular/common';
import { Component, OnInit } from '@angular/core';
import { Router } from '@angular/router';
import { ApiService } from '../../core/api.service';
import { BillingEventResponse } from '../../core/models';
import { SessionService } from '../../core/session.service';

type UiStatus = 'idle' | 'done' | 'fail';

@Component({
  selector: 'app-admin-billing',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './admin-billing.component.html',
  styleUrl: './admin-billing.component.css',
})
export class AdminBillingComponent implements OnInit {
  statusMessage = 'Billing view ready.';
  statusStyle: UiStatus = 'idle';

  billingEvents: BillingEventResponse[] = [];
  loading = false;

  constructor(
    private readonly api: ApiService,
    private readonly session: SessionService,
    private readonly router: Router
  ) {}

  ngOnInit(): void {
    this.refreshBillingEvents();
  }

  refreshBillingEvents(): void {
    const authToken = this.requireAdminToken();
    if (!authToken) {
      return;
    }

    this.loading = true;
    this.api.listBillingEvents(authToken, 50).subscribe({
      next: (payload) => {
        this.billingEvents = payload.items;
        this.setStatus('Billing events refreshed.', 'done');
      },
      error: (error: unknown) => {
        this.setStatus(this.api.extractErrorMessage(error), 'fail');
      },
      complete: () => {
        this.loading = false;
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

  trackByBillingEventId(_: number, event: BillingEventResponse): string {
    return event.id;
  }

  private setStatus(message: string, style: UiStatus): void {
    this.statusMessage = message;
    this.statusStyle = style;
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
}
