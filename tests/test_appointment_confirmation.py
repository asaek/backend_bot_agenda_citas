import unittest

from appointment_confirmation import ConfirmationDecision, classify_action_confirmation, classify_confirmation
from calendar_domain import ToolName


class AppointmentConfirmationTests(unittest.TestCase):
    def test_stage_one_affirmatives_are_complete_contextual_responses(self) -> None:
        for tool_name in (ToolName.RESCHEDULE_APPOINTMENT, ToolName.CANCEL_APPOINTMENT):
            for reply in (
                "Sí es correcto", "SI, ES CORRECTO!!", "¡si es correcto!",
                "sí está bien.", "Correcto, por favor", "Correcto, sí está bien",
            ):
                with self.subTest(tool_name=tool_name, reply=reply):
                    self.assertEqual(
                        classify_action_confirmation(reply, tool_name=tool_name),
                        ConfirmationDecision.CONFIRMED,
                    )

    def test_stage_one_conditions_and_other_references_cannot_confirm_an_action(self) -> None:
        for reply in (
            "Sí, si está bien", "Sí, si es correcto", "Correcto, si es correcto",
            "Sí, si quiero", "Sí, si deseo",
            "Sí, si no cambia la fecha", "Sí, si el precio está bien",
            "Sí, pero mejor no", "¿Sí es correcto?", "Sí es correcto para mañana",
            "Sí es correcto para la otra cita",
        ):
            with self.subTest(reply=reply):
                self.assertNotEqual(
                    classify_action_confirmation(reply, tool_name=ToolName.RESCHEDULE_APPOINTMENT),
                    ConfirmationDecision.CONFIRMED,
                )
        self.assertIsNone(classify_action_confirmation(
            "¿Cuánto cuesta si deseo reservar una cita?",
            tool_name=ToolName.RESCHEDULE_APPOINTMENT,
        ))

    def test_accepts_affirmative_with_polite_request(self) -> None:
        self.assertEqual(
            classify_confirmation("Sí, por favor"),
            ConfirmationDecision.CONFIRMED,
        )

    def test_accepts_natural_affirmatives(self) -> None:
        for reply in (
            "Claro, adelante",
            "Por supuesto, gracias",
            "De acuerdo, muchas gracias",
            "Sí, hazlo por favor",
        ):
            with self.subTest(reply=reply):
                self.assertEqual(
                    classify_confirmation(reply),
                    ConfirmationDecision.CONFIRMED,
                )

    def test_accepts_negative_with_politeness(self) -> None:
        for reply in ("No, gracias", "Mejor no, por favor"):
            with self.subTest(reply=reply):
                self.assertEqual(
                    classify_confirmation(reply),
                    ConfirmationDecision.REJECTED,
                )

    def test_keeps_uncertain_or_conflicting_replies_ambiguous(self) -> None:
        for reply in (
            "No estoy seguro, creo que sí",
            "Sí, pero mejor no",
            "Tal vez",
        ):
            with self.subTest(reply=reply):
                self.assertEqual(
                    classify_confirmation(reply),
                    ConfirmationDecision.UNKNOWN,
                )
