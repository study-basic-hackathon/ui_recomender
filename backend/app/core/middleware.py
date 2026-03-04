import logging
import time

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response

from app.core.exceptions import (
    ArtifactNotFoundError,
    InvalidJobStateError,
    JobNotFoundError,
    K8sClientError,
    ProposalNotFoundError,
)

logger = logging.getLogger(__name__)


class ErrorHandlerMiddleware(BaseHTTPMiddleware):
    """Global error handler for uncaught exceptions."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        try:
            response = await call_next(request)
            return response
        except JobNotFoundError as e:
            return JSONResponse(status_code=404, content={"detail": str(e)})
        except ProposalNotFoundError as e:
            return JSONResponse(status_code=404, content={"detail": str(e)})
        except ArtifactNotFoundError as e:
            return JSONResponse(status_code=404, content={"detail": str(e)})
        except InvalidJobStateError as e:
            return JSONResponse(status_code=400, content={"detail": str(e)})
        except K8sClientError as e:
            logger.error("K8s service error: %s", e)
            return JSONResponse(
                status_code=503,
                content={"detail": "Kubernetes service unavailable"},
            )
        except Exception:
            logger.exception(
                "Unhandled exception during request %s %s",
                request.method,
                request.url.path,
            )
            return JSONResponse(
                status_code=500,
                content={"detail": "Internal server error"},
            )


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Log request method, path, and response time."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        start = time.time()
        response = await call_next(request)
        duration = time.time() - start
        logger.info(
            "%s %s %d (%.3fs)",
            request.method,
            request.url.path,
            response.status_code,
            duration,
        )
        return response
