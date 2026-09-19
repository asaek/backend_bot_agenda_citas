"""Conversion de excepciones internas o de proveedores a resultados publicos."""

from collections.abc import Awaitable, Callable
from typing import TypeVar

from calendar_domain import (
    AppointmentAccessDenied,
    AppointmentNotFound,
    CalendarProviderError,
    CalendarProviderUnavailable,
    DomainValidationError,
    InvalidAppointmentState,
    InvalidToolArguments,
    OutsideBusinessHours,
    PublicCalendarError,
    SlotUnavailable,
    ToolErrorCode,
    ToolResult,
)
from tool_validation import ToolValidationError


_RESULT = TypeVar("_RESULT")

_VALIDATION_ERROR_TYPES = {
    ToolErrorCode.INVALID_ARGUMENTS: InvalidToolArguments,
    ToolErrorCode.DATE_IN_PAST: InvalidToolArguments,
    ToolErrorCode.SLOT_UNAVAILABLE: SlotUnavailable,
    ToolErrorCode.OUTSIDE_BUSINESS_HOURS: OutsideBusinessHours,
    ToolErrorCode.APPOINTMENT_NOT_FOUND: AppointmentNotFound,
    ToolErrorCode.APPOINTMENT_ACCESS_DENIED: AppointmentAccessDenied,
    ToolErrorCode.INVALID_APPOINTMENT_STATE: InvalidAppointmentState,
    ToolErrorCode.PROVIDER_UNAVAILABLE: CalendarProviderUnavailable,
    ToolErrorCode.PROVIDER_ERROR: CalendarProviderError,
}

_UNAVAILABLE_EXCEPTION_NAMES = frozenset(
    {
        "BadGateway",
        "ConnectError",
        "ConnectTimeout",
        "DeadlineExceeded",
        "GatewayTimeout",
        "InternalServerError",
        "NetworkError",
        "PoolTimeout",
        "ReadTimeout",
        "ResourceExhausted",
        "ServiceUnavailable",
        "Timeout",
        "TimeoutError",
        "TooManyRequests",
        "Unavailable",
        "WriteTimeout",
    }
)


def public_error_from_exception(error: BaseException) -> PublicCalendarError:
    """Reduce cualquier fallo a una excepcion de agenda sin detalles internos."""
    if isinstance(error, PublicCalendarError):
        return error

    if isinstance(error, ToolValidationError):
        try:
            code = ToolErrorCode(error.code)
        except ValueError:
            return InvalidToolArguments()
        error_type = _VALIDATION_ERROR_TYPES.get(code, InvalidToolArguments)
        return error_type()

    if isinstance(error, DomainValidationError):
        return InvalidToolArguments()

    if _is_provider_unavailable(error):
        return CalendarProviderUnavailable()
    return CalendarProviderError()


def tool_result_from_exception(error: BaseException) -> ToolResult:
    """Convierte un error en el resultado seguro que recibe el agente."""
    return ToolResult.failure(public_error_from_exception(error).to_tool_error())


async def execute_with_public_errors(
    operation: Callable[[], Awaitable[_RESULT]],
) -> ToolResult:
    """Ejecuta una operacion y evita propagar excepciones al LLM."""
    try:
        return ToolResult.success(await operation())
    except Exception as error:
        return tool_result_from_exception(error)


def _is_provider_unavailable(error: BaseException) -> bool:
    if isinstance(error, (ConnectionError, TimeoutError)):
        return True

    current: BaseException | None = error
    while current is not None:
        if type(current).__name__ in _UNAVAILABLE_EXCEPTION_NAMES:
            return True
        current = current.__cause__
    return False
