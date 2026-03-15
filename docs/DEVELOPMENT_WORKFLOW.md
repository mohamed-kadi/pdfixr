# Development Workflow

## Branch Strategy

- `main`: production-ready code only.
- `develop`: integration branch for completed features.
- `feature/<ticket-or-topic>`: regular feature work.
- `fix/<ticket-or-topic>`: bug fixes.
- `hotfix/<ticket-or-topic>`: urgent production patches (branch from `main`).

## Pull Request Rules

- Open PRs into `develop` for normal work.
- Open PRs into `main` only from `develop` (release) or `hotfix/*`.
- Require CI checks to pass before merge:
  - `Backend Tests`
  - `Frontend Build`
- Require at least one review before merge.

## Recommended GitHub Repository Settings

1. Protect `main` and `develop` branches.
2. Enable:
   - Require pull request before merging.
   - Require status checks to pass before merging.
   - Require linear history (optional, recommended).
3. Disable direct pushes to protected branches.

## First-Time Local Setup

```bash
git init -b main
git add .
git commit -m "chore: initial project baseline"
git branch develop
```

## Connect To GitHub

```bash
git remote add origin <your-github-repo-url>
git push -u origin main
git push -u origin develop
```

## Daily Developer Flow

```bash
git checkout develop
git pull
git checkout -b feature/<topic>
# code changes...
git add .
git commit -m "feat: <summary>"
git push -u origin feature/<topic>
```

Then open a PR from `feature/<topic>` to `develop`.

## Release Flow

1. Ensure `develop` is stable and CI is green.
2. Open PR from `develop` to `main`.
3. Merge after review and CI pass.
4. Tag release from `main`:

```bash
git checkout main
git pull
git tag -a v0.1.0 -m "v0.1.0"
git push origin v0.1.0
```
