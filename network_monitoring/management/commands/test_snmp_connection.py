
from django.core.management.base import BaseCommand, CommandError

from network_monitoring.models import MikroTikDevice
from network_monitoring.services.snmp_connection import (
    MikroTikSNMPConnection,
)


class Command(BaseCommand):
    help = "Test SNMPv3 connectivity and retrieve device metrics."

    def add_arguments(self, parser):
        parser.add_argument(
            "device_id",
            type=int,
            help="ID of the registered MikroTik device.",
        )

    def handle(self, *args, **options):
        device_id = options["device_id"]

        try:
            device = MikroTikDevice.objects.get(pk=device_id)
        except MikroTikDevice.DoesNotExist:
            raise CommandError(
                f"MikroTik device with ID {device_id} does not exist."
            )

        if not device.snmp_enabled:
            raise CommandError(
                f"SNMP monitoring is disabled for {device.name}."
            )

        if not device.snmp_username:
            raise CommandError("SNMPv3 username is missing.")

        connection = None

        try:
            auth_password = device.get_snmp_auth_password()
            privacy_password = device.get_snmp_priv_password()

            if not auth_password or not privacy_password:
                raise CommandError(
                    "SNMP authentication or privacy credentials are missing."
                )

            connection = MikroTikSNMPConnection(
                host=device.host,
                username=device.snmp_username,
                auth_password=auth_password,
                privacy_password=privacy_password,
                port=device.snmp_port,
            )

            self.stdout.write(
                f"Testing SNMPv3 connection to {device.name} "
                f"({device.host})..."
            )

            metrics = connection.get_metrics()

            self.stdout.write("")
            self.stdout.write(
                self.style.SUCCESS("SNMPv3 connection successful!")
            )

            self.stdout.write("\nDEVICE INFORMATION")
            self.stdout.write(
                f"Router Identity: {metrics['identity'] or 'Unavailable'}"
            )
            self.stdout.write(
                f"Router Description: {metrics['description'] or 'Unavailable'}"
            )

            uptime = metrics["uptime_seconds"]

            if uptime is not None:
                days = int(uptime // 86400)
                hours = int((uptime % 86400) // 3600)
                minutes = int((uptime % 3600) // 60)

                self.stdout.write(
                    f"Router Uptime: {days} days, "
                    f"{hours} hours, {minutes} minutes"
                )
            else:
                self.stdout.write("Router Uptime: Unavailable")

            self.stdout.write("\nSYSTEM METRICS")

            cpu = metrics["cpu_usage_percent"]
            cpu_cores = metrics["cpu_core_count"]

            memory = metrics["memory_usage_percent"]
            memory_total = metrics["memory_total_bytes"]
            memory_used = metrics["memory_used_bytes"]
            memory_free = metrics["memory_free_bytes"]

            temperature = metrics["temperature_celsius"]
            temperature_sensor = metrics["temperature_sensor"]

            self.stdout.write(
                f"CPU Usage: {cpu}% ({cpu_cores} processor(s))"
                if cpu is not None
                else "CPU Usage: Unsupported / Unavailable"
            )

            self.stdout.write(
                f"Memory Usage: {memory}%"
                if memory is not None
                else "Memory Usage: Unsupported / Unavailable"
            )

            if memory_total is not None:
                self.stdout.write(
                    f"Memory Total: {memory_total / (1024 ** 2):.2f} MB"
                )
                self.stdout.write(
                    f"Memory Used: {memory_used / (1024 ** 2):.2f} MB"
                )
                self.stdout.write(
                    f"Memory Free: {memory_free / (1024 ** 2):.2f} MB"
                )

            if temperature is not None:
                sensor_label = (temperature_sensor or "unknown").title()

                self.stdout.write(
                    f"Temperature Sensor: {sensor_label}"
                )
                self.stdout.write(
                    f"Temperature: {temperature:.1f} °C"
                )
            else:
                self.stdout.write(
                    "Temperature: Unsupported / Unavailable"
                )

            self.stdout.write("\nMETRIC AVAILABILITY")

            for metric, available in metrics["availability"].items():
                status = (
                    self.style.SUCCESS("Available")
                    if available
                    else self.style.WARNING("Unavailable")
                )

                self.stdout.write(f"{metric.title()}: {status}")

        except CommandError:
            raise

        except Exception as exc:
            raise CommandError(
                f"SNMPv3 connection test failed: {exc}"
            ) from exc

        finally:
            if connection is not None:
                connection.close()
