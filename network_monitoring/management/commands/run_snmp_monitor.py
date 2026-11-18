
import logging

from django.core.management.base import BaseCommand

from network_monitoring.services.snmp_manager import MikroTikSNMPManager


class Command(BaseCommand):
    help = "Run the persistent multi-device MikroTik SNMP monitoring service."

    def handle(self, *args, **options):

        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s | %(levelname)s | %(message)s",
            force=True,
        )

        manager = MikroTikSNMPManager(
            discovery_interval=5,
        )

        self.stdout.write(
            self.style.SUCCESS(
                "Starting multi-device MikroTik SNMP monitoring..."
            )
        )

        self.stdout.write(
            "Discovering SNMP-enabled devices from the database."
        )

        self.stdout.write(
            "Polling interval: 30 seconds."
        )

        self.stdout.write(
            "Press CTRL+C to stop all SNMP workers."
        )

        try:
            manager.run_forever()

        except KeyboardInterrupt:
            self.stdout.write(
                "\nStopping all SNMP monitoring workers..."
            )

            manager.stop_all()

        self.stdout.write(
            self.style.SUCCESS(
                "MikroTik SNMP monitoring stopped."
            )
        )
