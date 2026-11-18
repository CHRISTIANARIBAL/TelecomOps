
from django.db import models
from django.utils import timezone

class MikroTikDevice(models.Model):

    class ConnectionStatus(models.TextChoices):
        UNKNOWN = "unknown", "Unknown"
        CONNECTING = "connecting", "Connecting"
        CONNECTED = "connected", "Connected"
        DISCONNECTED = "disconnected", "Disconnected"
        RECONNECTING = "reconnecting", "Reconnecting"
        TIMEOUT = "timeout", "Connection Timeout"
        ERROR = "error", "Connection Error"

    class SNMPStatus(models.TextChoices):
        UNKNOWN = "unknown", "Unknown"
        CONNECTING = "connecting", "Connecting"
        CONNECTED = "connected", "Connected"
        DISCONNECTED = "disconnected", "Disconnected"
        TIMEOUT = "timeout", "Connection Timeout"
        ERROR = "error", "Connection Error"

    # ==========================================
    # GENERAL DEVICE INFORMATION
    # ==========================================

    name = models.CharField(max_length=100)

    host = models.GenericIPAddressField(
        help_text="Router IP address reachable through your network."
    )

    is_enabled = models.BooleanField(default=True)

    # ==========================================
    # MIKROTIK API CONFIGURATION
    # ==========================================

    api_port = models.PositiveIntegerField(default=8728)

    api_username = models.CharField(max_length=100)

    api_password_encrypted = models.TextField(
        editable=False,
    )

    connection_status = models.CharField(
        max_length=20,
        choices=ConnectionStatus.choices,
        default=ConnectionStatus.UNKNOWN,
    )

    last_connected = models.DateTimeField(
        null=True,
        blank=True,
    )

    last_error = models.TextField(
        blank=True,
    )

    # ==========================================
    # SNMP CONFIGURATION
    # ==========================================

    snmp_enabled = models.BooleanField(
        default=False,
        help_text="Enable independent SNMP monitoring for this device.",
    )

    snmp_port = models.PositiveIntegerField(
        default=161,
    )

    snmp_username = models.CharField(
        max_length=100,
        blank=True,
    )

    snmp_auth_password_encrypted = models.TextField(
        blank=True,
        editable=False,
    )

    snmp_priv_password_encrypted = models.TextField(
        blank=True,
        editable=False,
    )

    snmp_status = models.CharField(
        max_length=20,
        choices=SNMPStatus.choices,
        default=SNMPStatus.UNKNOWN,
    )

    snmp_last_poll = models.DateTimeField(
        null=True,
        blank=True,
    )

    snmp_last_error = models.TextField(
        blank=True,
    )

    # ==========================================
    # TIMESTAMPS
    # ==========================================

    created_at = models.DateTimeField(auto_now_add=True)

    updated_at = models.DateTimeField(auto_now=True)

    # ==========================================
    # MODEL SETTINGS
    # ==========================================

    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(
                fields=["host", "api_port"],
                name="unique_mikrotik_host_api_port",
            )
        ]

    def __str__(self):
        return f"{self.name} ({self.host})"

    # ==========================================
    # API CREDENTIAL ENCRYPTION
    # ==========================================

    def set_api_password(self, password):
        from .services.credential_encryption import encrypt_password

        self.api_password_encrypted = encrypt_password(password)

    def get_api_password(self):
        from .services.credential_encryption import decrypt_password

        return decrypt_password(self.api_password_encrypted)

    # ==========================================
    # SNMP CREDENTIAL ENCRYPTION
    # ==========================================

    def set_snmp_credentials(
        self,
        username,
        auth_password,
        privacy_password,
    ):
        from .services.credential_encryption import encrypt_password

        self.snmp_username = username
        self.snmp_auth_password_encrypted = encrypt_password(auth_password)
        self.snmp_priv_password_encrypted = encrypt_password(privacy_password)

    def get_snmp_auth_password(self):
        from .services.credential_encryption import decrypt_password

        if not self.snmp_auth_password_encrypted:
            return ""

        return decrypt_password(self.snmp_auth_password_encrypted)

    def get_snmp_priv_password(self):
        from .services.credential_encryption import decrypt_password

        if not self.snmp_priv_password_encrypted:
            return ""

        return decrypt_password(self.snmp_priv_password_encrypted)


class SNMPMetricHistory(models.Model):
    """
    Historical SNMP metrics collected from MikroTik devices.
    Each record represents one successful polling cycle.
    """

    device = models.ForeignKey(
        MikroTikDevice,
        on_delete=models.CASCADE,
        related_name="snmp_metric_history",
    )

    # CPU metrics
    cpu_usage_percent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
    )

    cpu_core_count = models.PositiveIntegerField(
        null=True,
        blank=True,
    )

    # Memory metrics (bytes)
    memory_total_bytes = models.PositiveBigIntegerField(
        null=True,
        blank=True,
    )

    memory_used_bytes = models.PositiveBigIntegerField(
        null=True,
        blank=True,
    )

    memory_free_bytes = models.PositiveBigIntegerField(
        null=True,
        blank=True,
    )

    memory_usage_percent = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
    )

    # Temperature metrics
    temperature_celsius = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        null=True,
        blank=True,
    )

    temperature_sensor = models.CharField(
        max_length=30,
        blank=True,
    )

    # Device uptime
    uptime_seconds = models.PositiveBigIntegerField(
        null=True,
        blank=True,
    )

    # Collection timestamp
    collected_at = models.DateTimeField(
        default=timezone.now,
        db_index=True,
    )

    class Meta:
        ordering = ["-collected_at"]
        indexes = [
            models.Index(
                fields=["device", "-collected_at"],
                name="snmp_device_time_idx",
            ),
        ]

    def __str__(self):
        return (
            f"{self.device.name} - "
            f"{self.collected_at:%Y-%m-%d %H:%M:%S}"
        )
