import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';

import { API_CONFIG } from '../../core/api-config';
import {
  BrokerConfigRequest,
  BrokerConfigResponse,
  BrokerConnectionTestResponse,
  BrokerTargetRequest,
} from '../../shared/interfaces/config.interface';
import { ConfigFormValues } from './config.interface';

export function toBrokerTarget(values: ConfigFormValues): BrokerTargetRequest {
  const apiKey = values.apiKey.trim();
  return {
    broker_url: values.brokerUrl.trim(),
    fiware_service: values.fiwareService.trim(),
    fiware_service_path: values.fiwareServicePath.trim() || '/',
    broker_kind: values.brokerKind,
    broker_api_key: values.brokerKind === 'cloud' && apiKey ? apiKey : null,
    ngsi_version: values.ngsiVersion,
  };
}

@Injectable({ providedIn: 'root' })
export class ConfigApiService {
  private readonly http = inject(HttpClient);
  private readonly config = inject(API_CONFIG);

  load(): Observable<BrokerConfigResponse> {
    return this.http.get<BrokerConfigResponse>(`${this.config.baseUrl}/config`);
  }

  testConnection(values: ConfigFormValues): Observable<BrokerConnectionTestResponse> {
    return this.http.post<BrokerConnectionTestResponse>(
      `${this.config.baseUrl}/config/test`,
      toBrokerTarget(values)
    );
  }

  save(values: ConfigFormValues, saveWithoutConnection: boolean): Observable<BrokerConfigResponse> {
    const body: BrokerConfigRequest = {
      ...toBrokerTarget(values),
      save_without_connection: saveWithoutConnection,
    };
    return this.http.put<BrokerConfigResponse>(`${this.config.baseUrl}/config`, body);
  }
}
