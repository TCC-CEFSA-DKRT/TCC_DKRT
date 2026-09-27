import { InjectionToken } from '@angular/core';

export interface ApiConfig {
  readonly baseUrl: string;
}

export const API_CONFIG = new InjectionToken<ApiConfig>('API_CONFIG');

export const DEFAULT_API_CONFIG: ApiConfig = {
  baseUrl: 'http://localhost:8000',
};
