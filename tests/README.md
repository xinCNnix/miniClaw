# miniClaw E2E Tests

## Prerequisites

1. **Backend Service**: Must be running on `http://localhost:8002`
   ```bash
   cd backend
   python -m uvicorn app.main:app --host 0.0.0.0 --port 8002 --reload
   ```

2. **Frontend Service**: Must be running on `http://localhost:3000`
   ```bash
   cd frontend
   npm run dev
   ```

3. **Install Test Dependencies**:
   ```bash
   cd frontend
   npm install
   npx playwright install chromium
   ```

## Running Tests

### Run all E2E tests
```bash
cd frontend
npm run test:e2e
```

### Run specific test file
```bash
cd frontend
npx playwright test ../tests/e2e/smoke.spec.ts
```

### Run tests in debug mode
```bash
cd frontend
npx playwright test ../tests/e2e/smoke.spec.ts --debug
```

### Run tests with UI
```bash
cd frontend
npx playwright test ../tests/e2e/smoke.spec.ts --headed
```

## Test Structure

```
tests/
└── e2e/
    ├── smoke.spec.ts       # Basic smoke tests
    ├── chat.spec.ts        # Chat functionality tests
    ├── files.spec.ts       # File operations tests
    └── knowledge-base.spec.ts # Knowledge base tests
```

## Environment Variables

- `BASE_URL`: Frontend URL (default: `http://localhost:3000`)
- `BACKEND_URL`: Backend API URL (default: `http://localhost:8002`)

Example:
```bash
BASE_URL=http://localhost:3000 BACKEND_URL=http://localhost:8002 npm run test:e2e
```

## Troubleshooting

### Tests fail with "Server not running"
- Make sure both backend and frontend services are running
- Check that ports 3000 and 8002 are not in use by other processes

### Tests fail with "Browser not found"
- Install Playwright browsers: `npx playwright install chromium`

### Tests timeout
- Increase timeout in playwright.config.ts
- Check for slow network or heavy backend operations
