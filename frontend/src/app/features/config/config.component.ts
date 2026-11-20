import { DOCUMENT } from '@angular/common';
import { HttpErrorResponse } from '@angular/common/http';
import { ChangeDetectionStrategy, Component, computed, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { Router } from '@angular/router';

import { HOME_PATH } from '../../core/session.constants';
import { SessionService } from '../../core/session.service';
import { ErrorStateComponent } from '../../shared/components/error-state/error-state.component';
import { LoadingSkeletonComponent } from '../../shared/components/loading-skeleton/loading-skeleton.component';
import { SplitPanelComponent } from '../../shared/components/split-panel/split-panel.component';
import {
  BrokerConfigResponse,
  BrokerConnectionFailedDetail,
  BrokerConnectionTestResponse,
  BrokerKind,
  NgsiVersion,
} from '../../shared/interfaces/config.interface';
import { ConfigApiService } from './config-api.service';
import { connectionValuesKey, describeConnection } from './config-connection';
import { hasFieldErrors, validateConfigForm } from './config-validation';
import {
  BROKER_KIND_OPTIONS,
  CONNECTION_REQUEST_FAILED_MESSAGE,
  FIELD_INPUT_IDS,
  NGSI_VERSION_OPTIONS,
} from './config.constants';
import {
  ConfigField,
  ConfigFormValues,
  LoadState,
  SaveState,
  TestState,
  TestedConnection,
} from './config.interface';

const EMPTY_VALUES: ConfigFormValues = {
  brokerKind: 'local',
  brokerUrl: '',
  fiwareService: '',
  fiwareServicePath: '/',
  apiKey: '',
  hasSavedApiKey: false,
  ngsiVersion: 'v2',
};

@Component({
  selector: 'app-config',
  standalone: true,
  imports: [FormsModule, ErrorStateComponent, LoadingSkeletonComponent, SplitPanelComponent],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './config.component.html',
  styleUrl: './config.component.scss',
})
export class ConfigComponent {
  private readonly api = inject(ConfigApiService);
  private readonly session = inject(SessionService);
  private readonly router = inject(Router);
  private readonly document = inject(DOCUMENT);

  protected readonly kindOptions = BROKER_KIND_OPTIONS;
  protected readonly ngsiVersionOptions = NGSI_VERSION_OPTIONS;
  protected readonly inputIds = FIELD_INPUT_IDS;
  protected readonly requestFailedMessage = CONNECTION_REQUEST_FAILED_MESSAGE;

  protected readonly loadState = signal<LoadState>('loading');
  protected readonly saveState = signal<SaveState>('idle');
  protected readonly testState = signal<TestState>('idle');
  protected readonly values = signal<ConfigFormValues>(EMPTY_VALUES);
  protected readonly attempted = signal(false);
  protected readonly savedConfig = signal<BrokerConfigResponse | null>(null);
  protected readonly canGoBack = signal(false);

  private readonly defaultLocalUrl = signal('');
  private readonly testedConnection = signal<TestedConnection | null>(null);

  protected readonly fieldErrors = computed(() =>
    this.attempted() ? validateConfigForm(this.values()) : {}
  );

  protected readonly connection = computed(() => {
    const tested = this.testedConnection();
    return tested && tested.valuesKey === connectionValuesKey(this.values()) ? tested.result : null;
  });

  protected readonly connectionMessage = computed(() => {
    const result = this.connection();
    return result ? describeConnection(result) : null;
  });

  protected readonly busy = computed(
    () => this.testState() === 'testing' || this.saveState() === 'saving'
  );

  constructor() {
    this.fetchConfig();
  }

  protected fetchConfig(): void {
    this.loadState.set('loading');
    this.api.load().subscribe({
      next: (cfg) => {
        this.defaultLocalUrl.set(cfg.default_local_broker_url || cfg.broker_url);
        this.values.set({
          brokerKind: cfg.broker_kind ?? 'local',
          brokerUrl: cfg.broker_url,
          fiwareService: cfg.fiware_service,
          fiwareServicePath: cfg.fiware_service_path,
          apiKey: '',
          hasSavedApiKey: cfg.has_api_key ?? false,
          ngsiVersion: cfg.ngsi_version ?? 'v2',
        });
        this.canGoBack.set(cfg.configured);
        this.loadState.set('ready');
      },
      error: () => this.loadState.set('error'),
    });
  }

  protected setField(field: ConfigField, value: string): void {
    this.values.update((current) => ({ ...current, [field]: value }));
    this.resetConfirmation();
  }

  protected setKind(kind: BrokerKind): void {
    this.values.update((current) => ({
      ...current,
      brokerKind: kind,
      brokerUrl: this.urlForKind(kind, current.brokerUrl.trim()),
    }));
    this.resetConfirmation();
  }

  protected setNgsiVersion(version: NgsiVersion): void {
    this.values.update((current) => ({ ...current, ngsiVersion: version }));
    this.resetConfirmation();
  }

  protected onTest(): void {
    if (!this.formIsValid()) {
      return;
    }
    const values = this.values();
    this.testState.set('testing');
    this.api.testConnection(values).subscribe({
      next: (result) => {
        this.rememberConnection(values, result);
        this.testState.set('done');
      },
      error: () => this.testState.set('error'),
    });
  }

  protected onSave(): void {
    if (this.formIsValid()) {
      this.save(false);
    }
  }

  protected onSaveAnyway(): void {
    this.save(true);
  }

  protected onFixConfig(): void {
    this.saveState.set('idle');
    this.focusField('brokerUrl');
  }

  protected connectionMessageFor(result: BrokerConnectionTestResponse): string {
    return describeConnection(result).text;
  }

  protected onBack(): void {
    this.router.navigateByUrl(HOME_PATH);
  }

  protected onContinue(): void {
    this.router.navigateByUrl('/dashboard');
  }

  private save(saveWithoutConnection: boolean): void {
    const values = this.values();
    this.saveState.set('saving');
    this.api.save(values, saveWithoutConnection).subscribe({
      next: (cfg) => this.handleSaved(cfg),
      error: (error: HttpErrorResponse) => this.handleSaveError(values, error),
    });
  }

  private handleSaved(cfg: BrokerConfigResponse): void {
    const current = this.session.session();
    this.session.session.set({
      deployment_mode: current?.deployment_mode ?? 'selfhosted',
      tenant: { fiware_service: cfg.fiware_service, fiware_service_path: cfg.fiware_service_path },
    });
    this.values.update((values) => ({ ...values, apiKey: '', hasSavedApiKey: cfg.has_api_key }));
    this.savedConfig.set(cfg);
    this.canGoBack.set(true);
    this.saveState.set('saved');
  }

  private handleSaveError(values: ConfigFormValues, error: HttpErrorResponse): void {
    const detail = error.error?.detail as BrokerConnectionFailedDetail | undefined;
    if (error.status === 409 && detail?.connection) {
      this.rememberConnection(values, detail.connection);
      this.saveState.set('needs-confirmation');
      return;
    }
    this.saveState.set('error');
  }

  private rememberConnection(values: ConfigFormValues, result: BrokerConnectionTestResponse): void {
    this.testedConnection.set({ valuesKey: connectionValuesKey(values), result });
  }

  private formIsValid(): boolean {
    this.attempted.set(true);
    const errors = validateConfigForm(this.values());
    if (!hasFieldErrors(errors)) {
      return true;
    }
    this.focusField(Object.keys(errors)[0] as ConfigField);
    return false;
  }

  private focusField(field: ConfigField): void {
    this.document.getElementById(this.inputIds[field])?.focus();
  }

  private resetConfirmation(): void {
    if (this.saveState() === 'needs-confirmation' || this.saveState() === 'saved') {
      this.saveState.set('idle');
    }
  }

  private urlForKind(kind: BrokerKind, url: string): string {
    if (kind === 'local' && (!url || url.startsWith('https://'))) {
      return this.defaultLocalUrl();
    }
    if (kind === 'cloud' && (!url || url === this.defaultLocalUrl())) {
      return 'https://';
    }
    return url;
  }
}
