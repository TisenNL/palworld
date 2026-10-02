# Copilot instructions

Follow the repository guidance in [`../AGENTS.md`](../AGENTS.md) for architecture, conventions, and the standard validation workflow.

Use these additional commands when targeting tests:

- Run the Vitest suite with `npm test`; target a file with `npx vitest run tests/<file>.spec.ts` and a test by title with `-t "test name"`.
- Run Playwright E2E tests with `npm run test:e2e`; target a file and test with `npx playwright test tests/e2e/<file>.spec.ts -g "test title"`.
- Run Python server tests with `npm run test:server`; target one module from the repository root with `py -3 -m unittest tests.test_game_marker_automation`, or one test with `py -3 -m unittest tests.test_game_marker_automation.<TestClass>.<test_method>`.
