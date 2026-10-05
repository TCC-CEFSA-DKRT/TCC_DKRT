import { ChangeDetectionStrategy, Component, inject, signal } from '@angular/core';
import { DatePipe } from '@angular/common';
import { FormsModule } from '@angular/forms';

import { EmptyStateComponent } from '../../shared/components/empty-state/empty-state.component';
import { ErrorStateComponent } from '../../shared/components/error-state/error-state.component';
import { LoadingSkeletonComponent } from '../../shared/components/loading-skeleton/loading-skeleton.component';
import { CatalogModelResponse, CatalogStatusResponse } from '../../shared/models/catalog.models';
import { CatalogApiService } from './catalog-api.service';

type ViewState = 'loading' | 'loaded' | 'never_synced' | 'error';
type ModelsState = 'idle' | 'loading' | 'loaded' | 'empty' | 'error';
type SchemaState = 'loading' | 'loaded' | 'error';

const MODELS_PAGE_SIZE = 20;

interface ExpandedSchema {
  key: string;
  state: SchemaState;
  content?: unknown;
  source?: string;
  fetchedAt?: string;
  error?: string;
}

function modelKey(subject: string, modelName: string): string {
  return `${subject}::${modelName}`;
}

/** Fase 8, seção 7 — Catalog: quando o catálogo foi sincronizado pela
 * última vez, e — se a última tentativa falhou — o catálogo local (última
 * sincronização bem-sucedida) com aviso explícito, nunca escondendo a
 * falha nem servindo dado stale como se fosse atual.
 *
 * Follow-up pos-Fase 8: além do status agregado, a lista navegável dos
 * modelos indexados (busca por nome/subject, paginada — `GET
 * /catalog/models`) e o conteúdo de cada um sob demanda, expandido inline
 * na própria linha (`GET /catalog/models/{model_name}/schema`) — antes
 * disso não havia nenhum jeito de ver *quais* modelos o catálogo continha
 * nem seu conteúdo, só a contagem. A lista só é carregada depois que o
 * status confirma que existe ao menos uma sincronização bem-sucedida
 * (`state() === 'loaded'`) — sem isso `GET /catalog/models` devolveria
 * uma lista vazia sem explicação (o catálogo em si é local e sempre
 * "funciona", mas mostrar uma tabela vazia sem contexto seria confuso).
 */
@Component({
  selector: 'app-catalog',
  standalone: true,
  imports: [DatePipe, FormsModule, EmptyStateComponent, ErrorStateComponent, LoadingSkeletonComponent],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './catalog.component.html',
  styleUrl: './catalog.component.scss',
})
export class CatalogComponent {
  private readonly api = inject(CatalogApiService);

  protected readonly state = signal<ViewState>('loading');
  protected readonly status = signal<CatalogStatusResponse | null>(null);

  protected readonly modelsState = signal<ModelsState>('idle');
  protected readonly models = signal<CatalogModelResponse[]>([]);
  protected readonly modelsTotal = signal(0);
  protected readonly modelsPage = signal(1);
  protected readonly modelsHasNext = signal(false);
  protected readonly modelsFilters = signal<{ subject?: string; q?: string }>({});

  /** Rascunho do formulário de busca — distinto de `modelsFilters()` (o
   * filtro efetivamente aplicado), mesmo padrão de AuditRunsComponent. */
  protected modelSearchInput = '';
  protected modelSubjectInput = '';

  protected readonly expandedSchemas = signal<Map<string, ExpandedSchema>>(new Map());

  constructor() {
    this.load();
  }

  protected load(): void {
    this.state.set('loading');
    this.api.getStatus().subscribe({
      next: (status) => {
        this.status.set(status);
        const nextState: ViewState = status.last_synced_at === null ? 'never_synced' : 'loaded';
        this.state.set(nextState);
        if (nextState === 'loaded') {
          this.loadModels(1);
        }
      },
      error: () => this.state.set('error'),
    });
  }

  protected loadModels(page: number): void {
    this.modelsState.set('loading');
    const filters = this.modelsFilters();
    this.api
      .listModels({ ...filters, page, page_size: MODELS_PAGE_SIZE })
      .subscribe({
        next: (result) => {
          this.models.set(result.items);
          this.modelsTotal.set(result.total);
          this.modelsPage.set(result.page);
          this.modelsHasNext.set(result.has_next);
          this.modelsState.set(result.items.length === 0 ? 'empty' : 'loaded');
        },
        error: () => this.modelsState.set('error'),
      });
  }

  protected applyModelFilters(): void {
    this.modelsFilters.set({
      subject: this.modelSubjectInput.trim() || undefined,
      q: this.modelSearchInput.trim() || undefined,
    });
    this.expandedSchemas.set(new Map());
    this.loadModels(1);
  }

  protected nextModelsPage(): void {
    if (this.modelsHasNext()) {
      this.loadModels(this.modelsPage() + 1);
    }
  }

  protected previousModelsPage(): void {
    if (this.modelsPage() > 1) {
      this.loadModels(this.modelsPage() - 1);
    }
  }

  protected toggleSchema(model: CatalogModelResponse): void {
    const key = modelKey(model.subject, model.model_name);
    const current = new Map(this.expandedSchemas());

    if (current.has(key)) {
      current.delete(key);
      this.expandedSchemas.set(current);
      return;
    }

    current.set(key, { key, state: 'loading' });
    this.expandedSchemas.set(current);

    this.api.getModelSchema(model.subject, model.model_name).subscribe({
      next: (schema) => {
        const updated = new Map(this.expandedSchemas());
        updated.set(key, {
          key,
          state: 'loaded',
          content: schema.content,
          source: schema.source,
          fetchedAt: schema.fetched_at,
        });
        this.expandedSchemas.set(updated);
      },
      error: (err) => {
        const updated = new Map(this.expandedSchemas());
        updated.set(key, {
          key,
          state: 'error',
          error: err?.error?.detail ?? 'Não foi possível carregar o schema.',
        });
        this.expandedSchemas.set(updated);
      },
    });
  }

  protected isExpanded(model: CatalogModelResponse): boolean {
    return this.expandedSchemas().has(modelKey(model.subject, model.model_name));
  }

  protected schemaFor(model: CatalogModelResponse): ExpandedSchema | undefined {
    return this.expandedSchemas().get(modelKey(model.subject, model.model_name));
  }

  protected formatSchema(content: unknown): string {
    return JSON.stringify(content, null, 2);
  }
}
