import { inject } from '@angular/core';
import { CanActivateFn, Router } from '@angular/router';
import { catchError, map, of } from 'rxjs';

import { LOGIN_PATH, RETURN_URL_PARAM } from './session.constants';
import { SessionService } from './session.service';

export const appGuard: CanActivateFn = (_route, state) => {
  const session = inject(SessionService);
  const router = inject(Router);

  const cached = session.session();
  const source = cached?.tenant ? of(cached) : session.load();

  return source.pipe(
    map((s) => {
      if (s.tenant) {
        return true;
      }
      if (s.deployment_mode === 'saas') {
        return router.createUrlTree([LOGIN_PATH], { queryParams: { [RETURN_URL_PARAM]: state.url } });
      }
      return router.parseUrl('/config');
    }),
    catchError(() => of(true))
  );
};
