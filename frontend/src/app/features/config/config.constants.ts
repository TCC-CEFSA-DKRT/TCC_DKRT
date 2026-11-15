import { BrokerConnectionStatus } from '../../shared/interfaces/config.interface';
import { BrokerKindOption, ConfigField } from './config.interface';

export const BROKER_URL_PATTERN = /^https?:\/\/\S+$/;

export const FIWARE_SERVICE_PATTERN = /^[A-Za-z0-9_]{0,50}$/;

export const FIWARE_SERVICE_PATH_PATTERN = /^\/([A-Za-z0-9_]+(\/[A-Za-z0-9_]+)*)?$/;

export const API_KEY_PATTERN = /^\S*$/;

export const CONNECTION_TEST_TIMEOUT_SECONDS = 5;

export const BROKER_KIND_OPTIONS: BrokerKindOption[] = [
  {
    value: 'local',
    title: 'Instância Docker local',
    description: 'Orion rodando nesta máquina pelo docker compose do projeto.',
  },
  {
    value: 'cloud',
    title: 'Broker em nuvem',
    description: 'Orion hospedado em outro servidor, acessado por https:// e, se exigido, com chave de acesso.',
  },
];

export const FIELD_ERROR_MESSAGES = {
  brokerUrlRequired: 'Informe a URL do broker.',
  brokerUrlFormat: 'Use o formato http://endereço:porta, sem espaços (ex.: http://localhost:1026).',
  brokerUrlHttpsForCloud: 'Broker em nuvem precisa de https://, para a chave de acesso não trafegar aberta.',
  fiwareServiceFormat: 'Use só letras, números e _ (até 50 caracteres), ou deixe em branco.',
  fiwareServicePathFormat: 'Comece com / e use só letras, números e _ em cada nível (ex.: / ou /cidade/sensores).',
  apiKeyFormat: 'A chave de acesso não pode ter espaços nem quebras de linha.',
};

export const FIELD_INPUT_IDS: Record<ConfigField, string> = {
  brokerUrl: 'config-broker-url',
  fiwareService: 'config-fiware-service',
  fiwareServicePath: 'config-fiware-service-path',
  apiKey: 'config-api-key',
};

export const CONNECTION_MESSAGES: Record<Exclude<BrokerConnectionStatus, 'ok'>, string> = {
  invalid_url: 'URL inválida: confira se começa com http:// ou https:// e tem o endereço e a porta.',
  unreachable:
    'Broker inacessível: nada respondeu nesse endereço. Confira a URL, a porta e se o Orion está rodando (docker compose ps).',
  timeout: `O broker não respondeu em ${CONNECTION_TEST_TIMEOUT_SECONDS} segundos. Confira o endereço e se a rede permite o acesso.`,
  unauthorized: 'Credencial recusada pelo broker (HTTP {status}). Confira a chave de acesso.',
  unexpected_response:
    'O endereço respondeu, mas não parece um Orion Context Broker (HTTP {status}). Confira a URL e a porta.',
};

export const CONNECTION_OK_MESSAGE = 'Conexão funcionando: o broker respondeu e tem {count} tipo(s) de entidade.';

export const CONNECTION_REQUEST_FAILED_MESSAGE =
  'Não foi possível testar a conexão agora: a API do auditor não respondeu. Tente novamente.';
