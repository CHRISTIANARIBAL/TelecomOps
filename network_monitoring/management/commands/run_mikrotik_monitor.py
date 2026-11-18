
import logging

from django.core.management.base import BaseCommand

from network_monitoring.services.connection_manager import (
    MikroTikConnectionManager,
)


class Command(BaseCommand):
    help = "Run the persistent multi-device MikroTik monitoring service."

    def handle(self, *args, **options):
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s | %(levelname)s | %(message)s",
            force=True,
        )

        manager = MikroTikConnectionManager(
            discovery_interval=5,
        )

        self.stdout.write(
            self.style.SUCCESS(
                "Starting multi-device MikroTik monitoring..."
            )
        )

        self.stdout.write(
            "Discovering enabled devices from the database."
        )

        self.stdout.write(
            "Press CTRL+C to stop all connections."
        )

        try:
            manager.run_forever()

        except KeyboardInterrupt:
            self.stdout.write(
                "\nStopping all MikroTik connections..."
            )
            manager.stop_all()

        self.stdout.write(
            self.style.SUCCESS(
                "MikroTik monitoring stopped."
            )
        )
