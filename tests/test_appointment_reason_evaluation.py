import json
import unittest

from appointment_reason_evaluation import (
    AppointmentReasonCategory,
    AppointmentReasonEvaluationError,
    AppointmentReasonQuality,
    StructuredAppointmentReasonEvaluator,
    priority_signal_messages,
    priority_signals_for_text,
)
from fakes import FakeLLMProvider


class AppointmentReasonEvaluationTests(unittest.IsolatedAsyncioTestCase):
    evaluated_at = "2026-09-25T20:00:00+00:00"

    async def test_parses_structured_llm_result(self) -> None:
        provider = FakeLLMProvider(
            reply=(
                '{"quality":"valid","category":"visual_symptom",'
                '"priority_signals":[],"confidence":0.94}'
            )
        )
        evaluator = StructuredAppointmentReasonEvaluator(provider)

        result = await evaluator.evaluate(
            "Veo borroso desde ayer",
            evaluated_at=self.evaluated_at,
        )

        self.assertEqual(result.quality, AppointmentReasonQuality.VALID)
        self.assertEqual(result.category, AppointmentReasonCategory.VISUAL_SYMPTOM)
        self.assertEqual(result.priority_signals, ())
        self.assertEqual(result.confidence, 0.94)
        self.assertTrue(result.accepted)
        self.assertEqual(result.evaluated_at, self.evaluated_at)
        self.assertEqual(provider.call_count, 1)

    async def test_does_not_call_llm_for_locally_rejected_text(self) -> None:
        provider = FakeLLMProvider(
            reply=(
                '{"quality":"valid","category":"visual_symptom",'
                '"priority_signals":[],"confidence":0.94}'
            )
        )
        evaluator = StructuredAppointmentReasonEvaluator(provider)

        result = await evaluator.evaluate(
            "jnbajnbsdijkqnbwikbdqwd",
            evaluated_at=self.evaluated_at,
        )

        self.assertEqual(result.quality, AppointmentReasonQuality.NEEDS_CLARIFICATION)
        self.assertEqual(result.category, AppointmentReasonCategory.UNKNOWN)
        self.assertFalse(result.accepted)
        self.assertEqual(provider.call_count, 0)

    async def test_priority_signals_are_kept_only_when_supported_by_the_text(self) -> None:
        provider = FakeLLMProvider(
            reply=(
                '{"quality":"valid","category":"visual_symptom",'
                '"priority_signals":["eye_pain","diagnosis_glaucoma"],'
                '"confidence":0.94}'
            )
        )
        evaluator = StructuredAppointmentReasonEvaluator(provider)

        result = await evaluator.evaluate(
            "Veo borroso desde ayer",
            evaluated_at=self.evaluated_at,
        )

        self.assertEqual(result.priority_signals, ())

    async def test_detects_supported_priority_signal_even_if_llm_omits_it(self) -> None:
        provider = FakeLLMProvider(
            reply=(
                '{"quality":"valid","category":"visual_symptom",'
                '"priority_signals":[],"confidence":0.94}'
            )
        )
        evaluator = StructuredAppointmentReasonEvaluator(provider)

        result = await evaluator.evaluate(
            "Tuve un golpe en el ojo",
            evaluated_at=self.evaluated_at,
        )

        self.assertEqual(result.priority_signals, ("ocular_trauma",))

    async def test_priority_signal_is_a_safe_operational_message(self) -> None:
        provider = FakeLLMProvider(
            reply=(
                '{"quality":"valid","category":"visual_symptom",'
                '"priority_signals":[],"confidence":0.94}'
            )
        )
        evaluator = StructuredAppointmentReasonEvaluator(provider)

        result = await evaluator.evaluate(
            "Me duele el ojo y está rojo",
            evaluated_at=self.evaluated_at,
        )

        self.assertEqual(result.priority_signals, ("eye_pain",))
        self.assertEqual(
            priority_signal_messages(result.priority_signals),
            (
                "El paciente refiere dolor ocular que podría requerir atención "
                "prioritaria.",
            ),
        )
        self.assertNotIn("glaucoma", priority_signal_messages(result.priority_signals)[0].lower())
        self.assertNotIn(
            "desprendimiento",
            priority_signal_messages(result.priority_signals)[0].lower(),
        )

    async def test_detects_red_eyes_even_if_the_llm_omits_the_signal(self) -> None:
        evaluator = StructuredAppointmentReasonEvaluator(
            FakeLLMProvider(
                reply=(
                    '{"quality":"valid","category":"visual_symptom",'
                    '"priority_signals":[],"confidence":0.94}'
                )
            )
        )

        result = await evaluator.evaluate(
            "Tengo los ojos rojos",
            evaluated_at=self.evaluated_at,
        )

        self.assertEqual(result.priority_signals, ("eye_redness",))
        self.assertEqual(
            priority_signal_messages(result.priority_signals),
            (
                "El paciente refiere ojos rojos que podrían requerir atención "
                "prioritaria.",
            ),
        )

    async def test_diagnostic_words_from_the_llm_are_not_priority_signals(self) -> None:
        provider = FakeLLMProvider(
            reply=(
                '{"quality":"valid","category":"visual_symptom",'
                '"priority_signals":["glaucoma","desprendimiento"],'
                '"confidence":0.94}'
            )
        )
        evaluator = StructuredAppointmentReasonEvaluator(provider)

        result = await evaluator.evaluate(
            "Me duele el ojo y está rojo",
            evaluated_at=self.evaluated_at,
        )

        self.assertEqual(result.priority_signals, ("eye_pain",))

    def test_priority_patterns_cover_the_requested_patient_messages(self) -> None:
        cases = (
            ("Perdí repentinamente la visión.", "sudden_vision_loss"),
            ("Tengo dolor ocular intenso.", "eye_pain"),
            ("Tengo los ojos rojos.", "eye_redness"),
            ("Recibí un golpe en el ojo.", "ocular_trauma"),
            ("Me cayó cloro en el ojo.", "chemical_exposure"),
            ("Tengo sangrado en el ojo.", "ocular_bleeding"),
            ("Veo destellos.", "flashes_or_floaters"),
            ("Tengo alteraciones visuales importantes.", "significant_visual_change"),
        )

        for text, expected_signal in cases:
            with self.subTest(text=text):
                self.assertIn(expected_signal, priority_signals_for_text(text))

    async def test_eye_discharge_variants_are_detected_even_when_the_llm_omits_them(self) -> None:
        cases = (
            "Tengo laga;as muy amarillentas y grandes en los ojos",
            "Tengo legañas amarillas",
            "Tengo lagañas muy abundantes",
            "Tengo secreción ocular verdosa",
        )
        for reason in cases:
            with self.subTest(reason=reason):
                provider = FakeLLMProvider(
                    reply='{"quality":"valid","category":"visual_symptom",'
                    '"priority_signals":[],"confidence":0.94}'
                )
                result = await StructuredAppointmentReasonEvaluator(provider).evaluate(
                    reason, evaluated_at=self.evaluated_at
                )
                self.assertEqual(result.priority_signals, ("ocular_discharge",))
                self.assertTrue(result.accepted)

    async def test_semantic_reason_signal_is_kept_with_literal_evidence(self) -> None:
        reason = "Desde hace una hora todo se volvió negro y apenas distingo las cosas"
        provider = FakeLLMProvider(
            reply=json.dumps(
                {
                    "quality": "valid",
                    "category": "visual_symptom",
                    "priority_signals": ["sudden_vision_loss"],
                    "priority_signal_evidence": [
                        {"signal": "sudden_vision_loss", "quote": reason}
                    ],
                    "confidence": 0.94,
                }
            )
        )
        result = await StructuredAppointmentReasonEvaluator(provider).evaluate(
            reason, evaluated_at=self.evaluated_at
        )

        self.assertEqual(result.priority_signals, ("sudden_vision_loss",))

    def test_denied_and_unqualified_symptoms_do_not_raise_priority(self) -> None:
        for text in (
            "No tengo dolor ocular",
            "Sin ojos rojos ni sangrado ocular",
            "Tengo pocas lagañas al despertar",
            "No tengo secreción ocular amarillenta",
        ):
            with self.subTest(text=text):
                self.assertEqual(priority_signals_for_text(text), ())
        self.assertEqual(
            priority_signals_for_text("No tengo dolor, pero tengo los ojos rojos"),
            ("eye_redness",),
        )
        self.assertIn("sudden_vision_loss", priority_signals_for_text("No puedo ver"))
        self.assertEqual(
            priority_signals_for_text("Tengo dolor ocular sin sangrado"), ("eye_pain",)
        )

    async def test_low_confidence_result_does_not_authorize_creation(self) -> None:
        provider = FakeLLMProvider(
            reply=(
                '{"quality":"valid","category":"visual_symptom",'
                '"priority_signals":[],"confidence":0.60}'
            )
        )
        evaluator = StructuredAppointmentReasonEvaluator(provider)

        result = await evaluator.evaluate(
            "Consulta por mi vista",
            evaluated_at=self.evaluated_at,
        )

        self.assertEqual(result.quality, AppointmentReasonQuality.VALID)
        self.assertFalse(result.accepted)

    async def test_invalid_llm_payload_is_rejected(self) -> None:
        evaluator = StructuredAppointmentReasonEvaluator(
            FakeLLMProvider(reply="No puedo clasificarlo")
        )

        with self.assertRaises(AppointmentReasonEvaluationError):
            await evaluator.evaluate(
                "Consulta por mi vista",
                evaluated_at=self.evaluated_at,
            )
