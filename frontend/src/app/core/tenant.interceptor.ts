import { HttpErrorResponse, HttpInterceptorFn } from '@angular/common/http';
import { inject } from '@angular/core';
import { Router } from '@angular/router';
import { catchError, throwError } from 'rxjs';

import { API_CONFIG } from './api-config';
import { SessionService } from './session.service';

export const tenantInterceptor: HttpInterceptorFn = (req, next) => {
  const config = inject(API_CONFIG);
  if (!req.url.startsWith(config.baseUrl)) {
    return next(req);
  }

  const session = inject(SessionService);
  const router = inject(Router);
  const current = session.session();

  const cloned = req.clone({ withCredentials: true });

  return next(cloned).pipe(
    catchError((error: unknown) => {
      if (
        error instanceof HttpErrorResponse &&
        error.status === 401 &&
        current?.deployment_mode === 'saas' &&
        !req.url.endsWith('/auth/login')
      ) {
        session.session.update((s) => (s ? { ...s, tenant: null } : s));
        router.navigateByUrl('/login');
      }
      return throwError(() => error);
    })
  );
};
