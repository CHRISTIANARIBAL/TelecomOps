
import logging
import threading

from django.db import close_old_connections

from network_monitoring.models import MikroTikDevice
from .snmp_worker import MikroTikSNMPWorker

logger = logging.getLogger(__name__)


class MikroTikSNMPManager:

    def __init__(self, discovery_interval=5):
        self.discovery_interval = discovery_interval
        self.stop_event = threading.Event()

        self.workers = {}
        self.device_configs = {}

        self.lock = threading.RLock()

    @staticmethod
    def get_device_configs():
        """
        Load enabled devices with SNMP enabled.

        Encrypted credentials are included in the configuration
        fingerprint. Plaintext passwords are never stored here.
        """
        close_old_connections()

        try:
            devices = MikroTikDevice.objects.filter(
                is_enabled=True,
                snmp_enabled=True,
            ).values(
                "id",
                "name",
                "host",
                "snmp_port",
                "snmp_username",
                "snmp_auth_password_encrypted",
                "snmp_priv_password_encrypted",
            )

            return {
                device["id"]: (
                    device["name"],
                    device["host"],
                    device["snmp_port"],
                    device["snmp_username"],
                    device["snmp_auth_password_encrypted"],
                    device["snmp_priv_password_encrypted"],
                )
                for device in devices
            }

        finally:
            close_old_connections()

    def reconcile_devices(self):
        """
        Detect new, disabled, deleted, or modified SNMP devices.
        """

        database_configs = self.get_device_configs()

        with self.lock:

            # Stop workers whose configuration changed
            # or whose devices were disabled/deleted.
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
                            "SNMP configuration change detected "
                            "for device ID %s.",
                            device_id,
                        )
                    else:
                        logger.info(
                            "SNMP device %s was disabled or deleted.",
                            device_id,
                        )

                    worker.stop()
                    worker.join(timeout=15)

                    if worker.is_alive():
                        logger.warning(
                            "SNMP worker %s is still stopping. "
                            "Replacement postponed.",
                            device_id,
                        )
                        continue

                    self.workers.pop(device_id, None)
                    self.device_configs.pop(device_id, None)

                    logger.info(
                        "Old SNMP worker stopped: device ID %s",
                        device_id,
                    )

            # Start new workers.
            for device_id, new_config in database_configs.items():

                if self.stop_event.is_set():
                    break

                worker = self.workers.get(device_id)

                if worker is not None:

                    if worker.is_alive():
                        continue

                    logger.warning(
                        "SNMP worker %s stopped unexpectedly. Restarting.",
                        device_id,
                    )

                    self.workers.pop(device_id, None)
                    self.device_configs.pop(device_id, None)

                logger.info(
                    "Starting SNMP worker for %s (%s).",
                    new_config[0],
                    new_config[1],
                )

                new_worker = MikroTikSNMPWorker(device_id)

                self.workers[device_id] = new_worker
                self.device_configs[device_id] = new_config

                try:
                    new_worker.start()

                except Exception:
                    logger.exception(
                        "Unable to start SNMP worker for device ID %s.",
                        device_id,
                    )

                    self.workers.pop(device_id, None)
                    self.device_configs.pop(device_id, None)

    def stop_all(self):
        logger.info("Stopping all SNMP device workers.")

        self.stop_event.set()

        with self.lock:

            workers = list(self.workers.items())

            for device_id, worker in workers:
                logger.info(
                    "Requesting SNMP worker shutdown: %s",
                    device_id,
                )
                worker.stop()

            for device_id, worker in workers:

                worker.join(timeout=15)

                if worker.is_alive():
                    logger.error(
                        "SNMP worker %s is still alive. "
                        "It has not been removed from the manager.",
                        device_id,
                    )
                    continue

                self.workers.pop(device_id, None)
                self.device_configs.pop(device_id, None)

        logger.info("SNMP manager shutdown completed.")

    def run_forever(self):
        logger.info("MikroTik SNMP monitoring manager started.")

        try:
            while not self.stop_event.is_set():

                try:
                    self.reconcile_devices()

                except Exception:
                    logger.exception(
                        "SNMP device reconciliation failed. "
                        "The manager will retry."
                    )

                self.stop_event.wait(self.discovery_interval)

        finally:
            self.stop_all()
