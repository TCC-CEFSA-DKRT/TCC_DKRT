export interface BrokerConfigRequest {
  broker_url: string;
  fiware_service: string;
  fiware_service_path: string;
}

export interface BrokerConfigResponse {
  configured: boolean;
  broker_url: string;
  fiware_service: string;
  fiware_service_path: string;
}

export interface EntityTypesResponse {
  types: string[];
  broker_reachable: boolean;
}
