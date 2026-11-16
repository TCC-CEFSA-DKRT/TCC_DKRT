import { InjectionToken } from '@angular/core';

import { ApiConfig } from './api-config.interface';

export const API_CONFIG = new InjectionToken<ApiConfig>('API_CONFIG');

export const DEFAULT_API_CONFIG: ApiConfig = {
  baseUrl: 'http://localhost:8000',
};
