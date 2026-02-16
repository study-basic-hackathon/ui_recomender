# Development Guidelines

## Architecture
- Backend: FastAPI + SQLAlchemy (router → usecase → repository)
- Frontend: React + TypeScript + Vite + React Router
- Container: Docker Compose

## FastAPI Rules
- Use `HTTPException` for expected errors
- Use middleware for uncaught exceptions
- Separate business logic into usecases
- Type hint everything
- Use async/await for I/O

## React Rules
- Use Error Boundaries for component errors
- Use `errorElement` in routes for route-level errors
- Use try-catch only for async operations
- Keep components small and typed
- Use React Router loaders for data fetching
