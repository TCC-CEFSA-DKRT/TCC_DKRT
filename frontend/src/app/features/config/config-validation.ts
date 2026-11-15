import {
  API_KEY_PATTERN,
  BROKER_URL_PATTERN,
  FIELD_ERROR_MESSAGES,
  FIWARE_SERVICE_PATH_PATTERN,
  FIWARE_SERVICE_PATTERN,
} from './config.constants';
import { ConfigFieldErrors, ConfigFormValues } from './config.interface';

function brokerUrlError(values: ConfigFormValues): string | undefined {
  const url = values.brokerUrl.trim();
  if (!url) {
    return FIELD_ERROR_MESSAGES.brokerUrlRequired;
  }
  if (!BROKER_URL_PATTERN.test(url)) {
    return FIELD_ERROR_MESSAGES.brokerUrlFormat;
  }
  if (values.brokerKind === 'cloud' && !url.startsWith('https://')) {
    return FIELD_ERROR_MESSAGES.brokerUrlHttpsForCloud;
  }
  return undefined;
}

export function validateConfigForm(values: ConfigFormValues): ConfigFieldErrors {
  const errors: ConfigFieldErrors = {};
  const brokerUrl = brokerUrlError(values);
  if (brokerUrl) {
    errors.brokerUrl = brokerUrl;
  }
  if (!FIWARE_SERVICE_PATTERN.test(values.fiwareService.trim())) {
    errors.fiwareService = FIELD_ERROR_MESSAGES.fiwareServiceFormat;
  }
  if (!FIWARE_SERVICE_PATH_PATTERN.test(values.fiwareServicePath.trim() || '/')) {
    errors.fiwareServicePath = FIELD_ERROR_MESSAGES.fiwareServicePathFormat;
  }
  if (values.brokerKind === 'cloud' && !API_KEY_PATTERN.test(values.apiKey.trim())) {
    errors.apiKey = FIELD_ERROR_MESSAGES.apiKeyFormat;
  }
  return errors;
}

export function hasFieldErrors(errors: ConfigFieldErrors): boolean {
  return Object.keys(errors).length > 0;
}
