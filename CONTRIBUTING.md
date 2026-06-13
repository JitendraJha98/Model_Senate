# Contributing to Model Senate

Thanks for your interest in improving Model Senate. This document covers everything you need to go from zero to an open pull request.

---

## Table of Contents

- [Ways to Contribute](#ways-to-contribute)
- [Development Setup](#development-setup)
- [Project Conventions](#project-conventions)
- [Making a Change](#making-a-change)
- [Submitting a Pull Request](#submitting-a-pull-request)
- [Good First Issues](#good-first-issues)

---

## Ways to Contribute

- **Bug reports** — open an issue with the bug report template
- **Feature requests** — open an issue with the feature request template
- **Code changes** — bug fixes, new provider adapters, UI improvements, new tools
- **Documentation** — fixing typos, improving setup instructions, expanding architecture notes
- **Tests** — adding coverage for untested paths

---

## Development Setup

### Prerequisites

- Python 3.10+ and [`uv`](https://docs.astral.sh/uv/)
- Node.js 18+ and `npm`
- At least one API key — [OpenRouter](https://openrouter.ai/) covers all default models with one key

### Steps

```bash
# 1. Fork and clone
git clone https://github.com/<your-username>/Model_Senate.git
cd Model_Senate

# 2. Install backend dependencies
uv sync

# 3. Install frontend dependencies
cd frontend && npm install && cd ..

# 4. Configure keys
cp .env.example .env
# Edit .env — add at minimum OPENROUTER_API_KEY

# 5. Start both servers
./start.sh          # macOS / Linux
.\start.ps1         # Windows PowerShell
```

Open **http://localhost:5173** to verify everything works.

---

## Project Conventions

These are enforced in code review. Read `CLAUDE.md` for the full engineering philosophy — here is the short version:

**Code style**
- Match the existing style in whatever file you're editing. No reformatting unrelated code.
- No comments that describe *what* the code does — only *why* when the reason is non-obvious.
- No features beyond what the issue asks for. No speculative abstractions.

**Tests**
- Backend tests live in `tests/`. Run with `uv run pytest`.
- Frontend tests live alongside components. Run with `cd frontend && npm test`.
- `asyncio_mode = "auto"` is already set — async test functions don't need decorators.
- Use `respx` for HTTP mocking; `FakeAdapter` in `test_senate.py` shows the pattern.
- All tests must pass before opening a PR.

**Branch model**
- Branch off `development`, not `main`.
- `main` is protected — all merges go through PRs.
- Name branches descriptively: `fix/council-parse-failure`, `feat/add-mistral-adapter`.

**Commits**
- One logical change per commit.
- Present-tense imperative subject line: `Add Mistral provider adapter`, not `Added` or `Adding`.

---

## Making a Change

1. **Open or find an issue first.** Even for small changes, a linked issue makes review easier.
2. **Branch off `development`.**

   ```bash
   git checkout development
   git pull origin development
   git checkout -b fix/your-change
   ```

3. **Make your change.** Touch only what you must — see `CLAUDE.md § Surgical Changes`.
4. **Verify.**

   ```bash
   uv run pytest                    # backend
   cd frontend && npm test          # frontend
   cd frontend && npm run build     # type-check
   ```

5. **Commit and push.**

   ```bash
   git push origin fix/your-change
   ```

---

## Submitting a Pull Request

- Open the PR against `development`, not `main`.
- Fill out the PR template — description, test plan, screenshots if it's a UI change.
- Keep the diff focused. A PR that does two unrelated things will be asked to split.
- If you're unsure whether a change is in scope, open a discussion issue first — it saves everyone time.

---

## Good First Issues

Look for issues tagged [`good first issue`](https://github.com/JitendraJha98/Model_Senate/issues?q=is%3Aissue+is%3Aopen+label%3A%22good+first+issue%22) on GitHub. These are self-contained, well-scoped, and don't require deep knowledge of the full pipeline.

---

## Questions

Open a [GitHub Discussion](https://github.com/JitendraJha98/Model_Senate/discussions) — issues are for bugs and feature requests, discussions are for everything else.
