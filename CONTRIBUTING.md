# Contributing to miniClaw

Thank you for your interest in contributing to miniClaw! We welcome contributions from the community.

## How to Contribute

### Reporting Bugs

Before creating bug reports, please check existing issues to avoid duplicates. When creating a bug report, include:

- **Description**: Clear description of the bug
- **Steps to reproduce**: Minimal steps to reproduce the issue
- **Expected behavior**: What you expected to happen
- **Actual behavior**: What actually happened
- **Environment**: OS, Python/Node version, browser info
- **Screenshots**: If applicable

### Suggesting Enhancements

We appreciate enhancement suggestions! When suggesting, include:

- **Use case**: What problem would this solve?
- **Proposed solution**: How should it work?
- **Alternatives**: What other approaches did you consider?
- **Impact**: How would this benefit users?

### Pull Requests

1. **Fork the repository** and create your branch from `main`
   ```bash
   git checkout -b feature/your-feature-name
   ```

2. **Follow the code standards** (see [CLAUDE.md](./CLAUDE.md))
   - Python: PEP8, Type Hints
   - TypeScript: Strict mode, no `any`
   - LangChain: Use `create_agent` API

3. **Write tests** for new functionality
   ```bash
   # Backend
   cd backend && pytest tests/

   # Frontend
   cd frontend && npm test
   ```

4. **Update documentation** if needed
   - README.md
   - API.md (for API changes)
   - ARCHITECTURE.md (for architectural changes)

5. **Keep changes small** and focused
   - One PR per feature/fix
   - Clear commit messages
   - Reference related issues

6. **Ensure all tests pass**
   ```bash
   # Backend
   cd backend && pytest --cov=app

   # Frontend
   cd frontend && npm run test:coverage
   ```

7. **Submit your PR** with:
   - Clear description of changes
   - Links to related issues
   - Screenshots for UI changes (if applicable)

## Development Setup

### Backend Development

```bash
cd backend

# Create virtual environment
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Run tests
pytest tests/

# Run with coverage
pytest --cov=app
```

### Frontend Development

```bash
cd frontend

# Install dependencies
npm install

# Start development server
npm run dev

# Run tests
npm test

# Run E2E tests
npx playwright test
```

## Code Style

### Python (Backend)

- Follow PEP 8
- Use Type Hints for all functions
- Maximum line length: 100 characters
- Use f-strings for string formatting
- Add docstrings for public functions

### TypeScript (Frontend)

- Use functional components
- Use TypeScript strict mode
- Avoid `any` type
- Use meaningful variable names
- Add JSDoc comments for complex functions

## Coding Standards

Please read [CLAUDE.md](./CLAUDE.md) for detailed coding standards and AI collaboration protocols.

Key points:
- **No hardcoded secrets**
- **Error handling** in all external calls
- **Input validation** for user data
- **Security first** (sanitization, validation)
- **Don't repeat yourself** - reuse existing code

## Testing Guidelines

### Backend Tests

- Unit tests for all tools and functions
- Integration tests for API endpoints
- Mock external API calls
- Target: 80%+ code coverage

### Frontend Tests

- Component tests with React Testing Library
- Hook tests with @testing-library/react-hooks
- E2E tests with Playwright
- Target: 70%+ code coverage

## Commit Messages

Use clear, descriptive commit messages:

```
type(scope): subject

body

footer
```

Types:
- `feat`: New feature
- `fix`: Bug fix
- `docs`: Documentation changes
- `style`: Code style changes (formatting)
- `refactor`: Code refactoring
- `test`: Adding or updating tests
- `chore`: Maintenance tasks

Examples:
- `feat(tools): add file upload capability`
- `fix(api): resolve SSE connection timeout issue`
- `docs(readme): update installation instructions`

## Project Structure

```
miniclaw/
├── backend/app/
│   ├── core/       # Core modules (agent, llm, tools)
│   ├── tools/      # 5 core tools
│   ├── skills/     # Skills system
│   ├── memory/     # Memory management
│   └── api/        # API routes
├── frontend/
│   ├── app/        # Next.js App Router
│   ├── components/ # React components
│   ├── hooks/      # Custom hooks
│   └── lib/        # Utilities
└── docs/           # Documentation
```

## Questions?

Feel free to:
- Open an issue for bugs or feature requests
- Start a discussion for general questions
- Join our community chat (if available)

## License

By contributing, you agree that your contributions will be licensed under the **MIT License**.

---

**Thank you for contributing to miniClaw! 🚀**
