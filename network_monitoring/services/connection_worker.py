
import logging
import socket
import threading
import time

from django.db import close_old_connections
from django.utils import timezone

from network_monitoring.models import MikroTikDevice
from .mikrotik_connection import MikroTikConnection

logger = logging.getLogger(__name__)


class MikroTikDeviceWorker:

    def __init__(
        self,
        device_id,
        retry_initial=10,
        retry_max=60,
    ):
        self.device_id = device_id
        self.retry_initial = retry_initial
        self.retry_max = retry_max

        self.stop_event = threading.Event()

        self.thread = threading.Thread(
            target=self.run,
            name=f"mikrotik-{device_id}",
            daemon=False,
        )

        self.connection = None

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
                connection_status=status,
                last_error=error[:2000],
                updated_at=timezone.now(),
            )
        finally:
            close_old_connections()

    def classify_error(self, exc):
        if isinstance(exc, (TimeoutError, socket.timeout)):
            return (
                MikroTikDevice.ConnectionStatus.TIMEOUT,
                "Connection timeout",
            )

        if isinstance(exc, ConnectionRefusedError):
            return (
                MikroTikDevice.ConnectionStatus.ERROR,
                "Connection refused",
            )

        if isinstance(exc, OSError):
            return (
                MikroTikDevice.ConnectionStatus.ERROR,
                "Network connection error",
            )

        return (
            MikroTikDevice.ConnectionStatus.ERROR,
            "Unexpected connection error",
        )

    def log_connection_error(self, exc):
        status, description = self.classify_error(exc)

        logger.warning(
            "%s for device ID %s: %s",
            description,
            self.device_id,
            exc,
        )

        return status

    def run(self):
        retry_delay = self.retry_initial
        first_attempt = True

        try:
            while not self.stop_event.is_set():

                close_old_connections()

                try:
                    device = MikroTikDevice.objects.filter(
                        pk=self.device_id,
                        is_enabled=True,
                    ).first()

                    if device is None:
                        logger.info(
                            "Device %s is no longer enabled.",
                            self.device_id,
                        )
                        break

                    password = device.get_api_password()

                    self.update_status(
                        MikroTikDevice.ConnectionStatus.CONNECTING
                        if first_attempt
                        else MikroTikDevice.ConnectionStatus.RECONNECTING
                    )

                    self.connection = MikroTikConnection(
                        host=device.host,
                        username=device.api_username,
                        password=password,
                        port=device.api_port,
                    )

                    logger.info(
                        "Connecting to %s (%s)",
                        device.name,
                        device.host,
                    )

                    self.connection.connect()

                    self.update_status(
                        MikroTikDevice.ConnectionStatus.CONNECTED
                    )

                    MikroTikDevice.objects.filter(
                        pk=self.device_id
                    ).update(
                        last_connected=timezone.now(),
                        last_error="",
                    )

                    logger.info(
                        "Device connected: %s (%s)",
                        device.name,
                        device.host,
                    )

                    # Reset backoff after a successful connection.
                    retry_delay = self.retry_initial
                    first_attempt = False

                    while not self.stop_event.wait(1):

                        elapsed = (
                            time.monotonic()
                            - self.connection.last_health_check
                        )

                        if elapsed >= self.connection.health_check_interval:

                            if not self.connection.health_check():
                                raise ConnectionError(
                                    "MikroTik API health check failed."
                                )

                    if self.stop_event.is_set():
                        break

                except Exception as exc:

                    if self.stop_event.is_set():
                        break

                    status = self.log_connection_error(exc)

                    self.update_status(
                        status,
                        str(exc),
                    )

                    logger.warning(
                        "Retrying device %s in %s seconds.",
                        self.device_id,
                        retry_delay,
                    )

                    self.stop_event.wait(retry_delay)

                    # Exponential backoff with a maximum delay.
                    retry_delay = min(
                        retry_delay * 2,
                        self.retry_max,
                    )

                finally:
                    if self.connection:
                        self.connection.disconnect()
                        self.connection = None

                close_old_connections()

        finally:
            if self.connection:
                self.connection.disconnect()
                self.connection = None

            self.update_status(
                MikroTikDevice.ConnectionStatus.DISCONNECTED
            )

            close_old_connections()

            logger.info(
                "Device worker stopped: ID %s",
                self.device_id,
            )
