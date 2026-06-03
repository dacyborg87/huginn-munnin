# Private GitHub Repository Checklist

## Repository Hygiene

- [ ] Confirm no real secrets, API keys, tokens, credentials, or private keys are present.
- [ ] Confirm `.env` is not tracked and `.env.example` contains placeholders only.
- [ ] Confirm generated runtime data under `apps/api/data/` is not tracked.
- [ ] Confirm `node_modules/`, `.next/`, `.venv/`, caches, and build outputs are not tracked.
- [ ] Confirm screenshots are intentional and do not expose local secrets or personal data.

## Build Verification

- [ ] Backend dependencies install from a clean clone.
- [ ] Frontend dependencies install from a clean clone.
- [ ] `apps/api/.venv/bin/python -m pytest apps/api/tests` passes.
- [ ] `apps/api/.venv/bin/ruff check apps/api/src apps/api/tests` passes.
- [ ] `npm run build` passes in `apps/web`.
- [ ] `docker compose up postgres chroma` starts infrastructure services.

## Documentation

- [ ] README includes overview, architecture, features, installation, development, screenshots, and roadmap.
- [ ] `docs/architecture.md` matches current architecture.
- [ ] `docs/repository-tree.md` matches private repository layout.
- [ ] `CONTRIBUTING.md` explains setup, checks, and security expectations.
- [ ] `CHANGELOG.md` has an Unreleased section.
- [ ] `LICENSE` is present.

## GitHub Settings

- [ ] Create the GitHub repository as private.
- [ ] Add repository description and internal topics.
- [ ] Enable secret scanning and push protection.
- [ ] Enable Dependabot alerts.
- [ ] Require pull request review before merging.
- [ ] Add branch protection for `main`.
- [ ] Add CI workflow before accepting pull requests.

## Private Release

- [ ] Tag the first private release as `v0.1.0` or keep the project pre-release.
- [ ] Mark early private releases as experimental.
- [ ] Include known limitations around in-memory stores and local-only learning persistence.
- [ ] Include defensive cybersecurity usage notes.
