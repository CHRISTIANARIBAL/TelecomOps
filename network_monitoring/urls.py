from django.urls import path
from . import views

app_name = 'network_monitoring'

urlpatterns = [
    path('', views.dashboard, name='dashboard'),
    path("api/snmp-analytics/", views.snmp_analytics_api, name="snmp_analytics_api"),
    path("monitoring/", views.network_monitoring, name="monitoring"),
]