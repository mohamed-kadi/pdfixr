# Client Handoff (Plain Language)

Use this file when delivering to non-technical clients.

## What To Send The Client

1. Client portal URL
2. Their email + password
3. The short instructions below

Local demo URL: `http://localhost:4200/sign-in`

## Client Instructions

1. Open the portal sign-in link.
2. Enter your email and password.
3. Choose your PDF file.
4. Click **Fix PDF**.
5. Wait until status shows complete.
6. Click **Download** to get the fixed file.

## Message Template

```text
Hello,

Your PDF form portal is ready.

Portal sign-in: <your-client-signin-url>
Email: <client-email>
Password: <client-password>

How to use:
1) Open the sign-in page
2) Enter your email and password
3) Upload PDF
4) Download the fixed file when complete

If anything fails, send me a screenshot and I will fix it quickly.
```

## Internal Notes (Do Not Send To Client)

- Admin sign-in: `/admin/sign-in`
- Admin page: `/admin`
- Admin accounts: internal only
- Audit logs and billing events are admin-only
