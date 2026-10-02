import unittest

from appointment_confirmation import ConfirmationDecision, classify_confirmation


class AppointmentConfirmationTests(unittest.TestCase):
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
