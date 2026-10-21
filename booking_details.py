"""Datos expresados por el paciente que comparten la reserva por chat y por voz."""

from dataclasses import dataclass

from appointment_reason_validation import validate_appointment_reason
from patient_name_validation import PatientNameValidationCode, validate_patient_name


@dataclass(frozen=True)
class BookingDetails:
    patient_name: str
    reason: str
    name_needs_confirmation: bool

    @classmethod
    def from_patient_texts(cls, patient_name: str, reason: str):
        name = validate_patient_name(patient_name)
        if name.code is PatientNameValidationCode.INVALID:
            raise ValueError("Solicita el nombre completo expresado por el paciente")
        validated_reason = validate_appointment_reason(reason)
        if not validated_reason.accepted:
            raise ValueError("Solicita un motivo comprensible expresado por el paciente")
        return cls(name.normalized_text, validated_reason.normalized_text,
                   name.code is PatientNameValidationCode.NEEDS_CONFIRMATION)
