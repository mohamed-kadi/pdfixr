import { CommonModule } from '@angular/common';
import { Component, OnInit } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { Router } from '@angular/router';
import { ApiService } from '../../core/api.service';
import { BillingStatus, WorkspaceCreateResponse, WorkspaceInfoResponse } from '../../core/models';
import { SessionService } from '../../core/session.service';

type UiStatus = 'idle' | 'done' | 'fail';

interface AdminWorkspaceRow extends WorkspaceInfoResponse {
  editPlanName: string;
  editMonthlyLimit: number;
  editBillingStatus: BillingStatus;
}

@Component({
  selector: 'app-admin-workspaces',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './admin-workspaces.component.html',
  styleUrl: './admin-workspaces.component.css',
})
export class AdminWorkspacesComponent implements OnInit {
  readonly planOptions = ['starter', 'pro', 'business', 'enterprise'] as const;
  readonly billingStatusOptions: readonly BillingStatus[] = ['trialing', 'active', 'past_due', 'canceled', 'inactive'];

  statusMessage = 'Workspace management ready.';
  statusStyle: UiStatus = 'idle';

  createName = '';
  createPlanName = 'starter';
  createMonthlyLimit: number | null = null;
  createMessage = 'No workspace created yet.';
  createStyle: UiStatus = 'idle';
  createdSecret = 'Client access code will appear here once created.';

  workspaces: AdminWorkspaceRow[] = [];

  loading = false;
  creatingWorkspace = false;
  savingWorkspaceId: string | null = null;

  constructor(
    private readonly api: ApiService,
    private readonly session: SessionService,
    private readonly router: Router
  ) {}

  ngOnInit(): void {
    this.refreshWorkspaces();
  }

  refreshWorkspaces(): void {
    const authToken = this.requireAdminToken();
    if (!authToken) {
      return;
    }

    this.loading = true;
    this.api.listWorkspaces(authToken).subscribe({
      next: (workspaces) => {
        this.workspaces = workspaces.map((workspace) => this.toEditableWorkspace(workspace));
        this.setStatus('Workspaces refreshed.', 'done');
      },
      error: (error: unknown) => {
        this.setStatus(this.api.extractErrorMessage(error), 'fail');
      },
      complete: () => {
        this.loading = false;
      },
    });
  }

  createWorkspace(): void {
    const authToken = this.requireAdminToken();
    if (!authToken) {
      this.setCreateMessage('Session expired. Sign in again.', 'fail');
      return;
    }

    const trimmedName = this.createName.trim();
    if (!trimmedName) {
      this.setCreateMessage('Workspace name is required.', 'fail');
      return;
    }

    if (this.createMonthlyLimit !== null && this.createMonthlyLimit < 1) {
      this.setCreateMessage('Monthly limit must be a positive number.', 'fail');
      return;
    }

    this.creatingWorkspace = true;
    this.api
      .createWorkspace(authToken, {
        name: trimmedName,
        plan_name: this.createPlanName,
        monthly_job_limit: this.createMonthlyLimit,
      })
      .subscribe({
        next: (created) => {
          this.applyCreatedWorkspaceSecret(created);
          this.createName = '';
          this.createMonthlyLimit = null;
          this.setCreateMessage(`Workspace "${created.name}" created. Send access code to the client.`, 'done');
          this.refreshWorkspaces();
        },
        error: (error: unknown) => {
          this.setCreateMessage(this.api.extractErrorMessage(error), 'fail');
        },
        complete: () => {
          this.creatingWorkspace = false;
        },
      });
  }

  saveWorkspace(workspace: AdminWorkspaceRow): void {
    const authToken = this.requireAdminToken();
    if (!authToken) {
      this.setStatus('Session expired. Sign in again.', 'fail');
      return;
    }

    if (workspace.editMonthlyLimit < 1) {
      this.setStatus('Monthly limit must be a positive number.', 'fail');
      return;
    }

    this.savingWorkspaceId = workspace.id;
    this.api
      .updateWorkspacePlan(authToken, workspace.id, {
        plan_name: workspace.editPlanName,
        monthly_job_limit: workspace.editMonthlyLimit,
        billing_status: workspace.editBillingStatus,
      })
      .subscribe({
        next: () => {
          this.setStatus(`Workspace ${workspace.name} updated.`, 'done');
          this.refreshWorkspaces();
        },
        error: (error: unknown) => {
          this.setStatus(this.api.extractErrorMessage(error), 'fail');
        },
        complete: () => {
          this.savingWorkspaceId = null;
        },
      });
  }

  isSaving(workspaceId: string): boolean {
    return this.savingWorkspaceId === workspaceId;
  }

  trackByWorkspaceId(_: number, workspace: AdminWorkspaceRow): string {
    return workspace.id;
  }

  private toEditableWorkspace(workspace: WorkspaceInfoResponse): AdminWorkspaceRow {
    return {
      ...workspace,
      editPlanName: workspace.plan_name,
      editMonthlyLimit: workspace.monthly_job_limit,
      editBillingStatus: workspace.billing_status,
    };
  }

  private applyCreatedWorkspaceSecret(created: WorkspaceCreateResponse): void {
    this.createdSecret = JSON.stringify(
      {
        workspace_id: created.id,
        name: created.name,
        access_code: created.api_key,
        access_code_id: created.api_key_prefix,
      },
      null,
      2
    );
  }

  private setStatus(message: string, style: UiStatus): void {
    this.statusMessage = message;
    this.statusStyle = style;
  }

  private setCreateMessage(message: string, style: UiStatus): void {
    this.createMessage = message;
    this.createStyle = style;
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
