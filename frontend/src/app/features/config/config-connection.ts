import { BrokerConnectionTestResponse } from '../../shared/interfaces/config.interface';
import { CONNECTION_MESSAGES, CONNECTION_OK_MESSAGE } from './config.constants';
import { ConfigFormValues, ConnectionMessage } from './config.interface';

export function describeConnection(result: BrokerConnectionTestResponse): ConnectionMessage {
  if (result.status === 'ok') {
    return {
      tone: 'ok',
      text: CONNECTION_OK_MESSAGE.replace('{count}', String(result.entity_types_count ?? 0)),
    };
  }
  return {
    tone: 'error',
    text: CONNECTION_MESSAGES[result.status].replace('{status}', String(result.http_status ?? '?')),
  };
}

export function connectionValuesKey(values: ConfigFormValues): string {
  return JSON.stringify([
    values.brokerKind,
    values.brokerUrl.trim(),
    values.fiwareService.trim(),
    values.fiwareServicePath.trim() || '/',
    values.brokerKind === 'cloud' ? values.apiKey.trim() : '',
    values.ngsiVersion,
  ]);
}
