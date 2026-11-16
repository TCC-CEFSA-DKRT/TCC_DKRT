import { FIELD_ERROR_MESSAGES } from './config.constants';
import { ConfigFormValues } from './config.interface';
import { hasFieldErrors, validateConfigForm } from './config-validation';

const VALID: ConfigFormValues = {
  brokerKind: 'local',
  brokerUrl: 'http://localhost:1026',
  fiwareService: 'openiot',
  fiwareServicePath: '/',
  apiKey: '',
  hasSavedApiKey: false,
};

describe('validateConfigForm', () => {
  it('accepts a local Docker broker with an empty Fiware-Service', () => {
    expect(validateConfigForm({ ...VALID, fiwareService: '' })).toEqual({});
  });

  it('asks for the broker URL when it is empty', () => {
    expect(validateConfigForm({ ...VALID, brokerUrl: '  ' }).brokerUrl).toBe(
      FIELD_ERROR_MESSAGES.brokerUrlRequired
    );
  });

  it('rejects a URL without http:// or https://', () => {
    expect(validateConfigForm({ ...VALID, brokerUrl: 'localhost:1026' }).brokerUrl).toBe(
      FIELD_ERROR_MESSAGES.brokerUrlFormat
    );
  });

  it('requires https:// for a cloud broker', () => {
    const errors = validateConfigForm({
      ...VALID,
      brokerKind: 'cloud',
      brokerUrl: 'http://orion.example.com',
    });

    expect(errors.brokerUrl).toBe(FIELD_ERROR_MESSAGES.brokerUrlHttpsForCloud);
  });

  it('rejects a Fiware-Service with characters Orion does not accept', () => {
    expect(validateConfigForm({ ...VALID, fiwareService: 'open iot' }).fiwareService).toBe(
      FIELD_ERROR_MESSAGES.fiwareServiceFormat
    );
  });

  it('accepts a Fiware-Service with exactly 50 characters and rejects 51', () => {
    expect(validateConfigForm({ ...VALID, fiwareService: 'a'.repeat(50) })).toEqual({});
    expect(validateConfigForm({ ...VALID, fiwareService: 'a'.repeat(51) }).fiwareService).toBe(
      FIELD_ERROR_MESSAGES.fiwareServiceFormat
    );
  });

  it('rejects a Fiware-ServicePath that does not start with a slash', () => {
    expect(validateConfigForm({ ...VALID, fiwareServicePath: 'cidade' }).fiwareServicePath).toBe(
      FIELD_ERROR_MESSAGES.fiwareServicePathFormat
    );
  });

  it('accepts a nested Fiware-ServicePath and treats an empty one as the root', () => {
    expect(validateConfigForm({ ...VALID, fiwareServicePath: '/cidade/sensores' })).toEqual({});
    expect(validateConfigForm({ ...VALID, fiwareServicePath: '' })).toEqual({});
  });

  it('rejects a cloud access key with spaces inside', () => {
    const errors = validateConfigForm({
      ...VALID,
      brokerKind: 'cloud',
      brokerUrl: 'https://orion.example.com',
      apiKey: 'abc def',
    });

    expect(errors.apiKey).toBe(FIELD_ERROR_MESSAGES.apiKeyFormat);
  });

  it('reports several invalid fields at once', () => {
    const errors = validateConfigForm({ ...VALID, brokerUrl: '', fiwareServicePath: 'x' });

    expect(Object.keys(errors).sort()).toEqual(['brokerUrl', 'fiwareServicePath']);
    expect(hasFieldErrors(errors)).toBeTrue();
    expect(hasFieldErrors({})).toBeFalse();
  });
});
