import { inject } from '@angular/core';
import { CanActivateFn, Router } from '@angular/router';
import { SessionService } from './session.service';

export const clientAuthGuard: CanActivateFn = () => {
  const session = inject(SessionService);
  const router = inject(Router);

  if (session.hasAdminSession()) {
    return router.createUrlTree(['/admin/workspaces']);
  }

  if (session.hasClientSession()) {
    return true;
  }

  return router.createUrlTree(['/sign-in']);
};

export const clientSignInRedirectGuard: CanActivateFn = () => {
  const session = inject(SessionService);
  const router = inject(Router);

  if (session.hasAdminSession()) {
    return router.createUrlTree(['/admin/workspaces']);
  }

  if (session.hasClientSession()) {
    return router.createUrlTree(['/']);
  }

  return true;
};
