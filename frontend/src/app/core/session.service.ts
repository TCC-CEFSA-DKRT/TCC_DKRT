import { HttpClient } from '@angular/common/http';
import { Injectable, inject, signal } from '@angular/core';
import { Observable } from 'rxjs';
import { switchMap, tap } from 'rxjs/operators';

import { Session } from '../shared/models/session.models';
import { API_CONFIG } from './api-config';

@Injectable({ providedIn: 'root' })
export class SessionService {
  private readonly http = inject(HttpClient);
  private readonly config = inject(API_CONFIG);

  readonly session = signal<Session | null>(null);

  load(): Observable<Session> {
    return this.http
      .get<Session>(`${this.config.baseUrl}/session`)
      .pipe(tap((session) => this.session.set(session)));
  }

  login(loginEmail: string, password: string): Observable<Session> {
    return this.http
      .post(`${this.config.baseUrl}/auth/login`, { login_email: loginEmail, password })
      .pipe(switchMap(() => this.load()));
  }

  logout(): Observable<void> {
    return this.http
      .post<void>(`${this.config.baseUrl}/auth/logout`, {})
      .pipe(tap(() => this.session.update((s) => (s ? { ...s, tenant: null } : s))));
  }
}
