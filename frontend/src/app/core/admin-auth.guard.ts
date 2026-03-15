import { inject } from '@angular/core';
import { CanActivateFn, Router } from '@angular/router';
import { isAdminHostAllowed } from './admin-host-policy';
import { SessionService } from './session.service';

export const adminAuthGuard: CanActivateFn = () => {
  const session = inject(SessionService);
  const router = inject(Router);

  if (!isAdminHostAllowed()) {
    return router.createUrlTree(['/sign-in']);
  }

  if (session.hasAdminSession()) {
    return true;
  }

  return router.createUrlTree(['/admin/sign-in']);
};

export const adminSignInRedirectGuard: CanActivateFn = () => {
  const session = inject(SessionService);
  const router = inject(Router);

  if (!isAdminHostAllowed()) {
    return router.createUrlTree(['/sign-in']);
  }

  if (session.hasAdminSession()) {
    return router.createUrlTree(['/admin/workspaces']);
  }

  return true;
};
