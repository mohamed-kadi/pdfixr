import { CommonModule } from '@angular/common';
import { Component, OnDestroy, OnInit } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { DomSanitizer, SafeResourceUrl } from '@angular/platform-browser';
import { ActivatedRoute, Router } from '@angular/router';
import { ApiService } from '../../core/api.service';
import { JobResponse, JobType, WorkspaceInfoResponse } from '../../core/models';
import { SessionService } from '../../core/session.service';

type UiStatus = 'idle' | 'busy' | 'done' | 'fail';

@Component({
  selector: 'app-client-portal',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './client-portal.component.html',
  styleUrl: './client-portal.component.css',
})
export class ClientPortalComponent implements OnInit, OnDestroy {
  clientEmail = '';
  workspace: WorkspaceInfoResponse | null = null;

  readonly operationTabs: Array<{
    type: JobType;
    icon: string;
    tone: 'fix' | 'compress' | 'merge' | 'split';
    title: string;
    subtitle: string;
    details: string;
    inputGuide: string;
    outputGuide: string;
  }> = [
    {
      type: 'font_fix',
      icon: 'FX',
      tone: 'fix',
      title: 'Fix Form Fields',
      subtitle: 'Cross-viewer form consistency',
      details:
        'Repairs fillable form appearance so typed values render consistently across Preview, Chrome, and other PDF viewers.',
      inputGuide: 'Upload one fillable PDF form.',
      outputGuide: 'Returns one fixed PDF with standardized form rendering behavior.',
    },
    {
      type: 'compress',
      icon: 'CP',
      tone: 'compress',
      title: 'Compress PDF',
      subtitle: 'Smaller file size',
      details: 'Reduces PDF size to improve sharing and upload speed while preserving document readability.',
      inputGuide: 'Upload one PDF document.',
      outputGuide: 'Returns one smaller PDF ready for download and sharing.',
    },
    {
      type: 'merge',
      icon: 'MG',
      tone: 'merge',
      title: 'Merge PDFs',
      subtitle: 'Combine multiple files',
      details: 'Combines multiple PDFs into one output file in the same order as the selected files.',
      inputGuide: 'Upload two or more PDF files.',
      outputGuide: 'Returns one merged PDF in the same file order you selected.',
    },
    {
      type: 'split',
      icon: 'SP',
      tone: 'split',
      title: 'Split PDF',
      subtitle: 'Export selected page ranges',
      details:
        'Creates separate PDFs from selected page ranges and returns them together as a ZIP download.',
      inputGuide: 'Upload one PDF and enter page ranges (example: 1-2,3,4-6).',
      outputGuide: 'Returns a ZIP containing one PDF per selected range.',
    },
  ];

  selectedFiles: File[] = [];
  selectedJobType: JobType = 'font_fix';
  splitRanges = '';
  splitDetectedPageCount: number | null = null;
  splitInspecting = false;
  splitInspectError: string | null = null;
  splitPreviewUrl: SafeResourceUrl | null = null;
  splitPreviewOpen = false;
  private splitPreviewObjectUrl: string | null = null;

  connectionMessage = 'Connection: not connected';
  connectionStatus: UiStatus = 'idle';

  statusMessage = 'No file submitted yet.';
  statusStyle: UiStatus = 'idle';

  jobs: JobResponse[] = [];
  activeJobId: string | null = null;
  isSubmitting = false;

  private pollTimer: ReturnType<typeof setInterval> | null = null;

  constructor(
    private readonly api: ApiService,
    private readonly session: SessionService,
    private readonly router: Router,
    private readonly route: ActivatedRoute,
    private readonly sanitizer: DomSanitizer
  ) {}

  ngOnInit(): void {
    if (this.session.hasAdminSession()) {
      this.router.navigateByUrl('/admin/workspaces');
      return;
    }

    const session = this.session.getClientSession();
    if (!session) {
      this.router.navigateByUrl('/sign-in');
      return;
    }

    this.clientEmail = session.email;
    this.applyRequestedOperation();
    this.refreshAll();
  }

  ngOnDestroy(): void {
    this.stopPolling();
    this.clearSplitAssist();
  }

  signOut(): void {
    this.stopPolling();
    this.session.clearClientSession();
    this.router.navigateByUrl('/sign-in');
  }

