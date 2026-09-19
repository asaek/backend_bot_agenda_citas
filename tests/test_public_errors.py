import unittest

from calendar_domain import (
    AppointmentAccessDenied,
    AppointmentNotFound,
    CalendarProviderError,
    CalendarProviderUnavailable,
    InvalidAppointmentState,
    InvalidToolArguments,
    OutsideBusinessHours,
    SlotUnavailable,
    ToolErrorCode,
)
from tool_results import (
    execute_with_public_errors,
    public_error_from_exception,
    tool_result_from_exception,
)
from tool_validation import ToolValidationError


class GoogleInternalError(Exception):
    pass


class ServiceUnavailable(Exception):
    pass


class PublicErrorTests(unittest.IsolatedAsyncioTestCase):
    def test_public_errors_have_stable_codes_and_safe_messages(self) -> None:
        errors = (
            (InvalidToolArguments(), ToolErrorCode.INVALID_ARGUMENTS),
            (SlotUnavailable(), ToolErrorCode.SLOT_UNAVAILABLE),
            (OutsideBusinessHours(), ToolErrorCode.OUTSIDE_BUSINESS_HOURS),
            (AppointmentNotFound(), ToolErrorCode.APPOINTMENT_NOT_FOUND),
            (AppointmentAccessDenied(), ToolErrorCode.APPOINTMENT_ACCESS_DENIED),
            (InvalidAppointmentState(), ToolErrorCode.INVALID_APPOINTMENT_STATE),
            (
                CalendarProviderUnavailable(),
                ToolErrorCode.PROVIDER_UNAVAILABLE,
            ),
            (CalendarProviderError(), ToolErrorCode.PROVIDER_ERROR),
        )

        for error, code in errors:
            with self.subTest(error=type(error).__name__):
                result = tool_result_from_exception(error)
                self.assertFalse(result.ok)
                self.assertEqual(result.error.code, code)
                self.assertNotIn("Google", result.error.message)

    def test_validation_errors_are_reduced_to_public_errors(self) -> None:
        result = tool_result_from_exception(
            ToolValidationError(
                ToolErrorCode.DATE_IN_PAST,
                "detalle interno que no debe llegar al LLM",
            )
        )

        self.assertFalse(result.ok)
        self.assertEqual(result.error.code, ToolErrorCode.INVALID_ARGUMENTS)
        self.assertNotIn("detalle interno", result.error.message)

    def test_unknown_provider_exception_does_not_leak_its_message(self) -> None:
        result = tool_result_from_exception(
            GoogleInternalError("respuesta privada de Google con credenciales")
        )

        self.assertFalse(result.ok)
        self.assertEqual(result.error.code, ToolErrorCode.PROVIDER_ERROR)
        self.assertNotIn("respuesta privada", result.error.message)
        self.assertNotIn("credenciales", result.error.message)

    def test_transient_provider_exception_is_retryable(self) -> None:
        result = tool_result_from_exception(ServiceUnavailable("503 privado"))

        self.assertFalse(result.ok)
        self.assertEqual(result.error.code, ToolErrorCode.PROVIDER_UNAVAILABLE)
        self.assertTrue(result.error.retryable)

    async def test_execution_returns_success_or_safe_failure(self) -> None:
        async def successful_operation() -> str:
            return "ok"

        async def failing_operation() -> str:
            raise GoogleInternalError("detalle del proveedor")

        success = await execute_with_public_errors(successful_operation)
        failure = await execute_with_public_errors(failing_operation)

        self.assertTrue(success.ok)
        self.assertEqual(success.data, "ok")
        self.assertFalse(failure.ok)
        self.assertEqual(failure.error.code, ToolErrorCode.PROVIDER_ERROR)
        self.assertNotIn("detalle del proveedor", failure.error.message)
