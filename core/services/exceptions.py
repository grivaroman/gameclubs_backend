"""
Доменные исключения сервисного слоя.

Каждое исключение несёт пользовательское сообщение и соответствующий
HTTP-статус. Транспортный слой решает, как это представить
(HTTPException в API, JSON {"status": "error"} в web).
"""


class ServiceError(Exception):
    """Базовая бизнес-ошибка. По умолчанию — 400 Bad Request."""

    status_code: int = 400

    def __init__(self, message: str, status_code: int | None = None):
        self.message = message
        if status_code is not None:
            self.status_code = status_code
        super().__init__(message)


class AuthRequiredError(ServiceError):
    status_code = 401


class ForbiddenError(ServiceError):
    status_code = 403


class NotFoundError(ServiceError):
    status_code = 404


class ConflictError(ServiceError):
    status_code = 409


class InsufficientFundsError(ServiceError):
    status_code = 402


class ValidationError(ServiceError):
    status_code = 400


class FeatureDisabledError(ServiceError):
    status_code = 404
