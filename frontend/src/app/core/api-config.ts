import { InjectionToken } from '@angular/core';

/**
 * Fase 8 — configuração da API e do tenant.
 *
 * Não há tela de login/troca de tenant nesta fase (fora de escopo, ver
 * fase8.spec.md seção 8) — o tenant é fixo em tempo de build, mesmo
 * princípio que os testes de backend usam (`Fiware-Service`/
 * `Fiware-ServicePath` fixos em `_TENANT_HEADERS`). Uma tela de troca de
 * tenant fica para quando autenticação real existir (plano geral, seção
 * 3.8).
 */
export interface ApiConfig {
  readonly baseUrl: string;
  readonly tenant: {
    readonly fiwareService: string;
    readonly fiwareServicePath: string;
  };
}

export const API_CONFIG = new InjectionToken<ApiConfig>('API_CONFIG');

export const DEFAULT_API_CONFIG: ApiConfig = {
  baseUrl: 'http://localhost:8000',
  tenant: {
    fiwareService: 'openiot',
    fiwareServicePath: '/',
  },
};
