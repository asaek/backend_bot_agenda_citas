import unittest

from conversation_intent import (
    PendingConversationFlow,
    PendingInterruption,
    classify_pending_interruption,
    is_reschedule_request_without_target_time,
)


class PendingConversationIntentTests(unittest.TestCase):
    def test_explicit_abandonment_beats_the_pending_slot_selection(self) -> None:
        interruption = classify_pending_interruption(
            "no cancela mejor dejala asi",
            flow=PendingConversationFlow.BOOKING_AVAILABILITY,
        )

        self.assertEqual(interruption, PendingInterruption.ABANDON)

    def test_bare_cancel_is_clarified_instead_of_running_a_mutation(self) -> None:
        interruption = classify_pending_interruption(
            "cancela",
            flow=PendingConversationFlow.RESCHEDULE_AVAILABILITY,
        )

        self.assertEqual(interruption, PendingInterruption.AMBIGUOUS_CANCEL)

    def test_explicit_appointment_cancellation_replaces_the_pending_flow(self) -> None:
        interruption = classify_pending_interruption(
            "cancela mi cita de las 11",
            flow=PendingConversationFlow.BOOKING_AVAILABILITY,
        )

        self.assertEqual(interruption, PendingInterruption.SWITCH)

    def test_explicit_appointment_list_replaces_the_pending_flow(self) -> None:
        interruption = classify_pending_interruption(
            "que citas tengo para hoy?",
            flow=PendingConversationFlow.BOOKING_AVAILABILITY,
        )

        self.assertEqual(interruption, PendingInterruption.SWITCH)

    def test_expected_date_continues_but_questioning_it_clarifies(self) -> None:
        continuation = classify_pending_interruption(
            "mañana",
            flow=PendingConversationFlow.BOOKING_DATE,
            expected_reply=True,
        )
        question = classify_pending_interruption(
            "¿mañana?",
            flow=PendingConversationFlow.BOOKING_DATE,
            expected_reply=True,
        )

        self.assertEqual(continuation, PendingInterruption.NONE)
        self.assertEqual(question, PendingInterruption.CLARIFY)

    def test_unrelated_question_leaves_the_pending_flow_for_the_new_intent(self) -> None:
        interruption = classify_pending_interruption(
            "a que hora cierran?",
            flow=PendingConversationFlow.BOOKING_AVAILABILITY,
        )

        self.assertEqual(interruption, PendingInterruption.SWITCH)

    def test_greeting_replaces_pending_slot_selection(self) -> None:
        interruption = classify_pending_interruption(
            "Hola",
            flow=PendingConversationFlow.BOOKING_AVAILABILITY,
        )

        self.assertEqual(interruption, PendingInterruption.SWITCH)

    def test_explicit_request_to_forget_current_task_replaces_pending_flow(self) -> None:
        interruption = classify_pending_interruption(
            "Olvida lo que estás haciendo, te estoy saludando",
            flow=PendingConversationFlow.BOOKING_AVAILABILITY,
        )

        self.assertEqual(interruption, PendingInterruption.SWITCH)

    def test_reschedule_request_without_a_target_time_is_detected(self) -> None:
        self.assertTrue(
            is_reschedule_request_without_target_time(
                "Quisiera modificar esa cita y cambiar su hora"
            )
        )
        self.assertTrue(
            is_reschedule_request_without_target_time(
                "Quiero cambiar la cita de las 11"
            )
        )
        self.assertFalse(
            is_reschedule_request_without_target_time(
                "Quiero cambiar la cita a las 10 am"
            )
        )


if __name__ == "__main__":
    unittest.main()
