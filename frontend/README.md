# Frontend (Angular)

Separate Angular frontend for this project.

## Routes

- `/sign-in` client sign-in (email + password)
- `/forgot-password` request password reset
- `/reset-password?token=<token>` confirm password reset
- `/` client portal (protected)
- `/admin/sign-in` owner/admin sign-in (email + password)
- `/admin/workspaces` owner/admin workspace management (protected)
- `/admin/users` owner/admin user management (protected)
- `/admin/billing` owner/admin billing events (protected)
- `/admin/audit` owner/admin global audit logs (protected)

Sign-in exchanges credentials for bearer token sessions used for API requests.

Password reset flow:
- `/forgot-password` submits reset requests.
- `/reset-password` applies a new password using the token.
- Token/URL are only shown in UI when backend env `PDF_SAAS_PASSWORD_RESET_RETURN_TOKEN=true`.

Admin console includes:
- Workspace creation + plan/billing edits
- User creation + role/workspace/active edits
- Inline user password reset
- Billing events + global audit views

Each admin route is a separate component for easier debugging and future feature work.

## Local Run

```bash
cd frontend
PATH=/opt/homebrew/bin:$PATH npm install
PATH=/opt/homebrew/bin:$PATH npm start
```

Open `http://localhost:4200`.

Backend API is expected at `http://localhost:8000/api/v1`.

Default dev accounts:
- Client: `client@local.dev` / `Client123!!`
- Admin: `admin@local.dev` / `Admin123!!`

## API Base Override (Optional)

You can override API base at runtime in browser console:

```js
localStorage.setItem('pdf_saas_api_base', 'https://your-api-domain/api/v1')
location.reload()
```

## Admin Host Gating (Optional)

You can restrict access to `/admin/*` routes by host.  
If no hosts are configured, admin routes are available on the current host (default dev behavior).

Runtime options:

```js
// In browser console (comma-separated list)
localStorage.setItem('pdf_saas_admin_hosts', 'admin.localhost:4201,admin.yourdomain.com')
location.reload()
```

Or provide a global runtime variable before Angular boots:

```html
<script>
  window.PDF_SAAS_ADMIN_ALLOWED_HOSTS = 'admin.yourdomain.com';
</script>
```

With host gating enabled, opening `/admin/*` from a non-allowed host redirects to `/sign-in`.

## Build

```bash
cd frontend
PATH=/opt/homebrew/bin:$PATH npm run build
```

## Build Stability Note

This project is configured with the Webpack-based Angular browser builder (`@angular-devkit/build-angular:browser`) for stability on some macOS/ARM environments where the esbuild-based application builder can crash with a native Node malloc error.
