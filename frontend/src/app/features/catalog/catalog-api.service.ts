import { HttpClient, HttpParams } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';

import { API_CONFIG } from '../../core/api-config';
import { PageResponse } from '../../shared/models/audit.models';
import {
  CatalogModelResponse,
  CatalogModelSchemaResponse,
  CatalogStatusResponse,
} from '../../shared/models/catalog.models';

/** Fase 8, seção 7 — Catalog. `getStatus()` reaproveita `GET /catalog`
 * (backend `catalog_sync_status_repository.py`). `listModels()`/
 * `getModelSchema()` são follow-up pos-Fase 8 (`GET /catalog/models`,
 * `GET /catalog/models/{model_name}/schema`): a tela só mostrava o status
 * agregado, sem lista navegável dos modelos nem jeito de ver o conteúdo
 * de cada um. */
@Injectable({ providedIn: 'root' })
export class CatalogApiService {
  private readonly http = inject(HttpClient);
  private readonly config = inject(API_CONFIG);

  getStatus(): Observable<CatalogStatusResponse> {
    return this.http.get<CatalogStatusResponse>(`${this.config.baseUrl}/catalog`);
  }

  listModels(filters: {
    subject?: string;
    q?: string;
    page: number;
    page_size: number;
  }): Observable<PageResponse<CatalogModelResponse>> {
    let params = new HttpParams().set('page', filters.page).set('page_size', filters.page_size);
    if (filters.subject) {
      params = params.set('subject', filters.subject);
    }
    if (filters.q) {
      params = params.set('q', filters.q);
    }
    return this.http.get<PageResponse<CatalogModelResponse>>(`${this.config.baseUrl}/catalog/models`, {
      params,
    });
  }

  getModelSchema(subject: string, modelName: string): Observable<CatalogModelSchemaResponse> {
    const params = new HttpParams().set('subject', subject);
    return this.http.get<CatalogModelSchemaResponse>(
      `${this.config.baseUrl}/catalog/models/${encodeURIComponent(modelName)}/schema`,
      { params }
    );
  }
}
