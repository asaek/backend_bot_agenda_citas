"""Conciliacion explicita de un aviso con evidencia externa, sin enviar mensajes."""

import argparse
import json
import sys
from contextlib import contextmanager
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from notification_delivery import DoctorNotificationDeliveryService, DoctorNotificationSettings
from notification_statuses import target_connection


class ExistingNotificationDatabase:
    def __init__(self, path):
        self.path = Path(path).resolve()

    @contextmanager
    def transaction(self):
        # La base de voz debe conservar su esquema exclusivo, sin tablas de pacientes.
        with target_connection(self.path) as db:
            if db is None:
                raise ValueError("La base no contiene una bandeja de notificaciones")
            with db:
                yield db


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", required=True)
    parser.add_argument("--notification-id", required=True, type=int)
    parser.add_argument("--attempt", required=True, type=int)
    parser.add_argument("--outcome", required=True, choices=("accepted", "not_delivered", "configuration_fixed"))
    parser.add_argument("--reason", required=True, help="Referencia tecnica a la comprobacion externa; sin datos del paciente")
    parser.add_argument("--provider-message-id")
    args = parser.parse_args()
    if not Path(args.database).is_file():
        parser.error("La base debe existir")
    service = DoctorNotificationDeliveryService(ExistingNotificationDatabase(args.database), None, DoctorNotificationSettings(False, ()))
    try:
        result = service.reconcile(args.notification_id, attempt_number=args.attempt,
            outcome=args.outcome, reason=args.reason, provider_message_id=args.provider_message_id)
    except ValueError as error:
        parser.error(str(error))
    print(json.dumps({"notification_id": result.id, "dispatch_status": result.status,
                      "delivery_status": result.delivery_status, "attempt_count": result.attempt_count}))


if __name__ == "__main__":
    main()
