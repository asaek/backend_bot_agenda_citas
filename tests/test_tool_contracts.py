import unittest
from datetime import datetime
from zoneinfo import ZoneInfo

from calendar_domain import (
    Appointment,
    AvailableSlot,
    DomainValidationError,
    PatientScope,
    ToolName,
    ToolRequest,
)
from tool_contracts import (
    TOOL_DEFINITIONS,
    CancelAppointmentInput,
    CancelAppointmentOutput,
    CheckAvailabilityInput,
    CheckAvailabilityOutput,
    CreateAppointmentInput,
    CreateAppointmentOutput,
    ListAppointmentsInput,
    ListAppointmentsOutput,
    RescheduleAppointmentInput,
    RescheduleAppointmentOutput,
    parse_tool_request,
    llm_tool_definitions,
)


class ToolContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.patient_scope = PatientScope(
            patient_id=1,
            conversation_id=2,
            whatsapp_number="5491100000000",
        )

    def request(
        self,
        tool_name: ToolName,
        arguments: dict[str, object],
    ) -> ToolRequest:
        return ToolRequest(
            tool_name=tool_name,
            arguments=arguments,
            patient_scope=self.patient_scope,
        )

    def test_defines_exactly_the_five_backend_tools(self) -> None:
        self.assertEqual(
            set(TOOL_DEFINITIONS),
            {
                ToolName.CHECK_AVAILABILITY,
                ToolName.CREATE_APPOINTMENT,
                ToolName.LIST_APPOINTMENTS,
                ToolName.RESCHEDULE_APPOINTMENT,
                ToolName.CANCEL_APPOINTMENT,
            },
        )
        for definition in TOOL_DEFINITIONS.values():
            self.assertNotIn("patient_id", definition.allowed_arguments)
            self.assertNotIn("duration_minutes", definition.allowed_arguments)
            self.assertNotIn("calendar_ids", definition.allowed_arguments)
            self.assertNotIn("timezone", definition.allowed_arguments)

    def test_parses_availability_using_the_backend_timezone(self) -> None:
        parsed = parse_tool_request(
            self.request(
                ToolName.CHECK_AVAILABILITY,
                {
                    "start_at": "2026-09-21T10:00:00",
                    "end_at": "2026-09-21T17:00:00",
                },
            ),
            default_timezone="America/Mexico_City",
        )

        self.assertIsInstance(parsed, CheckAvailabilityInput)
        self.assertEqual(parsed.patient_scope, self.patient_scope)
        self.assertEqual(parsed.start_at.tzinfo, ZoneInfo("America/Mexico_City"))
        self.assertEqual(parsed.end_at.hour, 17)

    def test_parses_create_appointment_without_llm_owned_defaults(self) -> None:
        parsed = parse_tool_request(
            self.request(
                ToolName.CREATE_APPOINTMENT,
                {
                    "start_at": "2026-09-21T10:00:00",
                    "reason": "Revision",
                },
            ),
            default_timezone="UTC",
        )

        self.assertIsInstance(parsed, CreateAppointmentInput)
        self.assertEqual(parsed.patient_scope, self.patient_scope)
        self.assertEqual(parsed.start_at.tzinfo, ZoneInfo("UTC"))
        self.assertEqual(parsed.reason, "Revision")
        self.assertFalse(hasattr(parsed, "duration_minutes"))
        self.assertFalse(hasattr(parsed, "calendar_ids"))

    def test_list_appointments_allows_an_empty_range_or_a_complete_range(self) -> None:
        all_appointments = parse_tool_request(
            self.request(ToolName.LIST_APPOINTMENTS, {}),
            default_timezone="UTC",
        )
        ranged = parse_tool_request(
            self.request(
                ToolName.LIST_APPOINTMENTS,
                {
                    "start_at": "2026-09-21T00:00:00",
                    "end_at": "2026-09-22T00:00:00",
                },
            ),
            default_timezone="UTC",
        )

        self.assertIsInstance(all_appointments, ListAppointmentsInput)
        self.assertIsNone(all_appointments.start_at)
        self.assertIsInstance(ranged, ListAppointmentsInput)
        self.assertIsNotNone(ranged.end_at)

    def test_list_appointments_schema_keeps_the_range_optional(self) -> None:
        definition = next(
            tool["function"]
            for tool in llm_tool_definitions()
            if tool["function"]["name"] == ToolName.LIST_APPOINTMENTS.value
        )

        parameters = definition["parameters"]
        self.assertEqual(set(parameters["properties"]), {"start_at", "end_at"})
        self.assertNotIn("required", parameters)
        self.assertFalse(parameters["additionalProperties"])

    def test_parses_reschedule_and_cancel_with_backend_scope(self) -> None:
        reschedule = parse_tool_request(
            self.request(
                ToolName.RESCHEDULE_APPOINTMENT,
                {
                    "appointment_id": "appointment-1",
                    "new_start_at": "2026-09-21T11:00:00",
                },
            ),
            default_timezone="UTC",
        )
        cancel = parse_tool_request(
            self.request(
                ToolName.CANCEL_APPOINTMENT,
                {"appointment_id": "appointment-1"},
            ),
            default_timezone="UTC",
        )

        self.assertIsInstance(reschedule, RescheduleAppointmentInput)
        self.assertEqual(reschedule.patient_scope, self.patient_scope)
        self.assertIsInstance(cancel, CancelAppointmentInput)
        self.assertEqual(cancel.appointment_id, "appointment-1")

    def test_rejects_missing_unknown_and_incomplete_arguments(self) -> None:
        with self.assertRaises(DomainValidationError):
            parse_tool_request(
                self.request(ToolName.CREATE_APPOINTMENT, {"reason": "Revision"}),
                default_timezone="UTC",
            )

        with self.assertRaises(DomainValidationError):
            parse_tool_request(
                self.request(
                    ToolName.CANCEL_APPOINTMENT,
                    {"appointment_id": "appointment-1", "reason": "Ya no puedo"},
                ),
                default_timezone="UTC",
            )

        with self.assertRaises(DomainValidationError):
            parse_tool_request(
                self.request(
                    ToolName.LIST_APPOINTMENTS,
                    {"start_at": "2026-09-21T00:00:00"},
                ),
                default_timezone="UTC",
            )

    def test_contract_outputs_are_typed_and_immutable(self) -> None:
        start_at = datetime(2026, 9, 21, 10, tzinfo=ZoneInfo("UTC"))
        appointment = Appointment(
            id="appointment-1",
            patient_scope=self.patient_scope,
            calendar_id="calendar-1",
            start_at=start_at,
            end_at=datetime(2026, 9, 21, 10, 30, tzinfo=ZoneInfo("UTC")),
            reason="Revision",
        )
        slot = AvailableSlot(
            calendar_id="calendar-1",
            start_at=start_at,
            end_at=datetime(2026, 9, 21, 10, 30, tzinfo=ZoneInfo("UTC")),
        )

        availability = CheckAvailabilityOutput(slots=(slot,))
        created = CreateAppointmentOutput(appointment=appointment)
        listed = ListAppointmentsOutput(appointments=(appointment,))
        rescheduled = RescheduleAppointmentOutput(appointment=appointment)
        cancelled = CancelAppointmentOutput(appointment=appointment)

        self.assertEqual(availability.slots, (slot,))
        self.assertEqual(created.appointment, appointment)
        self.assertEqual(listed.appointments, (appointment,))
        self.assertEqual(rescheduled.appointment, appointment)
        self.assertEqual(cancelled.appointment, appointment)
