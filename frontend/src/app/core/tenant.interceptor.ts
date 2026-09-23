import { HttpInterceptorFn } from '@angular/common/http';
import { inject } from '@angular/core';
import { API_CONFIG } from './api-config';

/**
 * Anexa os headers de tenant (`Fiware-Service`/`Fiware-ServicePath`) a toda
 * chamada feita para a API do backend — espelha `_TENANT_HEADERS` usado nos
 * testes do backend (Fase 4, `interfaces/rest/dependencies.get_tenant`),
 * que rejeita com 401 qualquer requisição sem `Fiware-Service`.
 *
 * Só anexa para requisições que de fato vão para a API configurada (nunca
 * para outros domínios, ex.: fontes de fonte do Google, se algum dia
 * houver chamada `fetch` fora do HttpClient para isso).
 */
export const tenantInterceptor: HttpInterceptorFn = (req, next) => {
  const config = inject(API_CONFIG);
  if (!req.url.startsWith(config.baseUrl)) {
    return next(req);
  }
  const cloned = req.clone({
    setHeaders: {
      'Fiware-Service': config.tenant.fiwareService,
      'Fiware-ServicePath': config.tenant.fiwareServicePath,
    },
  });
  return next(cloned);
};
