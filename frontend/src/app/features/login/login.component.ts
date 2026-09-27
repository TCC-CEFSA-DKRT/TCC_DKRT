import { ChangeDetectionStrategy, Component, inject, signal } from '@angular/core';
import { HttpErrorResponse } from '@angular/common/http';
import { FormsModule } from '@angular/forms';
import { Router } from '@angular/router';

import { SplitPanelComponent } from '../../shared/components/split-panel/split-panel.component';
import { SessionService } from '../../core/session.service';

type LoginState = 'idle' | 'submitting' | 'error';

@Component({
  selector: 'app-login',
  standalone: true,
  imports: [FormsModule, SplitPanelComponent],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './login.component.html',
  styleUrl: './login.component.scss',
})
export class LoginComponent {
  private readonly session = inject(SessionService);
  private readonly router = inject(Router);

  protected email = '';
  protected password = '';
  protected readonly state = signal<LoginState>('idle');
  protected readonly errorMessage = signal('');

  protected onSubmit(): void {
    if (this.state() === 'submitting') {
      return;
    }
    this.state.set('submitting');
    this.session.login(this.email, this.password).subscribe({
      next: () => this.router.navigateByUrl('/dashboard'),
      error: (err: HttpErrorResponse) => {
        this.errorMessage.set(
          err.status === 401
            ? 'Email ou senha inválidos.'
            : 'Não foi possível entrar. Tente novamente.'
        );
        this.state.set('error');
      },
    });
  }
}
