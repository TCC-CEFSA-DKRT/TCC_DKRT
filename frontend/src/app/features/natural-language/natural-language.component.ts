import { ChangeDetectionStrategy, Component, computed, inject, signal } from '@angular/core';
import { DecimalPipe } from '@angular/common';
import { FormsModule } from '@angular/forms';

import { ErrorStateComponent } from '../../shared/components/error-state/error-state.component';
import { AuditCreateResponse } from '../../shared/models/audit.models';
import { InterpretAuditResponse } from '../../shared/models/command.models';
import { NaturalLanguageApiService } from './natural-language-api.service';

type InterpretState = 'idle' | 'loading' | 'interpreted' | 'error';
type ConfirmState = 'idle' | 'submitting' | 'submitted' | 'error';

/** Confiança mínima para considerar que o modelo "entendeu" o comando —
 * abaixo disso a interpretação é tratada como vazia mesmo que
 * `entity_type` não seja null (fase8.spec.md, seção 6, mesmo limiar
 * documentado no prompt de `command_interpretation.md`, Fase 8 seção
 * 0.3: "confiança < 0.5" para comandos vagos/ambíguos). */
const MIN_CONFIDENCE_TO_CONFIRM = 0.5;

/** Fase 8, seção 6 — Natural Language: caixa de comando com **confirmação
 * humana obrigatória antes de executar** — o único requisito de segurança
 * de UX desta fase (seção 9). `POST /audits` (confirmAudit) só é chamado
 * a partir de `onConfirmClick()`, nunca de `onInterpret()`. */
@Component({
  selector: 'app-natural-language',
  standalone: true,
  imports: [DecimalPipe, FormsModule, ErrorStateComponent],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './natural-language.component.html',
  styleUrl: './natural-language.component.scss',
})
export class NaturalLanguageComponent {
  private readonly api = inject(NaturalLanguageApiService);

  protected commandText = '';
  protected readonly interpretState = signal<InterpretState>('idle');
  protected readonly interpretation = signal<InterpretAuditResponse | null>(null);

  /** Rascunho editável da interpretação — a fonte de verdade para o
   * `POST /audits` final é SEMPRE este rascunho, nunca `interpretation()`
   * diretamente (fase8.spec.md, seção 6: "a interpretação é um rascunho,
   * nunca a fonte de verdade final"). */
  protected editableEntityType = '';
  protected editableEntityId = '';

  protected readonly confirmState = signal<ConfirmState>('idle');
  protected readonly createdRun = signal<AuditCreateResponse | null>(null);

  /** Confirmação só é oferecida quando a interpretação de fato identificou
   * um tipo com confiança razoável — nunca para uma interpretação vazia
   * (fase8.spec.md, seção 6, segundo caso de teste). */
  protected readonly understoodEnough = computed(() => {
    const result = this.interpretation();
    return result !== null && result.entity_type !== null && result.confidence >= MIN_CONFIDENCE_TO_CONFIRM;
  });

  protected onInterpret(): void {
    const text = this.commandText.trim();
    if (!text) {
      return;
    }
    this.interpretState.set('loading');
    this.confirmState.set('idle');
    this.createdRun.set(null);
    this.api.interpret(text).subscribe({
      next: (result) => {
        this.interpretation.set(result);
        this.editableEntityType = result.entity_type ?? '';
        this.editableEntityId = result.entity_id ?? '';
        this.interpretState.set('interpreted');
      },
      error: () => this.interpretState.set('error'),
    });
  }

  /** Único ponto do componente que dispara `POST /audits` — chamado
   * exclusivamente por um clique explícito do usuário no botão de
   * confirmação, nunca automaticamente a partir de `onInterpret()`. Usa
   * os valores EDITADOS (`editableEntityType`/`editableEntityId`), não os
   * originais de `interpretation()`. */
  protected onConfirmClick(): void {
    if (!this.understoodEnough()) {
      return;
    }
    this.confirmState.set('submitting');
    this.api
      .confirmAudit(this.editableEntityType.trim() || null, this.editableEntityId.trim() || null)
      .subscribe({
        next: (created) => {
          this.createdRun.set(created);
          this.confirmState.set('submitted');
        },
        error: () => this.confirmState.set('error'),
      });
  }
}
