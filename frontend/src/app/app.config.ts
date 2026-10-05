import { ApplicationConfig, provideZoneChangeDetection } from '@angular/core';
import { provideRouter } from '@angular/router';
import { provideHttpClient, withInterceptors } from '@angular/common/http';

import { routes } from './app.routes';
import { API_CONFIG, DEFAULT_API_CONFIG } from './core/api-config';
import { tenantInterceptor } from './core/tenant.interceptor';

export const appConfig: ApplicationConfig = {
  providers: [
    provideZoneChangeDetection({ eventCoalescing: true }),
    provideRouter(routes),
    provideHttpClient(withInterceptors([tenantInterceptor])),
    { provide: API_CONFIG, useValue: DEFAULT_API_CONFIG },
  ],
};
