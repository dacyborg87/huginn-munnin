# Contributing

Thank you for considering a contribution to HUGINN // MUNINN.

## Development Workflow

1. Fork the repository and create a feature branch.
2. Keep changes focused and avoid unrelated refactors.
3. Run backend tests and linting before opening a pull request.
4. Run the frontend production build before opening a pull request.
5. Update documentation when behavior, setup, or architecture changes.

## Local Setup

Backend:

```bash
cd apps/api
python -m venv .venv
. .venv/bin/activate
pip install -e ".[dev]"
uvicorn --app-dir src huginn_muninn_api.main:app --reload
```

Frontend:

```bash
cd apps/web
npm install
npm run dev
```

Infrastructure:

```bash
docker compose up postgres chroma
```

## Checks

Run from the repository root:

```bash
apps/api/.venv/bin/python -m pytest apps/api/tests
apps/api/.venv/bin/ruff check apps/api/src apps/api/tests
cd apps/web && npm run build
```

## Security

Do not commit secrets, `.env` files, generated runtime memory, local databases, virtual environments, dependency folders, or build artifacts.

Cybersecurity features must remain defensive and assistive. Contributions that add active scanning, exploitation, or system automation must include explicit authorization boundaries and safety controls.

## Pull Request Expectations

- Explain the problem and the approach.
- Include tests for behavior changes.
- Note any limitations or follow-up work.
- Include screenshots for dashboard changes.