  onFileSelected(event: Event): void {
    const input = event.target as HTMLInputElement;
    this.selectedFiles = input.files ? Array.from(input.files) : [];
    this.clearSplitAssist();
  }

  selectOperation(jobType: JobType): void {
    if (this.selectedJobType === jobType) {
      return;
    }
    this.selectedJobType = jobType;
    this.selectedFiles = [];
    this.splitRanges = '';
    this.clearSplitAssist();
  }

  submit(): void {
    const authToken = this.requireAuthToken();
    if (!authToken) {
      return;
    }

    if (this.isLimitReached) {
      this.setStatus('Monthly limit reached. Contact your workspace admin to increase your plan.', 'fail');
      return;
    }

    const selectedCount = this.selectedFiles.length;
    if (this.selectedJobType === 'merge') {
      if (selectedCount < 2) {
        this.setStatus('Select at least 2 PDF files for merge.', 'fail');
        return;
      }
    } else if (this.selectedJobType === 'split') {
      if (selectedCount !== 1) {
        this.setStatus('Select 1 PDF file for split.', 'fail');
        return;
      }
      if (!this.splitRanges.trim()) {
        this.setStatus('Enter split ranges (example: 1-2,3,4-6).', 'fail');
        return;
      }
    } else if (selectedCount !== 1) {
      this.setStatus('Select 1 PDF file first.', 'fail');
      return;
    }

    this.isSubmitting = true;
    this.setStatus(`Uploading ${selectedCount} file(s) for ${this.jobTypeLabel(this.selectedJobType)}...`, 'busy');
    let jobOptions: Record<string, unknown> | undefined;
    if (this.selectedJobType === 'split') {
      jobOptions = { ranges: this.splitRanges.trim() };
    }
    this.api.createJob(authToken, this.selectedFiles, this.selectedJobType, jobOptions).subscribe({
      next: (job) => {
        this.activeJobId = job.id;
        this.setStatus(`File ${job.id.slice(0, 8)} submitted for ${this.jobTypeLabel(job.job_type)}.`, 'busy');
        this.fetchJobs();
        this.startPolling(job.id);
      },
      error: (error: unknown) => {
        this.setStatus(this.api.extractErrorMessage(error), 'fail');
      },
      complete: () => {
        this.isSubmitting = false;
      },
    });
  }

  refreshAll(): void {
    this.fetchWorkspace();
    this.fetchJobs();
  }

  download(job: JobResponse): void {
    const authToken = this.requireAuthToken();
    if (!authToken) {
      return;
    }

    this.api.downloadJob(authToken, job.id).subscribe({
      next: (blob) => {
        const url = URL.createObjectURL(blob);
        const anchor = document.createElement('a');
        anchor.href = url;
        anchor.download = this.downloadName(job.original_filename, job.id, job.job_type);
        document.body.appendChild(anchor);
        anchor.click();
        anchor.remove();
        URL.revokeObjectURL(url);
      },
      error: (error: unknown) => {
        this.setStatus(this.api.extractErrorMessage(error), 'fail');
      },
    });
  }

  formatDate(value: string): string {
    const dt = new Date(value);
    if (Number.isNaN(dt.getTime())) {
      return value;
    }
    return dt.toLocaleString();
  }

  trackByJobId(_: number, job: JobResponse): string {
    return job.id;
  }

  trackByOperationType(_: number, tab: { type: JobType }): JobType {
    return tab.type;
  }

  get selectedFileName(): string {
    if (this.selectedFiles.length === 0) {
      return 'No files selected';
    }
    if (this.selectedFiles.length === 1) {
      return this.selectedFiles[0].name;
    }
    return `${this.selectedFiles.length} files selected`;
  }

  get isMergeSelected(): boolean {
    return this.selectedJobType === 'merge';
  }

  get isSplitSelected(): boolean {
    return this.selectedJobType === 'split';
  }

  get activeOperation(): {
    type: JobType;
    title: string;
    subtitle: string;
    details: string;
    inputGuide: string;
    outputGuide: string;
  } {
    return (
      this.operationTabs.find((operation) => operation.type === this.selectedJobType) ?? this.operationTabs[0]
    );
  }

