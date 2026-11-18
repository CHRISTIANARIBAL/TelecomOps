from django.urls import path
from . import views

app_name = "billing"

urlpatterns = [
    path("", views.dashboard, name="dashboard"),

    path("clients/", views.clients, name="clients"),
    path("clients/add/", views.add_client, name="add_client"),
    path("clients/<int:pk>/edit/", views.edit_client, name="edit_client"),
    path("clients/<int:pk>/toggle-status/", views.toggle_client_status, name="toggle_client_status"),

    path("plans/", views.plans, name="plans"),
    path("plans/add/", views.add_plan, name="add_plan"),
    path("plans/<int:pk>/edit/", views.edit_plan, name="edit_plan"),
    path("plans/<int:pk>/delete/", views.delete_plan, name="delete_plan"),
    path("plans/delete-all/", views.delete_all_plans, name="delete_all_plans"),
]