import { CommonModule } from '@angular/common';
import { Component, OnInit } from '@angular/core';
import { Router } from '@angular/router';
import { ApiService } from '../../core/api.service';
import { AuditLogResponse } from '../../core/models';
import { SessionService } from '../../core/session.service';

type UiStatus = 'idle' | 'done' | 'fail';

@Component({
  selector: 'app-admin-audit',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './admin-audit.component.html',
  styleUrl: './admin-audit.component.css',
})
export class AdminAuditComponent implements OnInit {
  statusMessage = 'Audit view ready.';
  statusStyle: UiStatus = 'idle';

  auditLogs: AuditLogResponse[] = [];
  loading = false;

  constructor(
    private readonly api: ApiService,
    private readonly session: SessionService,
    private readonly router: Router
  ) {}

  ngOnInit(): void {
    this.refreshAuditLogs();
  }

  refreshAuditLogs(): void {
    const authToken = this.requireAdminToken();
    if (!authToken) {
      return;
    }

    this.loading = true;
    this.api.listAuditLogs(authToken, 50).subscribe({
      next: (payload) => {
        this.auditLogs = payload.items;
        this.setStatus('Global audit logs refreshed.', 'done');
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

  detailsPreview(details: Record<string, unknown>): string {
    const raw = JSON.stringify(details);
    if (raw.length <= 120) {
      return raw;
    }
    return `${raw.slice(0, 120)}...`;
  }

  trackByAuditId(_: number, log: AuditLogResponse): number {
    return log.id;
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
