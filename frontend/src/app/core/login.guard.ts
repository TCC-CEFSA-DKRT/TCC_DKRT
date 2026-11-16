import { inject } from '@angular/core';
import { CanActivateFn, Router } from '@angular/router';
import { catchError, map, of } from 'rxjs';

import { safeReturnUrl } from './return-url';
import { HOME_PATH, RETURN_URL_PARAM } from './session.constants';
import { SessionService } from './session.service';

export const loginGuard: CanActivateFn = (route) => {
  const session = inject(SessionService);
  const router = inject(Router);

  return session.load().pipe(
    map((s) => {
      if (s.deployment_mode === 'selfhosted') {
        return router.parseUrl(HOME_PATH);
      }
      if (s.tenant) {
        return router.parseUrl(safeReturnUrl(route.queryParamMap.get(RETURN_URL_PARAM)));
      }
      return true;
    }),
    catchError(() => of(true))
  );
};
