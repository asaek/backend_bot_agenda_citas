import json
import unittest
from datetime import datetime, time, timezone

from agent_orchestrator import AgentIterationLimitError, AgentOrchestrator
from calendar_domain import PatientScope, ToolErrorCode
from fake_calendar_provider import FakeCalendarProvider
from llm_provider import ChatMessage, ToolCall
from fakes import FakeLLMProvider
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
        self.assertNotIn("5491100000000", llm.received_messages[1][2].content)
        self.assertNotIn("calendar-1", llm.received_messages[1][2].content)

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
