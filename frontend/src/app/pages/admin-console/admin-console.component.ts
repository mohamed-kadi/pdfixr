import { CommonModule } from '@angular/common';
import { Component, OnDestroy, OnInit } from '@angular/core';
import { NavigationEnd, Router, RouterLink, RouterLinkActive, RouterOutlet } from '@angular/router';
import { filter, forkJoin, Subscription } from 'rxjs';
import { AuditLogListResponse, BillingEventListResponse, UserResponse, WorkspaceInfoResponse } from '../../core/models';
import { ApiService } from '../../core/api.service';
import { SessionService } from '../../core/session.service';

type UiStatus = 'idle' | 'busy' | 'done' | 'fail';

@Component({
  selector: 'app-admin-console',
  standalone: true,
  imports: [CommonModule, RouterLink, RouterLinkActive, RouterOutlet],
  templateUrl: './admin-console.component.html',
  styleUrl: './admin-console.component.css',
})
export class AdminConsoleComponent implements OnInit, OnDestroy {
  adminEmail = '';
  adminInitials = 'AD';
  currentSectionLabel = 'Workspaces';

  dashboardStatusMessage = 'Admin dashboard loaded.';
  dashboardStatusStyle: UiStatus = 'idle';
  kpiLoading = false;
  lastRefreshedAt = 'Not refreshed yet';

  kpiWorkspaceCount = 0;
  kpiCapacityUsed = 0;
  kpiCapacityLimit = 0;
  kpiUtilizationPercent = 0;
  kpiActiveClientUsers = 0;
  kpiActiveAdminUsers = 0;
  kpiBillingFailures = 0;
  kpiRecentAuditEvents = 0;
  kpiSecurityConfigured = 'unknown';
  kpiSecurityActive = 'unknown';
  kpiFallbackActivations = 0;

  private navSubscription: Subscription | null = null;

  constructor(
    private readonly api: ApiService,
    private readonly session: SessionService,
    private readonly router: Router
  ) {}

  ngOnInit(): void {
    const adminSession = this.session.getAdminSession();
    if (!adminSession) {
      this.router.navigateByUrl('/admin/sign-in');
      return;
    }
    this.adminEmail = adminSession.email;
    this.adminInitials = this.resolveInitials(adminSession.email);
    this.syncSectionLabel(this.router.url);
    this.navSubscription = this.router.events
      .pipe(filter((event): event is NavigationEnd => event instanceof NavigationEnd))
      .subscribe((event) => this.syncSectionLabel(event.urlAfterRedirects));
    this.refreshOverview();
  }

  ngOnDestroy(): void {
    this.navSubscription?.unsubscribe();
    this.navSubscription = null;
  }

  signOut(): void {
    this.session.clearAdminSession();
    this.router.navigateByUrl('/admin/sign-in');
  }

  switchToClientSignIn(): void {
    this.session.clearAdminSession();
    this.session.clearClientSession();
    this.router.navigateByUrl('/sign-in');
  }

  refreshOverview(): void {
    const authToken = this.requireAdminToken();
    if (!authToken) {
      return;
    }

    this.kpiLoading = true;
    this.setDashboardStatus('Refreshing admin KPIs...', 'busy');
    forkJoin({
      workspaces: this.api.listWorkspaces(authToken),
      users: this.api.listUsers(authToken),
      billingEvents: this.api.listBillingEvents(authToken, 80),
      auditLogs: this.api.listAuditLogs(authToken, 80),
      securityBackend: this.api.getAuthSecurityBackendStatus(authToken),
    }).subscribe({
      next: ({ workspaces, users, billingEvents, auditLogs, securityBackend }) => {
        this.applyKpis(workspaces, users, billingEvents, auditLogs);
        this.kpiSecurityConfigured = securityBackend.configured_backend;
        this.kpiSecurityActive = securityBackend.active_backend;
        const fallbackActivations = securityBackend.details['fallback_activations'];
        this.kpiFallbackActivations =
          typeof fallbackActivations === 'number'
            ? fallbackActivations
            : Number.parseInt(String(fallbackActivations ?? '0'), 10) || 0;
        this.lastRefreshedAt = new Date().toLocaleString();
        this.setDashboardStatus('KPIs refreshed successfully.', 'done');
      },
      error: (error: unknown) => {
        this.setDashboardStatus(this.api.extractErrorMessage(error), 'fail');
      },
      complete: () => {
        this.kpiLoading = false;
      },
    });
  }

  private applyKpis(
    workspaces: WorkspaceInfoResponse[],
    users: UserResponse[],
    billingEvents: BillingEventListResponse,
    auditLogs: AuditLogListResponse
  ): void {
    this.kpiWorkspaceCount = workspaces.length;
    this.kpiCapacityLimit = workspaces.reduce((sum, workspace) => sum + workspace.monthly_job_limit, 0);
    this.kpiCapacityUsed = workspaces.reduce((sum, workspace) => sum + workspace.current_period_jobs, 0);
    this.kpiUtilizationPercent =
      this.kpiCapacityLimit > 0 ? Math.min(999, Math.round((this.kpiCapacityUsed / this.kpiCapacityLimit) * 100)) : 0;

    this.kpiActiveClientUsers = users.filter((user) => user.role === 'client' && user.is_active).length;
    this.kpiActiveAdminUsers = users.filter((user) => user.role === 'admin' && user.is_active).length;

    this.kpiBillingFailures = billingEvents.items.filter((event) => event.status === 'failed').length;

    const oneDayAgo = Date.now() - 24 * 60 * 60 * 1000;
    this.kpiRecentAuditEvents = auditLogs.items.filter((row) => Date.parse(row.created_at) >= oneDayAgo).length;
  }

  private syncSectionLabel(url: string): void {
    if (url.includes('/admin/users')) {
      this.currentSectionLabel = 'Users';
      return;
    }
    if (url.includes('/admin/billing')) {
      this.currentSectionLabel = 'Billing';
      return;
    }
    if (url.includes('/admin/audit')) {
      this.currentSectionLabel = 'Audit Logs';
      return;
    }
    this.currentSectionLabel = 'Workspaces';
  }

  private resolveInitials(email: string): string {
    const value = email.trim();
    if (!value) {
      return 'AD';
    }
    const local = value.split('@')[0] || 'AD';
    const parts = local.split(/[.\-_ ]+/).filter((part) => part.length > 0);
    if (parts.length >= 2) {
      return `${parts[0].charAt(0)}${parts[1].charAt(0)}`.toUpperCase();
    }
    return local.slice(0, 2).toUpperCase();
  }

  private setDashboardStatus(message: string, style: UiStatus): void {
    this.dashboardStatusMessage = message;
    this.dashboardStatusStyle = style;
  }

  private requireAdminToken(): string | null {
    const token = this.session.getAdminSession()?.token.trim() ?? '';
    if (token) {
      return token;
    }
    this.setDashboardStatus('Session expired. Please sign in again.', 'fail');
    this.session.clearAdminSession();
    this.router.navigateByUrl('/admin/sign-in');
    return null;
  }
}
