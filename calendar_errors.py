"""API publica de errores para las operaciones de agenda."""

from calendar_domain import (
    AppointmentAccessDenied,
    AppointmentNotFound,
    CalendarProviderError,
    CalendarProviderUnavailable,
    InvalidAppointmentState,
    InvalidToolArguments,
    OutsideBusinessHours,
    PublicCalendarError,
    SlotUnavailable,
)

__all__ = [
    "AppointmentAccessDenied",
    "AppointmentNotFound",
    "CalendarProviderError",
    "CalendarProviderUnavailable",
    "InvalidAppointmentState",
    "InvalidToolArguments",
    "OutsideBusinessHours",
    "PublicCalendarError",
    "SlotUnavailable",
]
