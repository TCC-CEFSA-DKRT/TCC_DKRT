/** Espelha `CatalogStatusResponse` (backend, `interfaces/rest/schemas.py`). */
export interface CatalogStatusResponse {
  last_synced_at: string | null;
  last_sync_successful: boolean | null;
  last_sync_error: string | null;
  models_count: number | null;
}

/** Espelha `CatalogModelResponse` -- um item de `GET /catalog/models`
 * (follow-up pos-Fase 8: a tela so mostrava o status agregado, sem lista
 * navegavel). `subject` vai junto de proposito: e' o que desambigua um
 * `model_name` que exista em mais de um subject. */
export interface CatalogModelResponse {
  subject: string;
  model_name: string;
}

/** Espelha `CatalogModelSchemaResponse` -- conteudo de `GET
 * /catalog/models/{model_name}/schema`. `source` ("live" | "cache") vem
 * do mesmo pipeline de cache de 6 camadas usado pela auditoria em si
 * (SmartDataModelsAdapter.fetch_schema, Fase 2) -- nunca disfarça cache
 * de "ao vivo". */
export interface CatalogModelSchemaResponse {
  subject: string;
  model_name: string;
  version: string;
  schema_url: string;
  content: unknown;
  source: string;
  fetched_at: string;
}
