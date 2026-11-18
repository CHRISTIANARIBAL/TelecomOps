
from datetime import timedelta

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import render, redirect
from django.utils import timezone

from .models import MikroTikDevice, SNMPMetricHistory


@login_required
def dashboard(request):
    if request.session.get("password_recovery_pending"):
        return redirect("password_recovery_choice")

    return render(
        request,
        "network_monitoring/dashboard.html",
        {
            "active_page": "dashboard",
        },
    )


@login_required
def snmp_analytics_api(request):
    """
    Return current SNMP readings and historical metrics
    for the analytics dashboard.
    """

    # Supported time ranges
    time_ranges = {
        "30m": timedelta(minutes=30),
        "1h": timedelta(hours=1),
        "6h": timedelta(hours=6),
        "24h": timedelta(hours=24),
        "7d": timedelta(days=7),
    }

    selected_range = request.GET.get("range", "1h")

    if selected_range not in time_ranges:
        selected_range = "1h"

    selected_device = request.GET.get("device", "all")

    start_time = timezone.now() - time_ranges[selected_range]

    # Only include devices configured for SNMP.
    devices = MikroTikDevice.objects.filter(
        snmp_enabled=True
    ).order_by("name")

    if selected_device != "all":
        try:
            selected_device_id = int(selected_device)
        except (TypeError, ValueError):
            return JsonResponse(
                {"error": "Invalid device selection."},
                status=400,
            )

        devices = devices.filter(pk=selected_device_id)

        if not devices.exists():
            return JsonResponse(
                {"error": "Device not found or SNMP is disabled."},
                status=404,
            )

    # Latest successful metric record for each device.
    latest_metrics = []

    for device in devices:
        latest = (
            SNMPMetricHistory.objects
            .filter(device=device)
            .order_by("-collected_at")
            .first()
        )

        latest_metrics.append({
            "device_id": device.pk,
            "device_name": device.name,
            "host": device.host,
            "snmp_status": device.get_snmp_status_display(),
            "snmp_last_poll": (
                timezone.localtime(device.snmp_last_poll).isoformat()
                if device.snmp_last_poll else None
            ),
            "metrics": {
                "cpu_usage_percent": (
                    float(latest.cpu_usage_percent)
                    if latest and latest.cpu_usage_percent is not None
                    else None
                ),
                "cpu_core_count": (
                    latest.cpu_core_count if latest else None
                ),
                "memory_usage_percent": (
                    float(latest.memory_usage_percent)
                    if latest and latest.memory_usage_percent is not None
                    else None
                ),
                "memory_total_bytes": (
                    latest.memory_total_bytes if latest else None
                ),
                "memory_used_bytes": (
                    latest.memory_used_bytes if latest else None
                ),
                "memory_free_bytes": (
                    latest.memory_free_bytes if latest else None
                ),
                "temperature_celsius": (
                    float(latest.temperature_celsius)
                    if latest and latest.temperature_celsius is not None
                    else None
                ),
                "temperature_sensor": (
                    latest.temperature_sensor if latest else None
                ),
                "uptime_seconds": (
                    latest.uptime_seconds if latest else None
                ),
                "collected_at": (
                    timezone.localtime(latest.collected_at).isoformat()
                    if latest else None
                ),
            },
        })

    # Historical metric records within the selected time range.
    history_query = SNMPMetricHistory.objects.filter(
        device__snmp_enabled=True,
        collected_at__gte=start_time,
    )

    if selected_device != "all":
        history_query = history_query.filter(
            device_id=selected_device_id
        )

    history = (
        history_query
        .select_related("device")
        .order_by("collected_at")[:2000]
    )

    history_data = []

    for record in history:
        history_data.append({
            "device_id": record.device_id,
            "device_name": record.device.name,
            "host": record.device.host,
            "collected_at": timezone.localtime(
                record.collected_at
            ).isoformat(),
            "cpu_usage_percent": (
                float(record.cpu_usage_percent)
                if record.cpu_usage_percent is not None
                else None
            ),
            "memory_usage_percent": (
                float(record.memory_usage_percent)
                if record.memory_usage_percent is not None
                else None
            ),
            "temperature_celsius": (
                float(record.temperature_celsius)
                if record.temperature_celsius is not None
                else None
            ),
            "temperature_sensor": record.temperature_sensor,
        })

    return JsonResponse({
        "devices": [
            {
                "id": device.pk,
                "name": device.name,
                "host": device.host,
                "snmp_status": device.get_snmp_status_display(),
            }
            for device in devices
        ],
        "latest_metrics": latest_metrics,
        "history": history_data,
        "filters": {
            "range": selected_range,
            "device": selected_device,
        },
        "generated_at": timezone.localtime(
            timezone.now()
        ).isoformat(),
    })


@login_required
def network_monitoring(request):
    if request.session.get("password_recovery_pending"):
        return redirect("password_recovery_choice")

    devices = MikroTikDevice.objects.filter(
        snmp_enabled=True
    ).order_by("name")

    return render(
        request,
        "network_monitoring/monitoring.html",
        {
            "active_page": "network_monitoring",
            "devices": devices,
        },
    )
