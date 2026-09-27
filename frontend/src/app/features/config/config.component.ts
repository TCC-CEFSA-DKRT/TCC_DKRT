import { ChangeDetectionStrategy, Component, inject, signal } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { FormsModule } from '@angular/forms';
import { Router } from '@angular/router';

import { ErrorStateComponent } from '../../shared/components/error-state/error-state.component';
import { LoadingSkeletonComponent } from '../../shared/components/loading-skeleton/loading-skeleton.component';
import { SplitPanelComponent } from '../../shared/components/split-panel/split-panel.component';
import { BrokerConfigResponse, EntityTypesResponse } from '../../shared/models/config.models';
import { API_CONFIG } from '../../core/api-config';
import { SessionService } from '../../core/session.service';

type LoadState = 'loading' | 'ready' | 'error';
type SaveState = 'idle' | 'saving' | 'error';
type ConnectionTest = { status: 'ok'; count: number } | { status: 'warn' } | null;

@Component({
  selector: 'app-config',
  standalone: true,
  imports: [FormsModule, ErrorStateComponent, LoadingSkeletonComponent, SplitPanelComponent],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './config.component.html',
  styleUrl: './config.component.scss',
})
export class ConfigComponent {
  private readonly http = inject(HttpClient);
  private readonly config = inject(API_CONFIG);
  private readonly session = inject(SessionService);
  private readonly router = inject(Router);

  protected readonly loadState = signal<LoadState>('loading');
  protected readonly saveState = signal<SaveState>('idle');
  protected readonly connectionTest = signal<ConnectionTest>(null);
  protected readonly saved = signal(false);

  protected brokerUrl = '';
  protected fiwareService = '';
  protected fiwareServicePath = '/';

  constructor() {
    this.fetchConfig();
  }

  protected fetchConfig(): void {
    this.loadState.set('loading');
    this.http.get<BrokerConfigResponse>(`${this.config.baseUrl}/config`).subscribe({
      next: (cfg) => {
        this.brokerUrl = cfg.broker_url;
        this.fiwareService = cfg.fiware_service;
        this.fiwareServicePath = cfg.fiware_service_path;
        this.loadState.set('ready');
      },
      error: () => this.loadState.set('error'),
    });
  }

  protected onSave(): void {
    this.saveState.set('saving');
    this.connectionTest.set(null);
    const body = {
      broker_url: this.brokerUrl.trim(),
      fiware_service: this.fiwareService.trim(),
      fiware_service_path: this.fiwareServicePath.trim() || '/',
    };
    this.http.put<BrokerConfigResponse>(`${this.config.baseUrl}/config`, body).subscribe({
      next: (cfg) => {
        const current = this.session.session();
        this.session.session.set({
          deployment_mode: current?.deployment_mode ?? 'selfhosted',
          tenant: { fiware_service: cfg.fiware_service, fiware_service_path: cfg.fiware_service_path },
        });
        this.saveState.set('idle');
        this.saved.set(true);
        this.testConnection();
      },
      error: () => this.saveState.set('error'),
    });
  }

  private testConnection(): void {
    this.http.get<EntityTypesResponse>(`${this.config.baseUrl}/entity-types`).subscribe({
      next: (res) =>
        this.connectionTest.set(
          res.broker_reachable ? { status: 'ok', count: res.types.length } : { status: 'warn' }
        ),
      error: () => this.connectionTest.set({ status: 'warn' }),
    });
  }

  protected onContinue(): void {
    this.router.navigateByUrl('/dashboard');
  }
}
