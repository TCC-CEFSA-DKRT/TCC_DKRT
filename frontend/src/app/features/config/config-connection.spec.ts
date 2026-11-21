import { ConfigFormValues } from './config.interface';
import { connectionValuesKey, describeConnection } from './config-connection';

const VALUES: ConfigFormValues = {
  brokerKind: 'local',
  brokerUrl: 'http://localhost:1026',
  fiwareService: 'openiot',
  fiwareServicePath: '/',
  apiKey: '',
  hasSavedApiKey: false,
  ngsiVersion: 'v2',
};

describe('describeConnection', () => {
  it('tells how many entity types the broker has when the connection works', () => {
    const message = describeConnection({ status: 'ok', entity_types_count: 4, http_status: 200 });

    expect(message.tone).toBe('ok');
    expect(message.text).toContain('4 tipo(s) de entidade');
  });

  const failures = [
    ['invalid_url', 'URL inválida'],
    ['unreachable', 'Broker inacessível'],
    ['timeout', 'não respondeu em 5 segundos'],
    ['unauthorized', 'Credencial recusada'],
    ['unexpected_response', 'não parece um Orion Context Broker'],
  ] as const;

  for (const [status, expected] of failures) {
    it(`explains a ${status} failure in its own words`, () => {
      const message = describeConnection({ status, entity_types_count: null, http_status: 404 });

      expect(message.tone).toBe('error');
      expect(message.text).toContain(expected);
    });
  }

  it('shows the HTTP status the broker answered', () => {
    const message = describeConnection({ status: 'unauthorized', entity_types_count: null, http_status: 403 });

    expect(message.tone).toBe('error');
    expect(message.text).toContain('HTTP 403');
  });
});

describe('connectionValuesKey', () => {
  it('ignores surrounding spaces, so a retyped value still matches the tested one', () => {
    expect(connectionValuesKey({ ...VALUES, brokerUrl: ' http://localhost:1026 ' })).toBe(
      connectionValuesKey(VALUES)
    );
  });

  it('changes when any value that affects the connection changes', () => {
    const original = connectionValuesKey(VALUES);

    expect(connectionValuesKey({ ...VALUES, fiwareService: 'outro' })).not.toBe(original);
    expect(connectionValuesKey({ ...VALUES, brokerKind: 'cloud' })).not.toBe(original);
  });

  it('ignores the access key of a local broker, which is never sent', () => {
    expect(connectionValuesKey({ ...VALUES, apiKey: 'qualquer' })).toBe(connectionValuesKey(VALUES));
  });
});
