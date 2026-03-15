import { Routes } from '@angular/router';
import { adminAuthGuard, adminSignInRedirectGuard } from './core/admin-auth.guard';
import { clientAuthGuard, clientSignInRedirectGuard } from './core/client-auth.guard';
import { AdminAuditComponent } from './pages/admin-audit/admin-audit.component';
import { AdminBillingComponent } from './pages/admin-billing/admin-billing.component';
import { AdminSignInComponent } from './pages/admin-sign-in/admin-sign-in.component';
import { AdminConsoleComponent } from './pages/admin-console/admin-console.component';
import { AdminUsersComponent } from './pages/admin-users/admin-users.component';
import { AdminWorkspacesComponent } from './pages/admin-workspaces/admin-workspaces.component';
import { ClientPortalComponent } from './pages/client-portal/client-portal.component';
import { ClientSignInComponent } from './pages/client-sign-in/client-sign-in.component';
import { ForgotPasswordComponent } from './pages/forgot-password/forgot-password.component';
import { ResetPasswordComponent } from './pages/reset-password/reset-password.component';

export const routes: Routes = [
  {
    path: 'sign-in',
    component: ClientSignInComponent,
    canActivate: [clientSignInRedirectGuard],
    title: 'Client Sign In',
  },
  {
    path: '',
    component: ClientPortalComponent,
    canActivate: [clientAuthGuard],
    title: 'PDF Form Fixer',
  },
  {
    path: 'forgot-password',
    component: ForgotPasswordComponent,
    title: 'Forgot Password',
  },
  {
    path: 'reset-password',
    component: ResetPasswordComponent,
    title: 'Reset Password',
  },
  {
    path: 'admin/sign-in',
    component: AdminSignInComponent,
    canActivate: [adminSignInRedirectGuard],
    title: 'Admin Sign In',
  },
  {
    path: 'admin',
    component: AdminConsoleComponent,
    canActivate: [adminAuthGuard],
    children: [
      {
        path: '',
        pathMatch: 'full',
        redirectTo: 'workspaces',
      },
      {
        path: 'workspaces',
        component: AdminWorkspacesComponent,
        title: 'Admin Workspaces',
      },
      {
        path: 'users',
        component: AdminUsersComponent,
        title: 'Admin Users',
      },
      {
        path: 'billing',
        component: AdminBillingComponent,
        title: 'Admin Billing',
      },
      {
        path: 'audit',
        component: AdminAuditComponent,
        title: 'Admin Audit',
      },
    ],
  },
  {
    path: '**',
    redirectTo: '',
  },
];
