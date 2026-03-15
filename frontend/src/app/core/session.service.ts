import { Injectable } from '@angular/core';

export interface ClientSession {
  email: string;
  token: string;
  expiresAt: string;
}

export interface AdminSession {
  email: string;
  token: string;
  expiresAt: string;
}

@Injectable({ providedIn: 'root' })
export class SessionService {
  private static readonly CLIENT_SESSION_KEY = 'pdf_saas_client_session';
  private static readonly ADMIN_SESSION_KEY = 'pdf_saas_admin_session';

  getClientSession(): ClientSession | null {
    const session = this.readSession<ClientSession>(SessionService.CLIENT_SESSION_KEY, this.isClientSession);
    if (!session) {
      return null;
    }
    if (this.isExpired(session.expiresAt)) {
      this.removeSession(SessionService.CLIENT_SESSION_KEY);
      return null;
    }
    return session;
  }

  setClientSession(session: ClientSession): void {
    this.writeSession(SessionService.CLIENT_SESSION_KEY, {
      email: session.email.trim(),
      token: session.token.trim(),
      expiresAt: session.expiresAt,
    });
  }

  clearClientSession(): void {
    this.removeSession(SessionService.CLIENT_SESSION_KEY);
  }

  hasClientSession(): boolean {
    return this.getClientSession() !== null;
  }

  getAdminSession(): AdminSession | null {
    const session = this.readSession<AdminSession>(SessionService.ADMIN_SESSION_KEY, this.isAdminSession);
    if (!session) {
      return null;
    }
    if (this.isExpired(session.expiresAt)) {
      this.removeSession(SessionService.ADMIN_SESSION_KEY);
      return null;
    }
    return session;
  }

  setAdminSession(session: AdminSession): void {
    this.writeSession(SessionService.ADMIN_SESSION_KEY, {
      email: session.email.trim(),
      token: session.token.trim(),
      expiresAt: session.expiresAt,
    });
  }

  clearAdminSession(): void {
    this.removeSession(SessionService.ADMIN_SESSION_KEY);
  }

  hasAdminSession(): boolean {
    return this.getAdminSession() !== null;
  }

  private readSession<T>(key: string, isValid: (value: unknown) => value is T): T | null {
    try {
      const raw = localStorage.getItem(key);
      if (!raw) {
        return null;
      }
      const parsed: unknown = JSON.parse(raw);
      if (!isValid(parsed)) {
        return null;
      }
      return parsed;
    } catch {
      return null;
    }
  }

  private writeSession(key: string, value: object): void {
    try {
      localStorage.setItem(key, JSON.stringify(value));
    } catch {
      // Ignore storage errors in restrictive browser contexts.
    }
  }

  private removeSession(key: string): void {
    try {
      localStorage.removeItem(key);
    } catch {
      // Ignore storage errors in restrictive browser contexts.
    }
  }

  private isClientSession(value: unknown): value is ClientSession {
    if (!value || typeof value !== 'object') {
      return false;
    }

    const row = value as Record<string, unknown>;
    return (
      typeof row['email'] === 'string' &&
      !!row['email'].trim() &&
      typeof row['token'] === 'string' &&
      !!row['token'].trim() &&
      typeof row['expiresAt'] === 'string' &&
      !!row['expiresAt'].trim()
    );
  }

  private isAdminSession(value: unknown): value is AdminSession {
    if (!value || typeof value !== 'object') {
      return false;
    }

    const row = value as Record<string, unknown>;
    return (
      typeof row['email'] === 'string' &&
      !!row['email'].trim() &&
      typeof row['token'] === 'string' &&
      !!row['token'].trim() &&
      typeof row['expiresAt'] === 'string' &&
      !!row['expiresAt'].trim()
    );
  }

  private isExpired(expiresAt: string): boolean {
    const timestamp = Date.parse(expiresAt);
    if (Number.isNaN(timestamp)) {
      return true;
    }
    return timestamp <= Date.now();
  }
}
