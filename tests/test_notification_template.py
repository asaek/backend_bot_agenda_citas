import json
import unittest

from notification_template import TemplateMappingError, build_template_components, load_template_components


class TemplateMappingTests(unittest.TestCase):
    def test_preserves_component_order_named_parameters_and_literal_braces(self):
        raw = json.dumps([
            {"type": "header", "parameters": [{"type": "text", "text": "Aviso"}]},
            {"type": "body", "parameters": [{"type": "text", "parameter_name": "aviso", "text": "{{CITA}} {notification_body}"}]},
            {"type": "button", "sub_type": "url", "index": "0", "parameters": [{"type": "text", "text": "detalle"}]},
        ])
        components = build_template_components(raw, {"notification_body": "Nombre: Ana\n\tEstado: confirmada"})
        self.assertEqual(components[1]["parameters"][0], {"type": "text", "parameter_name": "aviso", "text": "{CITA} Nombre: Ana Estado: confirmada"})
        self.assertEqual(components[2]["index"], "0")
        self.assertEqual(load_template_components(raw)[1]["parameters"][0]["text"], "{{CITA}} {notification_body}")

    def test_missing_or_invalid_mapping_has_a_stable_error_without_configuration_values(self):
        for raw, reason in (("", "Mapeo de plantilla pendiente."), ("[]", "Mapeo de plantilla no válido."),
                            ("invalid-secret-value", "Mapeo de plantilla no válido.")):
            with self.subTest(raw=raw):
                with self.assertRaises(TemplateMappingError) as caught:
                    load_template_components(raw)
                self.assertEqual(str(caught.exception), reason)

    def test_rejects_unknown_sources_expressions_or_a_mapping_that_drops_notice_fields(self):
        for value in ("{unknown}", "{patient_name}", "{notification_body.__class__}",
                      "{notification_body!r}", "{notification_body:>20}", "{notification_body"):
            with self.subTest(value=value):
                raw = json.dumps([{"type": "body", "parameters": [{"type": "text", "text": value}]}])
                with self.assertRaises(TemplateMappingError):
                    load_template_components(raw)

    def test_missing_source_data_cannot_be_substituted_with_invented_values(self):
        raw = json.dumps([{"type": "body", "parameters": [{"type": "text", "text": "{notification_body}"}]}])
        with self.assertRaises(TemplateMappingError) as caught:
            build_template_components(raw, {})
        self.assertEqual(str(caught.exception), "Datos de plantilla no disponibles para este aviso.")
