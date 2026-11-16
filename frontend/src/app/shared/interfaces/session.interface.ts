export interface TenantResponse {
  fiware_service: string;
  fiware_service_path: string;
}

export interface Session {
  deployment_mode: 'saas' | 'selfhosted';
  tenant: TenantResponse | null;
}
