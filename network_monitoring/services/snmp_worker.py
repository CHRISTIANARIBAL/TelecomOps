
import logging
import socket
import threading

from decimal import Decimal, InvalidOperation
from django.db import close_old_connections
from django.utils import timezone

from network_monitoring.models import (
    MikroTikDevice,
    SNMPMetricHistory,
)
from .snmp_connection import MikroTikSNMPConnection

logger = logging.getLogger(__name__)


class MikroTikSNMPWorker:

    def __init__(
        self,
        device_id,
        poll_interval=30,
        retry_initial=10,
        retry_max=60,
    ):
        self.device_id = device_id
        self.poll_interval = poll_interval
        self.retry_initial = retry_initial
        self.retry_max = retry_max

        self.stop_event = threading.Event()

        self.thread = threading.Thread(
            target=self.run,
            name=f"snmp-{device_id}",
            daemon=False,
        )

        self.connection = None
        self.last_status = None
        self.latest_metrics = None

    def start(self):
        self.thread.start()

    def stop(self):
        self.stop_event.set()

    def join(self, timeout=None):
        self.thread.join(timeout)

    def is_alive(self):
        return self.thread.is_alive()

    def update_status(self, status, error=""):
        close_old_connections()

        try:
            MikroTikDevice.objects.filter(
                pk=self.device_id
            ).update(
                snmp_status=status,
                snmp_last_error=error[:2000],
            )
        finally:
            close_old_connections()

    def update_success(self):
        close_old_connections()

        try:
            MikroTikDevice.objects.filter(
                pk=self.device_id
            ).update(
                snmp_status=MikroTikDevice.SNMPStatus.CONNECTED,
                snmp_last_poll=timezone.now(),
                snmp_last_error="",
            )
        finally:
            close_old_connections()

    
    @staticmethod
    def to_decimal(value):
        if value is None:
            return None

        try:
            return Decimal(str(value))
        except (InvalidOperation, TypeError, ValueError):
            return None

    def save_metrics(self, metrics):
        """
        Save one historical record for each successful SNMP collection.

        Database failures are logged separately and do not change
        the SNMP connection status.
        """
        close_old_connections()

        try:
            uptime = metrics.get("uptime_seconds")

            SNMPMetricHistory.objects.create(
                device_id=self.device_id,

                cpu_usage_percent=self.to_decimal(
                    metrics.get("cpu_usage_percent")
                ),
                cpu_core_count=metrics.get("cpu_core_count"),

                memory_total_bytes=metrics.get("memory_total_bytes"),
                memory_used_bytes=metrics.get("memory_used_bytes"),
                memory_free_bytes=metrics.get("memory_free_bytes"),
                memory_usage_percent=self.to_decimal(
                    metrics.get("memory_usage_percent")
                ),

                temperature_celsius=self.to_decimal(
                    metrics.get("temperature_celsius")
                ),
                temperature_sensor=(
                    metrics.get("temperature_sensor") or ""
                ),

                uptime_seconds=(
                    int(uptime) if uptime is not None else None
                ),
            )

            logger.debug(
                "SNMP metrics saved for device ID %s.",
                self.device_id,
            )

            return True

        except Exception:
            logger.exception(
                "Failed to save SNMP metrics for device ID %s.",
                self.device_id,
            )
            return False

        finally:
            close_old_connections()

    

    def classify_error(self, exc):
        if isinstance(exc, (TimeoutError, socket.timeout)):
            return (
                MikroTikDevice.SNMPStatus.TIMEOUT,
                "SNMP request timed out",
            )

        message = str(exc).lower()

        if "timeout" in message or "no snmp response" in message:
            return (
                MikroTikDevice.SNMPStatus.TIMEOUT,
                "SNMP request timed out",
            )

        if isinstance(exc, OSError):
            return (
                MikroTikDevice.SNMPStatus.ERROR,
                "SNMP network error",
            )

        return (
            MikroTikDevice.SNMPStatus.ERROR,
            "SNMP connection error",
        )

    def load_device(self):
        close_old_connections()

        try:
            return MikroTikDevice.objects.filter(
                pk=self.device_id,
                is_enabled=True,
                snmp_enabled=True,
            ).first()
        finally:
            close_old_connections()

    def create_connection(self, device):
        auth_password = device.get_snmp_auth_password()
        privacy_password = device.get_snmp_priv_password()

        if not device.snmp_username:
            raise ValueError("SNMPv3 username is not configured.")

        if not auth_password or not privacy_password:
            raise ValueError("SNMPv3 credentials are incomplete.")

        return MikroTikSNMPConnection(
            host=device.host,
            username=device.snmp_username,
            auth_password=auth_password,
            privacy_password=privacy_password,
            port=device.snmp_port,
        )

    def run(self):
        retry_delay = self.retry_initial
        first_attempt = True

        try:
            while not self.stop_event.is_set():

                try:
                    device = self.load_device()

                    if device is None:
                        logger.info(
                            "SNMP device %s is disabled or deleted.",
                            self.device_id,
                        )
                        break

                    # Create the connection only once.
                    # Reuse its engine, event loop and transport
                    # for all subsequent polling cycles.
                    if self.connection is None:
                        self.connection = self.create_connection(device)

                    if first_attempt:
                        logger.info(
                            "Starting SNMP monitoring: %s (%s)",
                            device.name,
                            device.host,
                        )

                    self.update_status(
                        MikroTikDevice.SNMPStatus.CONNECTING
                    )
                    metrics = self.connection.get_metrics()
                    self.latest_metrics = metrics
                    self.save_metrics(metrics)
                    previous_status = self.last_status
                    self.update_success()

                    if previous_status != MikroTikDevice.SNMPStatus.CONNECTED:
                        if previous_status is not None:
                            logger.info(
                                "SNMP connection recovered: %s (%s)",
                                device.name,
                                device.host,
                            )
                        else:
                            logger.info(
                                "SNMP monitoring active: %s (%s). Identity: %s",
                                device.name,
                                device.host,
                                metrics.get("identity") or "Unknown",
                            )

                        logger.info(
                            "Initial SNMP metrics for %s: CPU=%s%%, RAM=%s%%, "
                            "Temperature=%s°C (%s)",
                            device.name,
                            metrics.get("cpu_usage_percent"),
                            metrics.get("memory_usage_percent"),
                            metrics.get("temperature_celsius"),
                            metrics.get("temperature_sensor") or "unsupported",
                        )

                    self.last_status = MikroTikDevice.SNMPStatus.CONNECTED

                    retry_delay = self.retry_initial
                    first_attempt = False

                    # Wait for the next polling cycle.
                    self.stop_event.wait(self.poll_interval)

                except Exception as exc:
                    if self.stop_event.is_set():
                        break

                    status, description = self.classify_error(exc)

                    if self.last_status != status:
                        logger.warning(
                            "%s for SNMP device ID %s: %s",
                            description,
                            self.device_id,
                            exc,
                        )

                    self.update_status(status, str(exc))
                    self.last_status = status

                    logger.warning(
                        "Retrying SNMP device %s in %s seconds.",
                        self.device_id,
                        retry_delay,
                    )

                    self.stop_event.wait(retry_delay)

                    retry_delay = min(
                        retry_delay * 2,
                        self.retry_max,
                    )

        finally:
            # Close SNMP resources only when the worker stops.
            if self.connection is not None:
                try:
                    self.connection.close()
                except Exception:
                    logger.exception(
                        "Error closing SNMP resources for device %s.",
                        self.device_id,
                    )
                finally:
                    self.connection = None

            self.update_status(
                MikroTikDevice.SNMPStatus.DISCONNECTED
            )

            close_old_connections()

            logger.info(
                "SNMP worker stopped: device ID %s",
                self.device_id,
            )
