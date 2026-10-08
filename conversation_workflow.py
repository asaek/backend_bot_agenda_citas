"""Snapshots persistentes de una gestion activa o pausada, sin efectos de agenda."""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime

from appointment_availability import (
    PENDING_APPOINTMENT_AVAILABILITY_KEY,
    PENDING_APPOINTMENT_DATE_KEY,
    PendingAppointmentAvailability,
    PendingAppointmentDate,
)
from appointment_confirmation import PENDING_APPOINTMENT_ACTION_KEY, PendingAppointmentAction
from appointment_scheduling import PENDING_APPOINTMENT_REASON_KEY, PendingAppointmentReason
from conversation_intent import PendingConversationFlow


PAUSED_CONVERSATION_WORKFLOW_KEY = "paused_conversation_workflow"
PENDING_WORKFLOW_KEYS = (
    PENDING_APPOINTMENT_ACTION_KEY,
    PENDING_APPOINTMENT_REASON_KEY,
    PENDING_APPOINTMENT_AVAILABILITY_KEY,
    PENDING_APPOINTMENT_DATE_KEY,
)


@dataclass(frozen=True, slots=True)
class PendingConversationWorkflow:
    flow: PendingConversationFlow
    action: PendingAppointmentAction | None = None
    reason: PendingAppointmentReason | None = None
    availability: PendingAppointmentAvailability | None = None
    pending_date: PendingAppointmentDate | None = None

    @classmethod
    def from_context(cls, value: object) -> "PendingConversationWorkflow":
        if not isinstance(value, Mapping):
            return cls(PendingConversationFlow.NONE)
        action = PendingAppointmentAction.from_context(value.get(PENDING_APPOINTMENT_ACTION_KEY))
        if action is not None:
            return cls(PendingConversationFlow.APPOINTMENT_CONFIRMATION, action=action)
        reason = PendingAppointmentReason.from_context(value.get(PENDING_APPOINTMENT_REASON_KEY))
        if reason is not None:
            return cls(PendingConversationFlow.BOOKING_DETAILS, reason=reason)
        availability = PendingAppointmentAvailability.from_context(
            value.get(PENDING_APPOINTMENT_AVAILABILITY_KEY)
        )
        if availability is not None:
            flow = (
                PendingConversationFlow.RESCHEDULE_AVAILABILITY
                if availability.appointment_id is not None
                else PendingConversationFlow.BOOKING_AVAILABILITY
            )
            return cls(flow, availability=availability)
        pending_date = PendingAppointmentDate.from_context(value.get(PENDING_APPOINTMENT_DATE_KEY))
        if pending_date is not None:
            return cls(PendingConversationFlow.BOOKING_DATE, pending_date=pending_date)
        return cls(PendingConversationFlow.NONE)

    def to_context(self) -> dict[str, object]:
        for key, value in (
            (PENDING_APPOINTMENT_ACTION_KEY, self.action),
            (PENDING_APPOINTMENT_REASON_KEY, self.reason),
            (PENDING_APPOINTMENT_AVAILABILITY_KEY, self.availability),
            (PENDING_APPOINTMENT_DATE_KEY, self.pending_date),
        ):
            if value is not None:
                return {key: value.to_context()}
        return {}


@dataclass(frozen=True, slots=True)
class PausedConversationWorkflow:
    workflow: PendingConversationWorkflow
    paused_at: str

    @classmethod
    def from_context(cls, value: object) -> "PausedConversationWorkflow | None":
        if not isinstance(value, Mapping) or not isinstance(value.get("paused_at"), str):
            return None
        try:
            timestamp = datetime.fromisoformat(value["paused_at"])
        except ValueError:
            return None
        workflow = PendingConversationWorkflow.from_context(value.get("workflow"))
        if timestamp.utcoffset() is None or workflow.flow is PendingConversationFlow.NONE:
            return None
        return cls(workflow, value["paused_at"])

    def to_context(self) -> dict[str, object]:
        return {"workflow": self.workflow.to_context(), "paused_at": self.paused_at}
