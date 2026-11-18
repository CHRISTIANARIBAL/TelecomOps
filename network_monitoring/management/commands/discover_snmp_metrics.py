
import asyncio

from django.core.management.base import BaseCommand, CommandError

from pysnmp.hlapi.v3arch.asyncio import (
    SnmpEngine,
    UsmUserData,
    UdpTransportTarget,
    ContextData,
    ObjectType,
    ObjectIdentity,
    get_cmd,
    next_cmd,
    usmHMACSHAAuthProtocol,
    usmAesCfb128Protocol,
)

from network_monitoring.models import MikroTikDevice


CPU_TABLE = "1.3.6.1.2.1.25.3.3.1.2"

MEMORY_TABLE = "1.3.6.1.2.1.25.2.3.1"

HEALTH_OIDS = {
    "Board temperature": "1.3.6.1.4.1.14988.1.1.3.10.0",
    "Processor temperature": "1.3.6.1.4.1.14988.1.1.3.11.0",
    "Memory health value": "1.3.6.1.4.1.14988.1.1.3.12.0",
    "Storage usage": "1.3.6.1.4.1.14988.1.1.3.13.0",
}

MEMORY_COLUMNS = {
    "1": "Index",
    "2": "Type",
    "3": "Description",
    "4": "Allocation units",
    "5": "Size",
    "6": "Used",
}


class Command(BaseCommand):
    help = "Discover actual SNMP metrics exposed by a MikroTik device."

    def add_arguments(self, parser):
        parser.add_argument("device_id", type=int)

    def handle(self, *args, **options):
        try:
            device = MikroTikDevice.objects.get(
                pk=options["device_id"]
            )
        except MikroTikDevice.DoesNotExist:
            raise CommandError("Device does not exist.")

        if not device.snmp_enabled:
            raise CommandError("SNMP is disabled for this device.")

        connection = None

        try:
            connection = {
                "host": device.host,
                "username": device.snmp_username,
                "auth": device.get_snmp_auth_password(),
                "priv": device.get_snmp_priv_password(),
                "port": device.snmp_port,
            }

            if not connection["auth"] or not connection["priv"]:
                raise CommandError("SNMP credentials are incomplete.")

            asyncio.run(self.discover(connection))

        except CommandError:
            raise
        except Exception as exc:
            raise CommandError(
                f"SNMP discovery failed: {exc}"
            ) from exc

    async def discover(self, device):
        engine = SnmpEngine()

        try:
            auth = UsmUserData(
                device["username"],
                device["auth"],
                device["priv"],
                authProtocol=usmHMACSHAAuthProtocol,
                privProtocol=usmAesCfb128Protocol,
            )

            target = await UdpTransportTarget.create(
                (device["host"], device["port"]),
                timeout=3,
                retries=1,
            )

            context = ContextData()

            self.stdout.write(
                self.style.SUCCESS(
                    f"\nSNMP discovery: {device['host']}"
                )
            )

            await self.walk_table(
                engine, auth, target, context,
                "CPU PROCESSOR TABLE", CPU_TABLE
            )

            await self.walk_table(
                engine, auth, target, context,
                "MEMORY STORAGE TABLE", MEMORY_TABLE
            )

            self.stdout.write("\nMIKROTIK HEALTH VALUES")

            health_objects = [
                ObjectType(ObjectIdentity(oid))
                for oid in HEALTH_OIDS.values()
            ]

            (
                error,
                status,
                index,
                bindings,
            ) = await get_cmd(
                engine,
                auth,
                target,
                context,
                *health_objects,
                lookupMib=False,
            )

            if error:
                self.stdout.write(f"Health GET error: {error}")
            elif status:
                self.stdout.write(
                    f"Health GET status: {status.prettyPrint()}"
                )
            else:
                labels = {
                    oid: label
                    for label, oid in HEALTH_OIDS.items()
                }

                for oid, value in bindings:
                    self.stdout.write(
                        f"{labels.get(str(oid), str(oid))}: "
                        f"{value.prettyPrint()} "
                        f"[{oid}]"
                    )

        finally:
            engine.close_dispatcher()

    
    async def walk_table(
        self, engine, auth, target, context, title, base_oid
    ):
        self.stdout.write(f"\n{title}")

        current_oid = base_oid
        found = False

        while True:
            (
                error,
                status,
                index,
                bindings,
            ) = await next_cmd(
                engine,
                auth,
                target,
                context,
                ObjectType(ObjectIdentity(current_oid)),
                lexicographicMode=False,
                lookupMib=False,
            )

            if error:
                self.stdout.write(f"Walk error: {error}")
                return

            if status:
                self.stdout.write(
                    f"SNMP error: {status.prettyPrint()}"
                )
                return

            if not bindings:
                break

            stop_walk = False

            for oid, value in bindings:
                oid_string = str(oid)

                # Stop if the returned OID is outside the table.
                if not oid_string.startswith(base_oid + "."):
                    stop_walk = True
                    break

                found = True

                self.stdout.write(
                    f"{oid_string} = {value.prettyPrint()}"
                )

                current_oid = oid_string

            if stop_walk:
                break

        if not found:
            self.stdout.write("No entries returned.")

