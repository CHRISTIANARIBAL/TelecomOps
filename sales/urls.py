from django.urls import path
from . import views

app_name = "sales"

urlpatterns = [
    path("", views.sales_list, name="sales_list"),
    path("product/<int:product_id>/sell/", views.sell_product, name="sell_product"),
    path("<int:pk>/", views.sale_detail, name="sale_detail"),
    path("<int:pk>/edit/", views.edit_sale, name="edit_sale"),
]