import { ChangeDetectionStrategy, Component, computed, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { RouterLink } from '@angular/router';

import { ErrorStateComponent } from '../../shared/components/error-state/error-state.component';
import { AuditCreateResponse } from '../../shared/models/audit.models';
import {
  COMMAND_TEXT_MAX_LENGTH,
  CommandIntent,
  InterpretAuditResponse,
} from '../../shared/models/command.models';
import { NaturalLanguageApiService } from './natural-language-api.service';
import { describeNaturalLanguageError } from './natural-language-errors';

type InterpretState = 'idle' | 'loading' | 'interpreted' | 'error';
type ConfirmState = 'idle' | 'submitting' | 'submitted' | 'error';

/** Qual painel mostrar depois da interpretação (issue #21):
 * - `ready`: pronto para revisar e confirmar (único que tem botão de confirmar);
 * - `clarify`: pedido ambíguo — pergunta de esclarecimento + sugestões;
 * - `discovery`: lista de tipos do broker;
 * - `out-of-scope`: pedido fora do domínio FIWARE — nada é executado;
 * - `unavailable`: o modelo de linguagem não respondeu. */
type ResultView = 'ready' | 'clarify' | 'discovery' | 'out-of-scope' | 'unavailable';

type ConfidenceLevel = 'alta' | 'media' | 'baixa';

/** Confiança mínima para considerar que o modelo "entendeu" o comando —
 * abaixo disso a interpretação é tratada como ambígua mesmo que
 * `entity_type` não seja null (fase8.spec.md, seção 6). Mesmo limiar de
 * `MIN_CONFIDENCE_TO_CONFIRM` no backend (interpret_audit_command.py) —
 * repetido aqui como defesa extra, caso a tela receba uma resposta antiga. */
const MIN_CONFIDENCE_TO_CONFIRM = 0.5;
const HIGH_CONFIDENCE = 0.8;

const DEFAULT_CLARIFICATION_QUESTION =
  'Não ficou claro qual tipo de entidade você quer auditar. Qual destes tipos você quer auditar?';

const INTENT_LABELS: Record<CommandIntent, string> = {
  audit: 'Auditar entidades',
  discovery: 'Listar os tipos de entidade do broker',
  clarify: 'Pedido ambíguo — precisa de esclarecimento',
  out_of_scope: 'Fora do escopo (não é sobre entidades FIWARE)',
};

const CONFIDENCE_LABELS: Record<ConfidenceLevel, string> = {
  alta: 'alta',
  media: 'média',
  baixa: 'baixa',
};

/** Fase 8, seção 6 + issue #21 — Natural Language: caixa de comando que
 * mostra **como o sistema interpretou o pedido** (intenção, parâmetros e
 * confiança) e exige **confirmação humana explícita antes de executar**.
 * `POST /audits` (confirmAudit) só é chamado a partir de
 * `onConfirmClick()`, nunca de `onInterpret()` nem de
 * `onChooseSuggestion()`. */
@Component({
  selector: 'app-natural-language',
  standalone: true,
  imports: [FormsModule, RouterLink, ErrorStateComponent],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './natural-language.component.html',
  styleUrl: './natural-language.component.scss',
})
export class NaturalLanguageComponent {
  private readonly api = inject(NaturalLanguageApiService);

  protected readonly maxLength = COMMAND_TEXT_MAX_LENGTH;
  protected readonly examples: readonly string[] = [
    'audite os sensores de qualidade do ar',
    'verifique a entidade urn:ngsi-ld:Streetlight:001',
    'quais tipos de entidade existem no broker?',
  ];

  protected readonly commandText = signal('');
  protected readonly interpretState = signal<InterpretState>('idle');
  protected readonly interpretation = signal<InterpretAuditResponse | null>(null);
  protected readonly interpretErrorMessage = signal('');

  /** Rascunho editável da interpretação — a fonte de verdade para o
   * `POST /audits` final é SEMPRE este rascunho, nunca `interpretation()`
   * diretamente (fase8.spec.md, seção 6: "a interpretação é um rascunho,
   * nunca a fonte de verdade final"). */
  protected readonly editableEntityType = signal('');
  protected readonly editableEntityId = signal('');

  /** `true` depois que o usuário escolhe um tipo sugerido no painel de
   * esclarecimento — leva ao painel de revisão, que ainda exige o clique
   * de confirmação. */
  protected readonly clarifiedByUser = signal(false);

  protected readonly confirmState = signal<ConfirmState>('idle');
  protected readonly confirmErrorMessage = signal('');
  protected readonly createdRun = signal<AuditCreateResponse | null>(null);

  protected readonly isLoading = computed(() => this.interpretState() === 'loading');

  protected readonly intent = computed<CommandIntent | null>(() => {
    const result = this.interpretation();
    // Resposta sem `intent` (backend anterior à Fase 8) vale como "audit".
    return result === null ? null : (result.intent ?? 'audit');
  });

  protected readonly view = computed<ResultView | null>(() => {
    const result = this.interpretation();
    const intent = this.intent();
    if (result === null || intent === null) {
      return null;
    }
    if (result.interpreter_available === false) {
      return 'unavailable';
    }
    switch (intent) {
      case 'discovery':
        return 'discovery';
      case 'out_of_scope':
        return 'out-of-scope';
      case 'clarify':
        return this.clarifiedByUser() ? 'ready' : 'clarify';
      case 'audit': {
        const understood =
          result.entity_type !== null && result.confidence >= MIN_CONFIDENCE_TO_CONFIRM;
        return understood || this.clarifiedByUser() ? 'ready' : 'clarify';
      }
    }
  });

  protected readonly isDiscovery = computed(() => this.view() === 'discovery');

  /** Confirmação só é oferecida no painel `ready` — nunca para pedido
   * ambíguo, fora do escopo, descoberta ou interpretador indisponível
   * (fase8.spec.md, seção 6; issue #21). */
  protected readonly understoodEnough = computed(() => this.view() === 'ready');

  /** Além de estar no painel `ready`, o tipo não pode estar vazio (evita
   * disparar sem querer uma auditoria de TODAS as entidades) e não pode
   * haver um envio em andamento ou já concluído (evita runs duplicados). */
  protected readonly canConfirm = computed(
    () =>
      this.understoodEnough() &&
      this.editableEntityType().trim() !== '' &&
      this.confirmState() !== 'submitting' &&
      this.confirmState() !== 'submitted'
  );

  protected readonly intentLabel = computed(() => {
    const intent = this.intent();
    if (intent === null) {
      return '';
    }
    if (this.clarifiedByUser()) {
      return 'Auditar entidades (tipo escolhido por você)';
    }
    if (intent === 'audit' && this.view() === 'clarify') {
      return INTENT_LABELS.clarify;
    }
    return INTENT_LABELS[intent];
  });

  protected readonly confidencePercent = computed(() =>
    Math.round((this.interpretation()?.confidence ?? 0) * 100)
  );

  protected readonly confidenceLevel = computed<ConfidenceLevel>(() => {
    const confidence = this.interpretation()?.confidence ?? 0;
    if (confidence >= HIGH_CONFIDENCE) {
      return 'alta';
    }
    return confidence >= MIN_CONFIDENCE_TO_CONFIRM ? 'media' : 'baixa';
  });

  protected readonly confidenceLabel = computed(() => CONFIDENCE_LABELS[this.confidenceLevel()]);

  protected readonly clarificationQuestion = computed(
    () => this.interpretation()?.clarification_question || DEFAULT_CLARIFICATION_QUESTION
  );

  protected readonly suggestions = computed(() => this.interpretation()?.discovered_types ?? []);

  protected onInterpret(): void {
    const text = this.commandText().trim();
    if (!text || this.isLoading()) {
      return;
    }
    this.interpretation.set(null);
    this.clarifiedByUser.set(false);
    this.confirmState.set('idle');
    this.confirmErrorMessage.set('');
    this.createdRun.set(null);
    this.interpretErrorMessage.set('');
    this.interpretState.set('loading');
    this.api.interpret(text).subscribe({
      next: (result) => {
        this.interpretation.set(result);
        this.editableEntityType.set(result.entity_type ?? '');
        this.editableEntityId.set(result.entity_id ?? '');
        this.interpretState.set('interpreted');
      },
      error: (error: unknown) => {
        this.interpretErrorMessage.set(describeNaturalLanguageError(error, 'interpret'));
        this.interpretState.set('error');
      },
    });
  }

  /** Resposta à pergunta de esclarecimento: só preenche o rascunho e abre
   * o painel de revisão. NÃO chama a API — a auditoria continua exigindo o
   * clique em "Confirmar e iniciar auditoria". */
  protected onChooseSuggestion(entityType: string): void {
    if (this.view() !== 'clarify') {
      return;
    }
    this.editableEntityType.set(entityType);
    this.editableEntityId.set('');
    this.clarifiedByUser.set(true);
  }

  /** Só preenche a caixa de texto com um exemplo; não interpreta nem executa. */
  protected onUseExample(example: string): void {
    this.commandText.set(example);
  }

  protected onNewCommand(): void {
    this.commandText.set('');
    this.interpretation.set(null);
    this.clarifiedByUser.set(false);
    this.confirmState.set('idle');
    this.confirmErrorMessage.set('');
    this.createdRun.set(null);
    this.interpretErrorMessage.set('');
    this.interpretState.set('idle');
  }

  /** Único ponto do componente que dispara `POST /audits` — chamado
   * exclusivamente por um clique explícito do usuário no botão de
   * confirmação, nunca automaticamente. Usa os valores EDITADOS
   * (`editableEntityType`/`editableEntityId`), não os originais de
   * `interpretation()`. */
  protected onConfirmClick(): void {
    if (!this.canConfirm()) {
      return;
    }
    this.confirmState.set('submitting');
    this.confirmErrorMessage.set('');
    this.api
      .confirmAudit(this.editableEntityType().trim(), this.editableEntityId().trim() || null)
      .subscribe({
        next: (created) => {
          this.createdRun.set(created);
          this.confirmState.set('submitted');
        },
        error: (error: unknown) => {
          this.confirmErrorMessage.set(describeNaturalLanguageError(error, 'confirm'));
          this.confirmState.set('error');
        },
      });
  }
}
