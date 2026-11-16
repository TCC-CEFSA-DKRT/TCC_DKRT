import { HttpClient } from '@angular/common/http';
import { Injectable, inject, signal } from '@angular/core';
import { Router } from '@angular/router';
import { Observable } from 'rxjs';
import { switchMap, tap } from 'rxjs/operators';

import { Session } from '../shared/interfaces/session.interface';
import { API_CONFIG } from './api-config';
import {
  LOGIN_PATH,
  LOGIN_REASON_PARAM,
  MAX_TIMER_DELAY_MS,
  RETURN_URL_PARAM,
  SESSION_EXPIRED_REASON,
} from './session.constants';

@Injectable({ providedIn: 'root' })
export class SessionService {
  private readonly http = inject(HttpClient);
  private readonly config = inject(API_CONFIG);
  private readonly router = inject(Router);
  private expiryTimer: ReturnType<typeof setTimeout> | null = null;

  readonly session = signal<Session | null>(null);

  load(): Observable<Session> {
    return this.http
      .get<Session>(`${this.config.baseUrl}/session`)
      .pipe(tap((session) => this.start(session)));
  }

  login(loginEmail: string, password: string): Observable<Session> {
    return this.http
      .post(`${this.config.baseUrl}/auth/login`, { login_email: loginEmail, password })
      .pipe(switchMap(() => this.load()));
  }

  logout(): Observable<void> {
    return this.http
      .post<void>(`${this.config.baseUrl}/auth/logout`, {})
      .pipe(tap(() => this.clearTenant()));
  }

  expire(returnUrl: string): void {
    if (!this.session()?.tenant) {
      return;
    }
    this.clearTenant();
    this.router.navigate([LOGIN_PATH], {
      queryParams: { [LOGIN_REASON_PARAM]: SESSION_EXPIRED_REASON, [RETURN_URL_PARAM]: returnUrl },
    });
  }

  private start(session: Session): void {
    this.cancelExpiryTimer();
    this.session.set(session);
    if (session.deployment_mode !== 'saas' || !session.tenant || !session.expires_at) {
      return;
    }
    const delay = Math.min(Math.max(Date.parse(session.expires_at) - Date.now(), 0), MAX_TIMER_DELAY_MS);
    this.expiryTimer = setTimeout(() => this.expire(this.router.url), delay);
  }

  private clearTenant(): void {
    this.cancelExpiryTimer();
    this.session.update((current) => (current ? { ...current, tenant: null, expires_at: null } : current));
  }

  private cancelExpiryTimer(): void {
    if (this.expiryTimer !== null) {
      clearTimeout(this.expiryTimer);
      this.expiryTimer = null;
    }
  }
}
