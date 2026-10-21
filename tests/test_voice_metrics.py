import unittest

from voice_metrics import VoiceMetrics, estimated_cost


class VoiceMetricsTests(unittest.TestCase):
    def test_separates_first_received_from_emitted_and_excludes_tool_turns(self):
        now = [10.0]
        metrics = VoiceMetrics(clock=lambda: now[0])
        metrics.speech_stopped("input")
        now[0] = 10.5
        metrics.committed(1, "input")
        now[0] = 11.0
        metrics.audio(1)
        now[0] = 11.5
        metrics.audio(1)  # Otro fragmento no cambia el primero.
        metrics.audio(1, emitted_at=11.2)
        metrics.committed(2, "tool-input")
        started = metrics.tool_started(2)
        now[0] = 12
        metrics.tool_finished(2, "check_availability", started)
        metrics.audio(2)
        metrics.audio(0)  # El saludo no es una respuesta a una intervencion.
        snapshot = metrics.snapshot()
        self.assertEqual(snapshot["turns"][0]["first_audio_received_ms"], 1000)
        self.assertEqual(snapshot["turns"][0]["first_audio_emitted_ms"], 1200)
        self.assertEqual(snapshot["without_tools"]["first_audio_received_ms"], {"samples": 1, "p50_ms": 1000, "p95_ms": 1000})
        self.assertEqual(snapshot["tools"][0]["duration_ms"], 500)
        self.assertEqual(snapshot["turns"][1]["reference"], "committed_received")

    def test_empty_or_interrupted_turns_do_not_become_zero_latency_samples(self):
        metrics = VoiceMetrics()
        metrics.committed(1, "silent")
        self.assertIsNone(metrics.snapshot()["without_tools"]["first_audio_received_ms"]["p50_ms"])
        self.assertEqual(metrics.snapshot()["without_tools"]["first_audio_emitted_ms"]["samples"], 0)

    def test_cost_includes_cache_modalities_and_separate_transcription(self):
        usage = {"responses": [{"model": "gpt-realtime-2.1", "usage": {
            "input_tokens": 1000, "output_tokens": 200,
            "input_token_details": {"text_tokens": 400, "audio_tokens": 600, "cached_tokens": 200,
                "cached_tokens_details": {"text_tokens": 50, "audio_tokens": 150}},
            "output_token_details": {"text_tokens": 50, "audio_tokens": 150}}}],
            "transcriptions": [{"model": "gpt-4o-mini-transcribe", "usage": {"input_tokens": 100, "output_tokens": 20,
                "input_token_details": {"audio_tokens": 95, "text_tokens": 5}}}]}
        result = estimated_cost(usage)
        self.assertTrue(result["complete"])
        self.assertAlmostEqual(result["realtime_usd"], .02668)
        self.assertAlmostEqual(result["transcription_usd"], .000225)
        self.assertAlmostEqual(result["total_usd"], .026905)
        self.assertIsNone(estimated_cost(usage, missing_records=1)["total_usd"])

    def test_unconfigured_model_or_missing_detail_is_not_reported_as_free(self):
        for record in ({"model": "other-model", "usage": {"input_tokens": 100}},
                       {"model": "gpt-realtime-2.1", "usage": {"input_tokens": 100}}):
            result = estimated_cost({"responses": [record], "transcriptions": []})
            self.assertFalse(result["complete"])
            self.assertIsNone(result["total_usd"])
            self.assertEqual(result["unpriced_records"], 1)

    def test_missing_cache_or_transcription_modalities_leaves_total_unknown(self):
        response = {"model": "gpt-realtime-2.1", "usage": {"input_tokens": 100, "output_tokens": 20,
            "input_token_details": {"audio_tokens": 80, "text_tokens": 20},
            "output_token_details": {"audio_tokens": 15, "text_tokens": 5}}}
        transcription = {"model": "gpt-4o-mini-transcribe", "usage": {"input_tokens": 100, "output_tokens": 20}}
        result = estimated_cost({"responses": [response], "transcriptions": [transcription]})
        self.assertFalse(result["complete"])
        self.assertIsNone(result["total_usd"])
        self.assertEqual(result["unpriced_records"], 2)
