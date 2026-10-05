import { inject } from '@angular/core';
import { CanActivateFn, Router } from '@angular/router';
import { catchError, map, of } from 'rxjs';

import { SessionService } from './session.service';

export const appGuard: CanActivateFn = () => {
  const session = inject(SessionService);
  const router = inject(Router);

  const cached = session.session();
  const source = cached?.tenant ? of(cached) : session.load();

  return source.pipe(
    map((s) => s.tenant ? true : router.parseUrl(s.deployment_mode === 'saas' ? '/login' : '/config')),
    catchError(() => of(true))
  );
};
