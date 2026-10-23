"""Mapeo explicito entre datos del aviso y componentes de una plantilla de Meta."""

import json
import re
from collections.abc import Mapping
from string import Formatter
from typing import Any


NOTICE_FIELDS = frozenset({
    "event_type", "status", "date", "time", "reason", "patient_name",
    "patient_phone", "summary", "priority_signals",
})
TEMPLATE_FIELDS = NOTICE_FIELDS | {"notification_body"}
PENDING_TEMPLATE_MAPPING = "Mapeo de plantilla pendiente."
INVALID_TEMPLATE_MAPPING = "Mapeo de plantilla no válido."
MISSING_TEMPLATE_DATA = "Datos de plantilla no disponibles para este aviso."


class TemplateMappingError(ValueError):
    """Error estable sin valores de configuracion ni datos del paciente."""


def load_template_components(raw: str) -> list[dict[str, Any]]:
    if not raw.strip():
        raise TemplateMappingError(PENDING_TEMPLATE_MAPPING)
    try:
        components = json.loads(raw)
        if not isinstance(components, list) or not components:
            raise ValueError
        sources: set[str] = set()
        seen = set()
        for component in components:
            if not isinstance(component, dict):
                raise ValueError
            kind = component.get("type")
            allowed = {"type", "parameters"}
            if kind == "button":
                allowed |= {"sub_type", "index"}
                if component.get("sub_type") != "url" or not isinstance(component.get("index"), str):
                    raise ValueError
                if not re.fullmatch(r"[0-9]+", component["index"]):
                    raise ValueError
            elif kind not in {"header", "body"}:
                raise ValueError
            identity = (kind, component.get("index"))
            if set(component) - allowed or identity in seen:
                raise ValueError
            seen.add(identity)
            parameters = component.get("parameters")
            if not isinstance(parameters, list) or not parameters:
                raise ValueError
            for parameter in parameters:
                if not isinstance(parameter, dict) or set(parameter) - {"type", "text", "parameter_name"}:
                    raise ValueError
                if parameter.get("type") != "text" or not isinstance(parameter.get("text"), str) or not parameter["text"].strip():
                    raise ValueError
                if "parameter_name" in parameter and (not isinstance(parameter["parameter_name"], str) or not parameter["parameter_name"].strip()):
                    raise ValueError
                for _, field_name, spec, conversion in Formatter().parse(parameter["text"]):
                    if field_name is not None:
                        if field_name not in TEMPLATE_FIELDS or spec or conversion:
                            raise ValueError
                        sources.add(field_name)
        # La cantidad y agrupacion son explicitas; el mapeo no debe perder datos del aviso.
        if "notification_body" not in sources and not NOTICE_FIELDS.issubset(sources):
            raise ValueError
        return components
    except (ValueError, TypeError, KeyError, RecursionError):
        raise TemplateMappingError(INVALID_TEMPLATE_MAPPING) from None


def build_template_components(raw: str, data: Mapping[str, str]) -> list[dict[str, Any]]:
    components = load_template_components(raw)
    try:
        for component in components:
            for parameter in component["parameters"]:
                fields = [name for _, name, _, _ in Formatter().parse(parameter["text"]) if name is not None]
                if any(not isinstance(data.get(name), str) for name in fields):
                    raise ValueError
                # Meta no admite saltos/tabuladores en los parametros de texto.
                value = " ".join(parameter["text"].format_map(data).split())
                if not value:
                    raise ValueError
                parameter["text"] = value
        return components
    except (ValueError, TypeError, KeyError):
        raise TemplateMappingError(MISSING_TEMPLATE_DATA) from None
