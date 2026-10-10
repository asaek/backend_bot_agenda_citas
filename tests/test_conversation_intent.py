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

    def test_natural_booking_selections_continue_the_offered_day(self) -> None:
        for text in (
            "quisiera una cita a las 9 am",
            "quiero una cita a las 9 am",
            "necesito una cita a las 9 am",
            "deseo una cita a las 9 am",
            "me gustaría una cita a las 9 am",
            "Hola, quisiera una cita a las 9 am, por favor.",
            "quisiera reservar una cita a las 9 am",
        ):
            with self.subTest(text=text):
                self.assertEqual(
                    classify_pending_interruption(
                        text, flow=PendingConversationFlow.BOOKING_AVAILABILITY,
                        expected_reply=True,
                    ),
                    PendingInterruption.NONE,
                )

    def test_booking_selection_does_not_capture_another_day_or_task(self) -> None:
        for text, expected in (
            ("quisiera una cita a las 9 am mañana", PendingInterruption.SWITCH),
            ("quisiera otra cita a las 9 am", PendingInterruption.SWITCH),
            ("deseo una cita a las 9 am mañana", PendingInterruption.SWITCH),
            ("deseo otra cita a las 9 am", PendingInterruption.SWITCH),
            ("me gustaría una cita a las 9 am mañana", PendingInterruption.SWITCH),
            ("me gustaría otra cita a las 9 am", PendingInterruption.SWITCH),
            ("deseo agendar una cita a las 9 am mañana", PendingInterruption.SWITCH),
            ("me gustaría reservar una cita a las 9 am mañana", PendingInterruption.SWITCH),
            ("cancela mi cita de las 9 am", PendingInterruption.SWITCH),
            ("¿Cuánto cuesta una cita a las 9 am?", PendingInterruption.PAUSE),
            ("ya no quiero agendar", PendingInterruption.ABANDON),
            ("¿9 am?", PendingInterruption.CLARIFY),
        ):
            with self.subTest(text=text):
                self.assertEqual(
                    classify_pending_interruption(
                        text, flow=PendingConversationFlow.BOOKING_AVAILABILITY,
                        expected_reply=True,
                    ),
                    expected,
                )

    def test_booking_words_inside_a_cost_question_pause_instead_of_switching(self) -> None:
        for text in (
            "¿Cuál es el costo si deseo reservar una cita?",
            "¿Cuánto cuesta si me gustaría agendar una cita?",
        ):
            with self.subTest(text=text):
                self.assertEqual(
                    classify_pending_interruption(
                        text, flow=PendingConversationFlow.BOOKING_AVAILABILITY,
                    ),
                    PendingInterruption.PAUSE,
                )

    def test_unrelated_question_pauses_the_pending_flow(self) -> None:
        interruption = classify_pending_interruption(
            "a que hora cierran?",
            flow=PendingConversationFlow.BOOKING_AVAILABILITY,
        )

        self.assertEqual(interruption, PendingInterruption.PAUSE)

    def test_greeting_pauses_pending_slot_selection(self) -> None:
        interruption = classify_pending_interruption(
            "Hola",
            flow=PendingConversationFlow.BOOKING_AVAILABILITY,
        )

        self.assertEqual(interruption, PendingInterruption.PAUSE)

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

    def test_contextual_selection_does_not_capture_another_task_or_uncertain_question(self) -> None:
        cases = (
            ("Quisiera cambiar otra cita a las 12 pm", PendingInterruption.SWITCH),
            ("Quisiera cambiar la cita de las 10 a las 12 pm", PendingInterruption.SWITCH),
            ("Quisiera cambiarla a las 12 pm mañana", PendingInterruption.SWITCH),
            ("Mueve otra cita a las 12 pm", PendingInterruption.SWITCH),
            ("Ponla a las 12 pm mañana", PendingInterruption.SWITCH),
            ("Pásala a las 12 pm mañana", PendingInterruption.SWITCH),
            ("Cancela mi cita de las 12 pm", PendingInterruption.SWITCH),
            ("No la cambies a las 12 pm", PendingInterruption.ABANDON),
            ("¿Cuánto cuesta la consulta a las 12 pm?", PendingInterruption.PAUSE),
            ("¿12 pm?", PendingInterruption.CLARIFY),
        )
        for text, expected in cases:
            with self.subTest(text=text):
                self.assertEqual(
                    classify_pending_interruption(
                        text,
                        flow=PendingConversationFlow.RESCHEDULE_AVAILABILITY,
                        expected_reply=True,
                    ),
                    expected,
                )


if __name__ == "__main__":
    unittest.main()
