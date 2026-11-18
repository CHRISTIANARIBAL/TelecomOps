
import logging
import threading

from django.db import close_old_connections

from network_monitoring.models import MikroTikDevice
from .connection_worker import MikroTikDeviceWorker

logger = logging.getLogger(__name__)


class MikroTikConnectionManager:

    def __init__(self, discovery_interval=5):
        self.discovery_interval = discovery_interval
        self.stop_event = threading.Event()
        self.workers = {}
        self.device_configs = {}
        self.lock = threading.RLock()

    @staticmethod
    def get_device_configs():
        """
        Load enabled devices and their connection configuration.

        The encrypted password is included in the fingerprint.
        Plaintext passwords are never logged or stored here.
        """
        close_old_connections()

        try:
            devices = MikroTikDevice.objects.filter(
                is_enabled=True
            ).values(
                "id",
                "name",
                "host",
                "api_port",
                "api_username",
                "api_password_encrypted",
            )

            return {
                device["id"]: (
                    device["name"],
                    device["host"],
                    device["api_port"],
                    device["api_username"],
                    device["api_password_encrypted"],
                )
                for device in devices
            }

        finally:
            close_old_connections()

    def reconcile_devices(self):
        """
        Compare database configurations with active workers.

        Changed configurations cause only the affected worker
        to stop and restart.
        """
        database_configs = self.get_device_configs()

        with self.lock:
            # Find workers that were deleted, disabled, or changed.
            for device_id in list(self.workers):
                worker = self.workers[device_id]

                old_config = self.device_configs.get(device_id)
                new_config = database_configs.get(device_id)

                configuration_changed = (
                    new_config is not None
                    and old_config != new_config
                )

                device_removed = new_config is None

                if configuration_changed or device_removed:
                    if configuration_changed:
                        logger.info(
                            "Configuration change detected for device ID %s.",
                            device_id,
                        )
                    else:
                        logger.info(
                            "Device %s was disabled or deleted.",
                            device_id,
                        )

                    worker.stop()

                    # Never start a replacement while the old worker
                    # still owns its API connection.
                    worker.join(timeout=15)

                    if worker.is_alive():
                        logger.warning(
                            "Worker %s is still stopping. "
                            "Replacement postponed.",
                            device_id,
                        )
                        continue

                    self.workers.pop(device_id, None)
                    self.device_configs.pop(device_id, None)

                    logger.info(
                        "Old worker stopped: device ID %s",
                        device_id,
                    )

            # Start new workers or workers whose configuration changed.
            for device_id, new_config in database_configs.items():

                if self.stop_event.is_set():
                    break

                worker = self.workers.get(device_id)

                if worker is not None:
                    if worker.is_alive():
                        continue

                    logger.warning(
                        "Worker %s stopped unexpectedly. Restarting.",
                        device_id,
                    )

                    self.workers.pop(device_id, None)
                    self.device_configs.pop(device_id, None)

                # Start the worker using the latest database configuration.
                logger.info(
                    "Starting worker for %s (%s).",
                    new_config[0],
                    new_config[1],
                )

                new_worker = MikroTikDeviceWorker(device_id)

                self.workers[device_id] = new_worker
                self.device_configs[device_id] = new_config

                try:
                    new_worker.start()
                except Exception:
                    logger.exception(
                        "Unable to start worker for device ID %s",
                        device_id,
                    )
                    self.workers.pop(device_id, None)
                    self.device_configs.pop(device_id, None)

    def stop_all(self):
        logger.info("Stopping all MikroTik device workers.")

        self.stop_event.set()

        with self.lock:
            workers = list(self.workers.items())

            for device_id, worker in workers:
                logger.info(
                    "Requesting worker shutdown: %s",
                    device_id,
                )
                worker.stop()

            for device_id, worker in workers:
                worker.join(timeout=15)

                if worker.is_alive():
                    logger.error(
                        "Worker %s is still alive. "
                        "It has not been removed from the manager.",
                        device_id,
                    )
                    continue

                self.workers.pop(device_id, None)
                self.device_configs.pop(device_id, None)

        logger.info("MikroTik connection manager shutdown completed.")

    def run_forever(self):
        logger.info("MikroTik multi-device manager started.")

        try:
            while not self.stop_event.is_set():
                try:
                    self.reconcile_devices()
                except Exception:
                    logger.exception(
                        "Device reconciliation failed. "
                        "The manager will retry."
                    )

                self.stop_event.wait(self.discovery_interval)

        finally:
            self.stop_all()
