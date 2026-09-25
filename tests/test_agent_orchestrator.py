import json
import unittest
from datetime import datetime, time, timezone

from agent_orchestrator import AgentIterationLimitError, AgentOrchestrator
from calendar_domain import (
    AppointmentStatus,
    CalendarProviderUnavailable,
    PatientScope,
    ToolErrorCode,
    ToolName,
)
from fake_calendar_provider import FakeCalendarProvider
from llm_provider import ChatMessage, ToolCall
from fakes import FakeLLMProvider
from notification_domain import (
    AppointmentNotificationEvent,
    AppointmentNotificationType,
)
from tool_executor import ToolExecutor
from tool_validation import BusinessHours, TimeWindow


class AgentOrchestratorTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.patient_scope = PatientScope(
            patient_id=7,
            conversation_id=9,
            whatsapp_number="5491100000000",
        )
        self.now = datetime(2026, 9, 20, 12, 0, tzinfo=timezone.utc)
        self.business_hours = BusinessHours(
            timezone_name="UTC",
            windows_by_weekday={
                weekday: (TimeWindow(time(9), time(17)),)
                for weekday in range(5)
            },
        )

    def executor(self, provider: FakeCalendarProvider) -> ToolExecutor:
        return ToolExecutor(
            provider=provider,
            business_hours=self.business_hours,
            default_timezone="UTC",
            now=self.now,
        )

    async def test_executes_tool_with_backend_scope_and_requests_final_text(self) -> None:
        provider = FakeCalendarProvider()
        llm = FakeLLMProvider(
            replies=(
                ToolCall(
                    name="create_appointment",
                    arguments={
                        "start_at": "2026-09-21T10:00:00",
                        "reason": "Revision",
                    },
                ),
                "La cita fue creada.",
            )
        )
        orchestrator = AgentOrchestrator(
            llm_provider=llm,
            tool_executor=self.executor(provider),
            max_iterations=2,
        )

        reply = await orchestrator.run(
            messages=[ChatMessage(role="user", content="Necesito una cita")],
            patient_scope=self.patient_scope,
        )

        self.assertEqual(reply, "La cita fue creada.")
        self.assertEqual(llm.call_count, 2)
        self.assertEqual(provider.appointments[0].patient_scope, self.patient_scope)
        self.assertEqual(
            [message.role for message in llm.received_messages[1]],
            ["user", "assistant", "tool"],
        )
        assistant_message = llm.received_messages[1][1]
        self.assertEqual(assistant_message.tool_calls[0].name, "create_appointment")
        tool_payload = json.loads(llm.received_messages[1][2].content)
        self.assertTrue(tool_payload["ok"])
        self.assertEqual(
            tool_payload["data"]["appointment"]["id"],
            provider.appointments[0].id,
        )
        self.assertNotIn("5491100000000", llm.received_messages[1][2].content)
        self.assertNotIn("calendar-1", llm.received_messages[1][2].content)

    async def test_emits_event_for_successful_create_with_request_identity(self) -> None:
        provider = FakeCalendarProvider()
        llm = FakeLLMProvider(
            replies=(
                ToolCall(
                    name="create_appointment",
                    arguments={
                        "start_at": "2026-09-21T10:00:00",
                        "reason": "Revision",
                    },
                    call_id="call-create",
                ),
                "La cita fue creada.",
            )
        )
        orchestrator = AgentOrchestrator(
            llm_provider=llm,
            tool_executor=self.executor(provider),
        )
        events: list[AppointmentNotificationEvent] = []

        await orchestrator.run(
            messages=[ChatMessage(role="user", content="Necesito una cita")],
            patient_scope=self.patient_scope,
            incoming_message_id=42,
            on_appointment_event=events.append,
        )

        self.assertEqual(len(events), 1)
        event = events[0]
        self.assertEqual(event.notification_type, AppointmentNotificationType.SCHEDULED)
        self.assertEqual(event.tool_name, ToolName.CREATE_APPOINTMENT)
        self.assertEqual(event.incoming_message_id, 42)
        self.assertEqual(event.tool_call_id, "call-create")
        self.assertEqual(event.patient_scope, self.patient_scope)
        self.assertEqual(event.appointment, provider.appointments[0])

    async def test_emits_events_for_successful_reschedule_and_cancel(self) -> None:
        provider = FakeCalendarProvider()
        appointment = await provider.create_appointment(
            patient_scope=self.patient_scope,
            start_at=datetime(2026, 9, 21, 10, tzinfo=timezone.utc),
            reason="Revision",
        )
        events: list[AppointmentNotificationEvent] = []

        for message_id, tool_name, arguments, call_id in (
            (
                43,
                "reschedule_appointment",
                {
                    "appointment_id": appointment.id,
                    "new_start_at": "2026-09-21T11:00:00",
                },
                "call-reschedule",
            ),
            (
                44,
                "cancel_appointment",
                {"appointment_id": appointment.id},
                "call-cancel",
            ),
        ):
            orchestrator = AgentOrchestrator(
                llm_provider=FakeLLMProvider(
                    replies=(
                        ToolCall(
                            name=tool_name,
                            arguments=arguments,
                            call_id=call_id,
                        ),
                        "Operacion completada.",
                    )
                ),
                tool_executor=self.executor(provider),
            )

            await orchestrator.run(
                messages=[ChatMessage(role="user", content="Actualiza mi cita")],
                patient_scope=self.patient_scope,
                incoming_message_id=message_id,
                on_appointment_event=events.append,
            )

        self.assertEqual(
            [event.notification_type for event in events],
            [
                AppointmentNotificationType.MODIFIED,
                AppointmentNotificationType.CANCELLED,
            ],
        )
        self.assertEqual(
            [event.tool_name for event in events],
            [ToolName.RESCHEDULE_APPOINTMENT, ToolName.CANCEL_APPOINTMENT],
        )
        self.assertEqual(
            [event.tool_call_id for event in events],
            ["call-reschedule", "call-cancel"],
        )
        self.assertEqual(events[-1].appointment.status, AppointmentStatus.CANCELLED)

    async def test_does_not_emit_event_when_appointment_operation_fails(self) -> None:
        provider = FakeCalendarProvider(
            simulated_errors={
                ToolName.CREATE_APPOINTMENT: CalendarProviderUnavailable,
            }
        )
        llm = FakeLLMProvider(
            replies=(
                ToolCall(
                    name="create_appointment",
                    arguments={
                        "start_at": "2026-09-21T10:00:00",
                        "reason": "Revision",
                    },
                ),
                "No pude crear la cita.",
            )
        )
        orchestrator = AgentOrchestrator(
            llm_provider=llm,
            tool_executor=self.executor(provider),
        )
        events: list[AppointmentNotificationEvent] = []

        await orchestrator.run(
            messages=[ChatMessage(role="user", content="Necesito una cita")],
            patient_scope=self.patient_scope,
            incoming_message_id=45,
            on_appointment_event=events.append,
        )

        self.assertEqual(events, [])
        self.assertEqual(provider.appointments, ())

    async def test_does_not_emit_event_for_non_mutating_tool(self) -> None:
        provider = FakeCalendarProvider()
        llm = FakeLLMProvider(
            replies=(
                ToolCall(name="list_appointments", arguments={}),
                "No tienes citas.",
            )
        )
        orchestrator = AgentOrchestrator(
            llm_provider=llm,
            tool_executor=self.executor(provider),
        )
        events: list[AppointmentNotificationEvent] = []

        await orchestrator.run(
            messages=[ChatMessage(role="user", content="Lista mis citas")],
            patient_scope=self.patient_scope,
            incoming_message_id=46,
            on_appointment_event=events.append,
        )

        self.assertEqual(events, [])

    async def test_rejects_patient_and_calendar_arguments_before_provider(self) -> None:
        provider = FakeCalendarProvider()
        llm = FakeLLMProvider(
            replies=(
                ToolCall(
                    name="create_appointment",
                    arguments={
                        "start_at": "2026-09-21T10:00:00",
                        "reason": "Revision",
                        "patient_id": 999,
                        "calendar_id": "other-calendar",
                    },
                ),
                "No puedo ejecutar esa solicitud.",
            )
        )
        orchestrator = AgentOrchestrator(
            llm_provider=llm,
            tool_executor=self.executor(provider),
        )

        reply = await orchestrator.run(
            messages=[ChatMessage(role="user", content="Reserva")],
            patient_scope=self.patient_scope,
        )

        self.assertEqual(reply, "No puedo ejecutar esa solicitud.")
        self.assertEqual(provider.appointments, ())
        tool_payload = json.loads(llm.received_messages[1][2].content)
        self.assertFalse(tool_payload["ok"])
        self.assertEqual(tool_payload["error"]["code"], ToolErrorCode.INVALID_ARGUMENTS.value)

    async def test_stops_after_the_configured_number_of_tool_iterations(self) -> None:
        provider = FakeCalendarProvider()
        tool_call = ToolCall(
            name="list_appointments",
            arguments={},
        )
        llm = FakeLLMProvider(replies=(tool_call, tool_call, "Nunca llega"))
        orchestrator = AgentOrchestrator(
            llm_provider=llm,
            tool_executor=self.executor(provider),
            max_iterations=1,
        )

        with self.assertRaises(AgentIterationLimitError):
            await orchestrator.run(
                messages=[ChatMessage(role="user", content="Lista mis citas")],
                patient_scope=self.patient_scope,
            )

        self.assertEqual(llm.call_count, 2)

    def test_requires_a_positive_iteration_limit(self) -> None:
        with self.assertRaises(ValueError):
            AgentOrchestrator(
                llm_provider=FakeLLMProvider(),
                tool_executor=self.executor(FakeCalendarProvider()),
                max_iterations=0,
            )
