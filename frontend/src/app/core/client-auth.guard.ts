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

export const clientSignInRedirectGuard: CanActivateFn = (route) => {
  const session = inject(SessionService);
  const router = inject(Router);

  if (session.hasAdminSession()) {
    return router.createUrlTree(['/admin/workspaces']);
  }

  if (session.hasClientSession()) {
    const requestedOperation = route.queryParamMap.get('operation');
    if (
      requestedOperation === 'font_fix' ||
      requestedOperation === 'compress' ||
      requestedOperation === 'merge' ||
      requestedOperation === 'split'
    ) {
      return router.createUrlTree(['/portal'], { queryParams: { operation: requestedOperation } });
    }
    return router.createUrlTree(['/portal']);
  }

  return true;
};
