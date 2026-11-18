
import logging
import socket
import time

from librouteros import connect

logger = logging.getLogger(__name__)


class MikroTikConnection:
    """
    Persistent, single-thread-owned RouterOS API connection.

    This service only performs read operations.
    """

    def __init__(
        self,
        host,
        username,
        password,
        port=8728,
        connection_timeout=5,
        health_check_interval=30,
        retry_interval=10,
    ):
        self.host = host
        self.username = username
        self.password = password
        self.port = port

        self.connection_timeout = connection_timeout
        self.health_check_interval = health_check_interval
        self.retry_interval = retry_interval

        self.api = None
        self.connected = False
        self.last_health_check = 0

    def connect(self):
        """Establish a RouterOS API session."""

        self.disconnect()

        try:
            self.api = connect(
                host=self.host,
                username=self.username,
                password=self.password,
                port=self.port,
                timeout=self.connection_timeout,
                encoding="UTF-8",
            )

            identity = tuple(
                self.api.path("system", "identity")
            )

            if not identity:
                raise ConnectionError(
                    "Router returned no identity information."
                )

            self.connected = True
            self.last_health_check = time.monotonic()

            logger.info(
                "Connected to MikroTik %s (%s)",
                self.host,
                identity[0].get("name", "Unknown"),
            )

            return identity[0]

        except Exception:
            self.disconnect()

            # Re-raise the original exception.
            # The worker will classify and handle it.
            raise

    
    def disconnect(self):
        """Close the API socket only when one exists."""

        api = self.api
        self.api = None
        self.connected = False

        if api is not None:
            try:
                api.close()
                logger.info(
                    "Disconnected from MikroTik: %s",
                    self.host,
                )
            except Exception:
                logger.warning(
                    "Error closing MikroTik connection: %s",
                    self.host,
                    exc_info=True,
                )


    def health_check(self):
        """Perform a lightweight read-only check."""
        if not self.connected or self.api is None:
            return False

        try:
            tuple(self.api.path("system", "identity"))
            self.last_health_check = time.monotonic()
            return True

        except Exception:
            logger.warning(
                "MikroTik health check failed: %s",
                self.host,
                exc_info=True,
            )
            self.disconnect()
            return False

    def get_system_information(self):
        """Read basic system information."""
        if not self.connected or self.api is None:
            raise ConnectionError("MikroTik is not connected.")

        resource = tuple(self.api.path("system", "resource"))
        identity = tuple(self.api.path("system", "identity"))

        return {
            "identity": identity[0] if identity else {},
            "resource": resource[0] if resource else {},
        }

    def run_forever(self, stop_event):
        """
        Keep the connection alive until stop_event is set.
        Reconnect automatically after a connection failure.
        """
        logger.info("Starting persistent MikroTik connection service.")

        try:
            while not stop_event.is_set():

                if not self.connected:
                    try:
                        self.connect()
                    except Exception:
                        stop_event.wait(self.retry_interval)
                        continue

                elapsed = time.monotonic() - self.last_health_check

                if elapsed >= self.health_check_interval:
                    if not self.health_check():
                        stop_event.wait(self.retry_interval)
                        continue

                stop_event.wait(1)

        finally:
            self.disconnect()
            logger.info("MikroTik monitoring service stopped.")
