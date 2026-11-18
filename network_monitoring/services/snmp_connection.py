
import asyncio
import logging
import threading

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

logger = logging.getLogger(__name__)


class MikroTikSNMPConnection:
    """
    Reusable SNMPv3 connection resources.

    One connection instance belongs to one worker thread.
    The event loop, SNMP engine and UDP transport are reused.
    """

    OIDS = {
        "identity": "1.3.6.1.2.1.1.5.0",
        "description": "1.3.6.1.2.1.1.1.0",
        "uptime": "1.3.6.1.2.1.1.3.0",

        # MikroTik temperature sensors
        "board_temperature": "1.3.6.1.4.1.14988.1.1.3.10.0",
        "processor_temperature": "1.3.6.1.4.1.14988.1.1.3.11.0",
    }

    # HOST-RESOURCES-MIB: hrProcessorLoad
    CPU_LOAD_BASE = "1.3.6.1.2.1.25.3.3.1.2"

    # HOST-RESOURCES-MIB: hrStorageDescr
    STORAGE_DESCR_BASE = "1.3.6.1.2.1.25.2.3.1.3"

    # HOST-RESOURCES-MIB: hrStorageAllocationUnits
    STORAGE_ALLOCATION_UNITS_BASE = "1.3.6.1.2.1.25.2.3.1.4"

    # HOST-RESOURCES-MIB: hrStorageSize
    STORAGE_SIZE_BASE = "1.3.6.1.2.1.25.2.3.1.5"

    # HOST-RESOURCES-MIB: hrStorageUsed
    STORAGE_USED_BASE = "1.3.6.1.2.1.25.2.3.1.6"

    def __init__(
        self,
        host,
        username,
        auth_password,
        privacy_password,
        port=161,
        timeout=3,
        retries=1,
    ):
        self.host = host
        self.username = username
        self.auth_password = auth_password
        self.privacy_password = privacy_password
        self.port = port
        self.timeout = timeout
        self.retries = retries

        self.loop = None
        self.snmp_engine = None
        self.transport_target = None

        self.owner_thread_id = None
        self.closed = False

    def _initialize(self):
        if self.closed:
            raise RuntimeError("SNMP connection has been closed.")

        current_thread_id = threading.get_ident()

        if (
            self.owner_thread_id is not None
            and self.owner_thread_id != current_thread_id
        ):
            raise RuntimeError(
                "SNMP connection cannot be used from another thread."
            )

        if self.loop is not None:
            if self.loop.is_closed():
                raise RuntimeError("SNMP event loop is already closed.")
            return

        self.owner_thread_id = current_thread_id
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)

        try:
            self.snmp_engine = SnmpEngine()

            self.transport_target = self.loop.run_until_complete(
                UdpTransportTarget.create(
                    (self.host, self.port),
                    timeout=self.timeout,
                    retries=self.retries,
                )
            )

            logger.info("SNMP resources initialized: %s", self.host)

        except Exception:
            self.close()
            raise

    def _build_auth(self):
        return UsmUserData(
            userName=self.username,
            authKey=self.auth_password,
            privKey=self.privacy_password,
            authProtocol=usmHMACSHAAuthProtocol,
            privProtocol=usmAesCfb128Protocol,
        )

    async def _get_values(self, oids):
        """GET several scalar OIDs in one SNMP request."""
        objects = [
            ObjectType(ObjectIdentity(oid))
            for oid in oids
        ]

        (
            error_indication,
            error_status,
            error_index,
            var_binds,
        ) = await get_cmd(
            self.snmp_engine,
            self._build_auth(),
            self.transport_target,
            ContextData(),
            *objects,
            lookupMib=False,
        )

        if error_indication:
            raise ConnectionError(str(error_indication))

        if error_status:
            raise RuntimeError(
                f"SNMP error: {error_status.prettyPrint()} "
                f"at index {error_index}"
            )

        return {
            str(oid): value.prettyPrint()
            for oid, value in var_binds
        }

    async def _walk_column(self, base_oid):
        """
        Walk one SNMP table column using GETNEXT.

        PySNMP 7.1.x next_cmd is awaited once per request.
        """
        results = {}
        current_oid = base_oid

        while True:
            (
                error_indication,
                error_status,
                error_index,
                var_binds,
            ) = await next_cmd(
                self.snmp_engine,
                self._build_auth(),
                self.transport_target,
                ContextData(),
                ObjectType(ObjectIdentity(current_oid)),
                lexicographicMode=False,
                lookupMib=False,
            )

            if error_indication:
                raise ConnectionError(str(error_indication))

            if error_status:
                raise RuntimeError(
                    f"SNMP table walk error: "
                    f"{error_status.prettyPrint()} "
                    f"at index {error_index}"
                )

            if not var_binds:
                break

            stop_walk = False

            for oid, value in var_binds:
                oid_string = str(oid)
                prefix = base_oid + "."

                if not oid_string.startswith(prefix):
                    stop_walk = True
                    break

                index = oid_string[len(prefix):]
                results[index] = value.prettyPrint()
                current_oid = oid_string

            if stop_walk:
                break

        return results

    @staticmethod
    def _parse_integer(value):
        """Parse a numeric SNMP value, or return None if unavailable."""
        if value is None:
            return None

        text = str(value).strip()

        if text.lower().startswith(
            (
                "no such object",
                "no such instance",
                "end of mib",
            )
        ):
            return None

        try:
            return int(text)
        except (TypeError, ValueError):
            return None

    async def _get_system_information(self):
        return await self._get_values(list(self.OIDS.values()))

    def get_system_information(self):
        """Return raw system and temperature scalar readings."""
        self._initialize()

        try:
            result = self.loop.run_until_complete(
                self._get_system_information()
            )

            logger.debug("SNMP system poll successful: %s", self.host)
            return result

        except Exception:
            logger.warning(
                "SNMP system polling failed: %s",
                self.host,
                exc_info=True,
            )
            raise

    async def _get_cpu_metrics(self):
        """Calculate average CPU utilization across available processors."""
        cpu_table = await self._walk_column(self.CPU_LOAD_BASE)

        readings = []

        for value in cpu_table.values():
            reading = self._parse_integer(value)

            if reading is not None and 0 <= reading <= 100:
                readings.append(reading)

        if not readings:
            return None, 0

        average = sum(readings) / len(readings)
        return round(average, 2), len(readings)

    async def _get_memory_metrics(self):
        """
        Find the main memory row, then retrieve its allocation unit,
        total size and used size.
        """
        descriptions = await self._walk_column(
            self.STORAGE_DESCR_BASE
        )

        memory_index = None

        for index, description in descriptions.items():
            if description.strip().lower() == "main memory":
                memory_index = index
                break

        if memory_index is None:
            return None, None, None, None

        requested_oids = [
            f"{self.STORAGE_ALLOCATION_UNITS_BASE}.{memory_index}",
            f"{self.STORAGE_SIZE_BASE}.{memory_index}",
            f"{self.STORAGE_USED_BASE}.{memory_index}",
        ]

        values = await self._get_values(requested_oids)

        allocation_units = self._parse_integer(
            values.get(requested_oids[0])
        )
        storage_size = self._parse_integer(
            values.get(requested_oids[1])
        )
        storage_used = self._parse_integer(
            values.get(requested_oids[2])
        )

        if (
            allocation_units is None
            or storage_size is None
            or storage_used is None
            or allocation_units <= 0
            or storage_size <= 0
            or storage_used < 0
            or storage_used > storage_size
        ):
            return None, None, None, None

        total_bytes = storage_size * allocation_units
        used_bytes = storage_used * allocation_units
        free_bytes = total_bytes - used_bytes

        usage_percent = (used_bytes / total_bytes) * 100

        return (
            total_bytes,
            used_bytes,
            free_bytes,
            round(usage_percent, 2),
        )

    async def _get_metrics(self):
        """Collect and normalize system, CPU, memory and temperature data."""
        scalar_oids = list(self.OIDS.values())
        raw = await self._get_values(scalar_oids)

        identity = raw.get(self.OIDS["identity"])
        description = raw.get(self.OIDS["description"])

        uptime = self._parse_integer(
            raw.get(self.OIDS["uptime"])
        )

        cpu_percent, cpu_core_count = await self._get_cpu_metrics()

        (
            memory_total,
            memory_used,
            memory_free,
            memory_percent,
        ) = await self._get_memory_metrics()

        # Prefer board temperature when available.
        board_temperature = self._parse_integer(
            raw.get(self.OIDS["board_temperature"])
        )

        processor_temperature = self._parse_integer(
            raw.get(self.OIDS["processor_temperature"])
        )

        if board_temperature is not None:
            temperature = board_temperature / 10
            temperature_sensor = "board"
        elif processor_temperature is not None:
            temperature = processor_temperature / 10
            temperature_sensor = "processor"
        else:
            temperature = None
            temperature_sensor = None

        return {
            "identity": identity,
            "description": description,
            "board_temperature_celsius": (
                temperature if temperature_sensor == "board" else None
            ),
            "processor_temperature_celsius": (
                temperature if temperature_sensor == "processor" else None
            ),

            # SNMP TimeTicks are hundredths of a second.
            "uptime_seconds": (
                uptime / 100 if uptime is not None else None
            ),

            "cpu_usage_percent": cpu_percent,
            "cpu_core_count": cpu_core_count,

            "memory_total_bytes": memory_total,
            "memory_used_bytes": memory_used,
            "memory_free_bytes": memory_free,
            "memory_usage_percent": memory_percent,

            "temperature_celsius": temperature,
            "temperature_sensor": temperature_sensor,

            "availability": {
                "cpu": cpu_percent is not None,
                "memory": memory_percent is not None,
                "temperature": temperature is not None,
            },
        }

    def get_metrics(self):
        """Return normalized metrics from the SNMP-managed device."""
        self._initialize()

        try:
            metrics = self.loop.run_until_complete(
                self._get_metrics()
            )

            logger.debug("SNMP metrics poll successful: %s", self.host)
            return metrics

        except Exception:
            logger.warning(
                "SNMP metrics polling failed: %s",
                self.host,
                exc_info=True,
            )
            raise

    def close(self):
        if self.closed:
            return

        if (
            self.owner_thread_id is not None
            and self.owner_thread_id != threading.get_ident()
        ):
            raise RuntimeError(
                "SNMP resources must be closed by their owner thread."
            )

        try:
            if self.snmp_engine is not None:
                self.snmp_engine.close_dispatcher()

        except Exception:
            logger.warning(
                "Error closing SNMP dispatcher: %s",
                self.host,
                exc_info=True,
            )

        finally:
            if self.loop is not None and not self.loop.is_closed():
                self.loop.close()

            if self.owner_thread_id == threading.get_ident():
                asyncio.set_event_loop(None)

            self.snmp_engine = None
            self.transport_target = None
            self.loop = None
            self.closed = True

            logger.info("SNMP resources closed: %s", self.host)
