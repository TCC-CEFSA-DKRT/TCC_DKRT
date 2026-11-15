import { HttpErrorResponse, HttpInterceptorFn } from '@angular/common/http';
import { inject } from '@angular/core';
import { Router } from '@angular/router';
import { catchError, throwError } from 'rxjs';

import { API_CONFIG } from './api-config';
import { LOGIN_PATH } from './session.constants';
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
        if (current.tenant) {
          session.expire(router.url);
        } else {
          router.navigateByUrl(LOGIN_PATH);
        }
      }
      return throwError(() => error);
    })
  );
};
