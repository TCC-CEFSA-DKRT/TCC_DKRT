import { HttpErrorResponse } from '@angular/common/http';
import { TimeoutError } from 'rxjs';

import { COMMAND_TEXT_MAX_LENGTH } from '../../shared/models/command.models';

export type NaturalLanguageAction = 'interpret' | 'confirm';

/** Issue #21 — traduz qualquer falha HTTP em uma frase clara para o
 * usuário. Nunca devolve `error.message`, stack trace, código interno ou o
 * corpo cru da resposta: o critério de aceite exige "resposta clara, sem
 * erro técnico na tela". */
export function describeNaturalLanguageError(error: unknown, action: NaturalLanguageAction): string {
  if (error instanceof TimeoutError) {
    return action === 'interpret'
      ? 'A interpretação demorou mais do que o esperado. Tente novamente em instantes.'
      : 'O servidor demorou a responder. Confira em "Auditorias" se a auditoria foi criada antes de tentar de novo.';
  }

  const status = error instanceof HttpErrorResponse ? error.status : -1;

  if (status === 0) {
    return 'Não foi possível conectar ao servidor do auditor. Verifique se a API está em execução e tente novamente.';
  }
  if (status === 401) {
    return 'Sua sessão expirou. Entre novamente para continuar.';
  }
  if (status === 422) {
    return action === 'interpret'
      ? `Não consegui processar esse texto. Escreva um pedido com até ${COMMAND_TEXT_MAX_LENGTH} caracteres.`
      : 'Os parâmetros informados não são válidos. Revise o tipo e o ID da entidade e tente novamente.';
  }
  return action === 'interpret'
    ? 'O serviço de interpretação está indisponível no momento. Tente novamente em instantes.'
    : 'Não foi possível iniciar a auditoria agora. Tente novamente em instantes.';
}
