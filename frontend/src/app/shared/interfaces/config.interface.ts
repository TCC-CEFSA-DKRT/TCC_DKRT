export type BrokerKind = 'local' | 'cloud';

export type BrokerConnectionStatus =
  | 'ok'
  | 'invalid_url'
  | 'unreachable'
  | 'timeout'
  | 'unauthorized'
  | 'unexpected_response';

export interface BrokerTargetRequest {
  broker_url: string;
  fiware_service: string;
  fiware_service_path: string;
  broker_kind: BrokerKind;
  broker_api_key: string | null;
}

export interface BrokerConfigRequest extends BrokerTargetRequest {
  save_without_connection: boolean;
}

export interface BrokerConnectionTestResponse {
  status: BrokerConnectionStatus;
  entity_types_count: number | null;
  http_status: number | null;
}

export interface BrokerConfigResponse {
  configured: boolean;
  broker_url: string;
  fiware_service: string;
  fiware_service_path: string;
  broker_kind: BrokerKind;
  has_api_key: boolean;
  default_local_broker_url: string;
  connection: BrokerConnectionTestResponse | null;
}

export interface BrokerConnectionFailedDetail {
  message: string;
  connection: BrokerConnectionTestResponse;
}

export interface EntityTypesResponse {
  types: string[];
  broker_reachable: boolean;
}
