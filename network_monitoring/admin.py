
from django import forms
from django.contrib import admin

from .models import MikroTikDevice, SNMPMetricHistory


class MikroTikDeviceAdminForm(forms.ModelForm):

    api_password = forms.CharField(
        label="API Password",
        widget=forms.PasswordInput(render_value=False),
        required=False,
        help_text="Required for new devices. Leave blank when editing to keep the existing password.",
    )

    snmp_auth_password = forms.CharField(
        label="SNMP Authentication Password",
        widget=forms.PasswordInput(render_value=False),
        required=False,
        help_text="Required when enabling SNMP for the first time. Leave blank to keep the existing password.",
    )

    snmp_priv_password = forms.CharField(
        label="SNMP Privacy Password",
        widget=forms.PasswordInput(render_value=False),
        required=False,
        help_text="Required when enabling SNMP for the first time. Leave blank to keep the existing password.",
    )

    class Meta:
        model = MikroTikDevice
        fields = (
            "name",
            "host",
            "api_port",
            "api_username",
            "is_enabled",
            "snmp_enabled",
            "snmp_port",
            "snmp_username",
        )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        if not self.instance.pk:
            self.fields["api_password"].required = True

        if self.instance.pk and self.instance.snmp_auth_password_encrypted:
            self.fields["snmp_auth_password"].help_text = (
                "Password is already configured. Leave blank to keep it."
            )

        if self.instance.pk and self.instance.snmp_priv_password_encrypted:
            self.fields["snmp_priv_password"].help_text = (
                "Password is already configured. Leave blank to keep it."
            )

    def clean(self):
        cleaned_data = super().clean()

        snmp_enabled = cleaned_data.get("snmp_enabled")
        username = cleaned_data.get("snmp_username")
        auth_password = cleaned_data.get("snmp_auth_password")
        priv_password = cleaned_data.get("snmp_priv_password")

        existing_auth = bool(
            self.instance.pk
            and self.instance.snmp_auth_password_encrypted
        )
        existing_priv = bool(
            self.instance.pk
            and self.instance.snmp_priv_password_encrypted
        )

        if snmp_enabled:
            if not username:
                self.add_error(
                    "snmp_username",
                    "SNMPv3 username is required.",
                )

            if not auth_password and not existing_auth:
                self.add_error(
                    "snmp_auth_password",
                    "SNMP authentication password is required.",
                )

            if not priv_password and not existing_priv:
                self.add_error(
                    "snmp_priv_password",
                    "SNMP privacy password is required.",
                )

            for field_name, password in (
                ("snmp_auth_password", auth_password),
                ("snmp_priv_password", priv_password),
            ):
                if password and len(password) < 8:
                    self.add_error(
                        field_name,
                        "SNMPv3 passwords must contain at least 8 characters.",
                    )

        return cleaned_data


@admin.register(MikroTikDevice)
class MikroTikDeviceAdmin(admin.ModelAdmin):

    form = MikroTikDeviceAdminForm

    list_display = (
        "name",
        "host",
        "api_port",
        "is_enabled",
        "connection_status",
        "snmp_enabled",
        "snmp_status",
        "last_connected",
        "snmp_last_poll",
    )

    list_filter = (
        "is_enabled",
        "connection_status",
        "snmp_enabled",
        "snmp_status",
    )

    search_fields = (
        "name",
        "host",
        "api_username",
        "snmp_username",
    )

    readonly_fields = (
        "connection_status",
        "last_connected",
        "last_error",
        "snmp_status",
        "snmp_last_poll",
        "snmp_last_error",
        "created_at",
        "updated_at",
    )

    fieldsets = (
        (
            "Device Information",
            {
                "fields": (
                    "name",
                    "host",
                    "is_enabled",
                )
            },
        ),
        (
            "MikroTik API Configuration",
            {
                "fields": (
                    "api_port",
                    "api_username",
                    "api_password",
                )
            },
        ),
        (
            "API Connection Information",
            {
                "fields": (
                    "connection_status",
                    "last_connected",
                    "last_error",
                )
            },
        ),
        (
            "SNMP Configuration",
            {
                "fields": (
                    "snmp_enabled",
                    "snmp_port",
                    "snmp_username",
                    "snmp_auth_password",
                    "snmp_priv_password",
                )
            },
        ),
        (
            "SNMP Connection Information",
            {
                "fields": (
                    "snmp_status",
                    "snmp_last_poll",
                    "snmp_last_error",
                )
            },
        ),
        (
            "Timestamps",
            {
                "fields": (
                    "created_at",
                    "updated_at",
                )
            },
        ),
    )

    def save_model(self, request, obj, form, change):
        api_password = form.cleaned_data.get("api_password")
        auth_password = form.cleaned_data.get("snmp_auth_password")
        priv_password = form.cleaned_data.get("snmp_priv_password")

        if api_password:
            obj.set_api_password(api_password)

        if auth_password and priv_password:
            obj.set_snmp_credentials(
                username=obj.snmp_username,
                auth_password=auth_password,
                privacy_password=priv_password,
            )

        super().save_model(request, obj, form, change)

@admin.register(SNMPMetricHistory)
class SNMPMetricHistoryAdmin(admin.ModelAdmin):

    list_display = (
        "device",
        "cpu_usage_percent",
        "cpu_core_count",
        "memory_usage_percent",
        "temperature_celsius",
        "temperature_sensor",
        "collected_at",
    )

    list_filter = (
        "device",
        "temperature_sensor",
        "collected_at",
    )

    search_fields = (
        "device__name",
        "device__host",
    )

    date_hierarchy = "collected_at"

    ordering = ("-collected_at",)

    list_per_page = 50

    list_display_links = None

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
