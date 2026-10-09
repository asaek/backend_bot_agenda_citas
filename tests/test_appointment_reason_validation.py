import unittest

from appointment_reason_validation import (
    AppointmentReasonValidationCode,
    validate_appointment_reason,
)


class AppointmentReasonValidationTests(unittest.TestCase):
    def test_normalizes_whitespace_without_rewriting_the_patient_text(self) -> None:
        result = validate_appointment_reason("  Me   duele\t el ojo  ")

        self.assertTrue(result.accepted)
        self.assertEqual(result.code, AppointmentReasonValidationCode.ACCEPTED)
        self.assertEqual(result.normalized_text, "Me duele el ojo")

    def test_accepts_short_but_meaningful_eye_reason(self) -> None:
        result = validate_appointment_reason("ojo")

        self.assertTrue(result.accepted)
        self.assertEqual(result.code, AppointmentReasonValidationCode.ACCEPTED)

    def test_accepts_free_text_with_accents_and_punctuation(self) -> None:
        result = validate_appointment_reason("Visión borrosa desde ayer.")

        self.assertTrue(result.accepted)
        self.assertEqual(result.code, AppointmentReasonValidationCode.ACCEPTED)

    def test_rejects_empty_text(self) -> None:
        result = validate_appointment_reason("   ")

        self.assertFalse(result.accepted)
        self.assertEqual(result.code, AppointmentReasonValidationCode.EMPTY)

    def test_rejects_text_without_letters(self) -> None:
        result = validate_appointment_reason("12345 😵")

        self.assertFalse(result.accepted)
        self.assertEqual(result.code, AppointmentReasonValidationCode.NO_LETTERS)

    def test_rejects_too_short_text(self) -> None:
        result = validate_appointment_reason("ok")

        self.assertFalse(result.accepted)
        self.assertEqual(result.code, AppointmentReasonValidationCode.TOO_SHORT)

    def test_rejects_keyboard_smash_text(self) -> None:
        result = validate_appointment_reason("asdfgh")

        self.assertFalse(result.accepted)
        self.assertEqual(
            result.code,
            AppointmentReasonValidationCode.LIKELY_GIBBERISH,
        )

    def test_rejects_long_low_vowel_noise(self) -> None:
        result = validate_appointment_reason("jnbajnbsdijkqnbwikbdqwd")

        self.assertFalse(result.accepted)
        self.assertEqual(
            result.code,
            AppointmentReasonValidationCode.LIKELY_GIBBERISH,
        )

    def test_rejects_vague_reference_without_a_reason(self) -> None:
        result = validate_appointment_reason("Lo de siempre")

        self.assertFalse(result.accepted)
        self.assertEqual(
            result.code,
            AppointmentReasonValidationCode.AMBIGUOUS,
        )

    def test_does_not_reject_valid_long_medical_word(self) -> None:
        result = validate_appointment_reason("Seguimiento de queratocono")

        self.assertTrue(result.accepted)
        self.assertEqual(result.code, AppointmentReasonValidationCode.ACCEPTED)

    def test_habitual_reference_does_not_hide_a_meaningful_reason(self) -> None:
        for text in ("Tengo molestias en la vista, como siempre",
                     "Lo de siempre: revisión de córnea"):
            with self.subTest(text=text):
                self.assertTrue(validate_appointment_reason(text).accepted)
        for text in ("Es lo de siempre.", "Lo mismo de siempre", "Como siempre",
                     "Es por lo de siempre", "Lo de siempre, por favor"):
            with self.subTest(text=text):
                self.assertEqual(
                    validate_appointment_reason(text).code,
                    AppointmentReasonValidationCode.AMBIGUOUS,
                )
