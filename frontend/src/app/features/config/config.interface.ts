import { BrokerConnectionTestResponse, BrokerKind } from '../../shared/interfaces/config.interface';

export type LoadState = 'loading' | 'ready' | 'error';

export type SaveState = 'idle' | 'saving' | 'needs-confirmation' | 'saved' | 'error';

export type TestState = 'idle' | 'testing' | 'done' | 'error';

export type ConfigField = 'brokerUrl' | 'fiwareService' | 'fiwareServicePath' | 'apiKey';

export type ConfigFieldErrors = Partial<Record<ConfigField, string>>;

export interface ConfigFormValues {
  brokerKind: BrokerKind;
  brokerUrl: string;
  fiwareService: string;
  fiwareServicePath: string;
  apiKey: string;
  hasSavedApiKey: boolean;
}

export interface ConnectionMessage {
  tone: 'ok' | 'error';
  text: string;
}

export interface TestedConnection {
  valuesKey: string;
  result: BrokerConnectionTestResponse;
}

export interface BrokerKindOption {
  value: BrokerKind;
  title: string;
  description: string;
}