  get workspaceName(): string {
    return this.workspace?.name ?? 'Workspace';
  }

  get workspacePlan(): string {
    return this.workspace?.plan_name ?? 'Plan unavailable';
  }

  get usageJobs(): number {
    return this.workspace?.current_period_jobs ?? 0;
  }

  get monthlyLimit(): number {
    return this.workspace?.monthly_job_limit ?? 0;
  }

  get remainingJobs(): number {
    return this.workspace?.remaining_jobs ?? 0;
  }

  get usagePercent(): number {
    if (!this.workspace || this.workspace.monthly_job_limit <= 0) {
      return 0;
    }
    return Math.min(100, Math.round((this.workspace.current_period_jobs / this.workspace.monthly_job_limit) * 100));
  }

  get isLimitReached(): boolean {
    if (!this.workspace) {
      return false;
    }
    return this.workspace.remaining_jobs <= 0;
  }

  get isNearLimit(): boolean {
    if (!this.workspace || this.workspace.monthly_job_limit <= 0) {
      return false;
    }
    return this.workspace.remaining_jobs > 0 && this.workspace.remaining_jobs <= 3;
  }

  get processingJobsCount(): number {
    return this.jobs.filter((job) => job.status === 'processing' || job.status === 'queued').length;
  }

  get completedJobsCount(): number {
    return this.jobs.filter((job) => job.status === 'completed').length;
  }

  get failedJobsCount(): number {
    return this.jobs.filter((job) => job.status === 'failed').length;
  }

  get latestJobUpdatedAt(): string {
    if (this.jobs.length === 0) {
      return 'No files yet';
    }
    return this.formatDate(this.jobs[0].updated_at);
  }

  private fetchWorkspace(): void {
    const authToken = this.requireAuthToken();
    if (!authToken) {
      return;
    }

    this.api.getWorkspace(authToken).subscribe({
      next: (workspace) => {
        this.workspace = workspace;
        this.connectionMessage = `Connected to ${workspace.name}`;
        this.connectionStatus = 'done';
      },
      error: (error: unknown) => {
        this.workspace = null;
        this.connectionMessage = this.api.extractErrorMessage(error);
        this.connectionStatus = 'fail';
      },
    });
  }

  private fetchJobs(): void {
    const authToken = this.requireAuthToken();
    if (!authToken) {
      return;
    }

    this.api.listJobs(authToken).subscribe({
      next: (payload) => {
        this.jobs = [...payload.items].sort((left, right) => this.toTimestamp(right.updated_at) - this.toTimestamp(left.updated_at));
      },
      error: (error: unknown) => {
        this.setStatus(this.api.extractErrorMessage(error), 'fail');
      },
    });
  }

  private startPolling(jobId: string): void {
    this.stopPolling();
    this.pollTimer = setInterval(() => {
      const authToken = this.requireAuthToken();
      if (!authToken) {
        this.stopPolling();
        return;
      }

      this.api.getJob(authToken, jobId).subscribe({
        next: (job) => {
          this.fetchJobs();
          if (job.status === 'completed') {
            this.setStatus('File is ready. You can download it now.', 'done');
            this.stopPolling();
            return;
          }
          if (job.status === 'failed') {
            this.setStatus(`Processing failed: ${job.error_message ?? 'Unknown error.'}`, 'fail');
            this.stopPolling();
            return;
          }
          if (job.status === 'processing') {
            this.setStatus('Processing...', 'busy');
            return;
          }
          this.setStatus('Waiting in queue...', 'idle');
        },
        error: (error: unknown) => {
          this.setStatus(this.api.extractErrorMessage(error), 'fail');
          this.stopPolling();
        },
      });
    }, 1800);
  }

  private stopPolling(): void {
    if (this.pollTimer) {
      clearInterval(this.pollTimer);
      this.pollTimer = null;
    }
  }

  private setStatus(message: string, style: UiStatus): void {
    this.statusMessage = message;
    this.statusStyle = style;
  }

  jobTypeLabel(type: JobType): string {
    if (type === 'compress') {
      return 'PDF Compression';
    }
    if (type === 'merge') {
      return 'PDF Merge';
    }
    if (type === 'split') {
      return 'PDF Split';
    }
    return 'Font Fix';
  }

