import { TestBed } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';
import { provideHttpClientTesting } from '@angular/common/http/testing';
import { provideRouter } from '@angular/router';

import { API_CONFIG, DEFAULT_API_CONFIG } from '../../../core/api-config';
import { SessionService } from '../../../core/session.service';
import { UserMenuComponent } from './user-menu.component';

describe('UserMenuComponent', () => {
  function render(loginEmail: string | null) {
    TestBed.configureTestingModule({
      imports: [UserMenuComponent],
      providers: [
        provideRouter([]),
        provideHttpClient(),
        provideHttpClientTesting(),
        { provide: API_CONFIG, useValue: DEFAULT_API_CONFIG },
      ],
    });
    TestBed.inject(SessionService).session.set({
      deployment_mode: 'saas',
      tenant: { fiware_service: 'cidade_a', fiware_service_path: '/' },
      login_email: loginEmail,
    });
    const fixture = TestBed.createComponent(UserMenuComponent);
    fixture.detectChanges();
    return fixture.nativeElement as HTMLElement;
  }

  it('shows the email of the person logged in, the tenant and the initial', () => {
    const element = render('ana@cidade.test');

    expect(element.querySelector('.user-menu__email')?.textContent).toBe('ana@cidade.test');
    expect(element.querySelector('.user-menu__tenant')?.textContent).toBe('cidade_a');
    expect(element.querySelector('.user-menu__avatar')?.textContent?.trim()).toBe('a');
  });

  it('falls back to the tenant when the session has no email', () => {
    const element = render(null);

    expect(element.querySelector('.user-menu__email')).toBeNull();
    expect(element.querySelector('.user-menu__tenant')?.textContent).toBe('cidade_a');
    expect(element.querySelector('.user-menu__avatar')?.textContent?.trim()).toBe('c');
  });
});
