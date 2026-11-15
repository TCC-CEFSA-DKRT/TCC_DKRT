import { DOCUMENT } from '@angular/common';
import { HttpErrorResponse } from '@angular/common/http';
import { ChangeDetectionStrategy, Component, computed, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute, Router } from '@angular/router';

import { safeReturnUrl } from '../../core/return-url';
import {
  LOGIN_REASON_PARAM,
  RETURN_URL_PARAM,
  SESSION_EXPIRED_REASON,
} from '../../core/session.constants';
import { SessionService } from '../../core/session.service';
import { SplitPanelComponent } from '../../shared/components/split-panel/split-panel.component';
import { LOGIN_INPUT_IDS, LOGIN_MESSAGES } from './login.constants';
import { LoginField, LoginState } from './login.interface';
import { validateLogin } from './login-validation';

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
  private readonly route = inject(ActivatedRoute);
  private readonly document = inject(DOCUMENT);

  protected readonly inputIds = LOGIN_INPUT_IDS;
  protected readonly email = signal('');
  protected readonly password = signal('');
  protected readonly state = signal<LoginState>('idle');
  protected readonly errorMessage = signal('');
  protected readonly attempted = signal(false);
  protected readonly sessionExpired =
    this.route.snapshot.queryParamMap.get(LOGIN_REASON_PARAM) === SESSION_EXPIRED_REASON;
  protected readonly expiredMessage = LOGIN_MESSAGES.sessionExpired;

  protected readonly fieldErrors = computed(() =>
    this.attempted() ? validateLogin(this.email(), this.password()) : {}
  );

  protected onSubmit(): void {
    if (this.state() === 'submitting') {
      return;
    }
    this.attempted.set(true);
    const errors = validateLogin(this.email(), this.password());
    const firstInvalid = Object.keys(errors)[0] as LoginField | undefined;
    if (firstInvalid) {
      this.document.getElementById(this.inputIds[firstInvalid])?.focus();
      return;
    }
    this.state.set('submitting');
    this.session.login(this.email().trim(), this.password()).subscribe({
      next: () =>
        this.router.navigateByUrl(
          safeReturnUrl(this.route.snapshot.queryParamMap.get(RETURN_URL_PARAM))
        ),
      error: (err: HttpErrorResponse) => {
        this.errorMessage.set(
          err.status === 401 ? LOGIN_MESSAGES.invalidCredentials : LOGIN_MESSAGES.unavailable
        );
        this.state.set('error');
      },
    });
  }
}