  compressionSummary(job: JobResponse): string | null {
    if (job.job_type !== 'compress' || job.status !== 'completed') {
      return null;
    }
    if (job.input_size_bytes == null || job.output_size_bytes == null || job.size_reduction_percent == null) {
      return null;
    }
    const direction = job.size_reduction_percent >= 0 ? 'smaller' : 'larger';
    const pct = Math.abs(job.size_reduction_percent).toFixed(1);
    return `${pct}% ${direction} (${this.formatBytes(job.input_size_bytes)} -> ${this.formatBytes(job.output_size_bytes)})`;
  }

  private formatBytes(bytes: number): string {
    if (bytes < 1024) {
      return `${bytes} B`;
    }
    const units = ['KB', 'MB', 'GB'];
    let value = bytes / 1024;
    let idx = 0;
    while (value >= 1024 && idx < units.length - 1) {
      value /= 1024;
      idx += 1;
    }
    return `${value.toFixed(1)} ${units[idx]}`;
  }

  private downloadName(originalFilename: string, jobId: string, jobType: JobType): string {
    let suffix = '_fixed';
    if (jobType === 'compress') {
      suffix = '_compressed';
    } else if (jobType === 'merge') {
      suffix = '_merged';
    }
    const lower = originalFilename.toLowerCase();
    if (jobType === 'split') {
      if (lower.endsWith('.pdf')) {
        return `${originalFilename.slice(0, -4)}_split.zip`;
      }
      return `${jobId}_split.zip`;
    }
    if (lower.endsWith('.pdf')) {
      return `${originalFilename.slice(0, -4)}${suffix}.pdf`;
    }
    return `${jobId}${suffix}.pdf`;
  }

  private requireAuthToken(): string | null {
    const token = this.session.getClientSession()?.token.trim() ?? '';
    if (token) {
      return token;
    }

    this.setStatus('Session expired. Please sign in again.', 'fail');
    this.session.clearClientSession();
    this.router.navigateByUrl('/sign-in');
    return null;
  }

  private toTimestamp(value: string): number {
    const parsed = Date.parse(value);
    if (Number.isNaN(parsed)) {
      return 0;
    }
    return parsed;
  }

  private applyRequestedOperation(): void {
    const raw = this.route.snapshot.queryParamMap.get('operation');
    if (raw === 'font_fix' || raw === 'compress' || raw === 'merge' || raw === 'split') {
      this.selectedJobType = raw;
      this.selectedFiles = [];
      this.splitRanges = '';
      this.clearSplitAssist();
    }
  }

  detectSplitPageCount(): void {
    if (!this.isSplitSelected || this.selectedFiles.length !== 1) {
      return;
    }
    this.splitInspectError = null;
    const selected = this.selectedFiles[0];
    const authToken = this.requireAuthToken();
    if (!authToken) {
      return;
    }

    this.splitInspecting = true;
    this.api.inspectPdf(authToken, selected).subscribe({
      next: (payload) => {
        this.splitDetectedPageCount = payload.page_count;
      },
      error: (error: unknown) => {
        this.splitInspectError = this.api.extractErrorMessage(error);
      },
      complete: () => {
        this.splitInspecting = false;
      },
    });
  }

  openSplitPreview(): void {
    if (!this.isSplitSelected || this.selectedFiles.length !== 1 || this.splitPreviewOpen) {
      return;
    }
    const selected = this.selectedFiles[0];
    const objectUrl = URL.createObjectURL(selected);
    this.splitPreviewObjectUrl = objectUrl;
    this.splitPreviewUrl = this.sanitizer.bypassSecurityTrustResourceUrl(`${objectUrl}#page=1&zoom=page-fit`);
    this.splitPreviewOpen = true;
  }

  closeSplitPreview(): void {
    this.splitPreviewOpen = false;
    this.splitPreviewUrl = null;
    if (this.splitPreviewObjectUrl) {
      URL.revokeObjectURL(this.splitPreviewObjectUrl);
      this.splitPreviewObjectUrl = null;
    }
  }

  private clearSplitAssist(): void {
    this.splitDetectedPageCount = null;
    this.splitInspecting = false;
    this.splitInspectError = null;
    this.closeSplitPreview();
  }
}
