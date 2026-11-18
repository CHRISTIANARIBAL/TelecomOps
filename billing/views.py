
from django.core.exceptions import PermissionDenied
from django.contrib.auth.decorators import login_required
from django.db.models import Sum, Q, Count, Prefetch
from django.db import transaction
from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone
from django.core.paginator import Paginator
from django.contrib import messages
from .forms import CustomerRegistrationForm, InternetPlanForm, ClientSubscriptionForm
from django.db.models.deletion import ProtectedError
from decimal import Decimal

from .models import (
    Customer,
    InternetPlan,
    Subscription,
    Invoice,
    Payment,
    BillingActivity,
)

@login_required
def dashboard(request):
    if request.session.get("password_recovery_pending"):
        return redirect("password_recovery_choice")

    today = timezone.localdate()

    # Customer statistics
    total_customers = Customer.objects.count()
    active_customers = Customer.objects.filter(
        is_active=True
    ).count()

    # Internet plan statistics
    total_plans = InternetPlan.objects.count()
    active_plans = InternetPlan.objects.filter(
        is_active=True
    ).count()

    # Subscription statistics
    total_subscriptions = Subscription.objects.count()
    active_subscriptions = Subscription.objects.filter(
        status=Subscription.Status.ACTIVE
    ).count()

    suspended_subscriptions = Subscription.objects.filter(
        status=Subscription.Status.SUSPENDED
    ).count()

    pending_subscriptions = Subscription.objects.filter(
        status=Subscription.Status.PENDING
    ).count()

    # Invoice statistics
    invoices = Invoice.objects.exclude(
        status__in=[
            Invoice.Status.DRAFT,
            Invoice.Status.VOID,
        ]
    )

    outstanding_invoices = invoices.filter(
        status__in=[
            Invoice.Status.UNPAID,
            Invoice.Status.PARTIALLY_PAID,
            Invoice.Status.OVERDUE,
        ]
    )

    outstanding_balance = sum(
        (invoice.balance for invoice in outstanding_invoices),
        Decimal("0.00"),
    )

    overdue_invoices = invoices.filter(
        status=Invoice.Status.OVERDUE
    ).count()

    unpaid_invoices = invoices.filter(
        status=Invoice.Status.UNPAID
    ).count()

    # Current month collections
    monthly_collections = (
        Payment.objects.filter(
            status=Payment.Status.COMPLETED,
            payment_date__year=today.year,
            payment_date__month=today.month,
        ).aggregate(total=Sum("amount"))["total"]
        or Decimal("0.00")
    )

    # Recent transactions
    recent_payments = (
        Payment.objects
        .select_related("customer")
        .order_by("-payment_date", "-created_at")[:5]
    )

    recent_invoices = (
        Invoice.objects
        .select_related("customer", "subscription")
        .order_by("-created_at")[:5]
    )

    recent_activities = (
        BillingActivity.objects
        .select_related("user", "customer")
        .order_by("-created_at")[:8]
    )

    context = {
        "active_page": "billing",
        "total_customers": total_customers,
        "active_customers": active_customers,
        "total_plans": total_plans,
        "active_plans": active_plans,
        "total_subscriptions": total_subscriptions,
        "active_subscriptions": active_subscriptions,
        "suspended_subscriptions": suspended_subscriptions,
        "pending_subscriptions": pending_subscriptions,
        "outstanding_balance": outstanding_balance,
        "overdue_invoices": overdue_invoices,
        "unpaid_invoices": unpaid_invoices,
        "monthly_collections": monthly_collections,
        "recent_payments": recent_payments,
        "recent_invoices": recent_invoices,
        "recent_activities": recent_activities,
    }

    return render(
        request,
        "billing/dashboard.html",
        context,
    )

@login_required
def clients(request):
    if request.session.get("password_recovery_pending"):
        return redirect("password_recovery_choice")

    current_subscriptions = (
        Subscription.objects
        .filter(
            status__in=[
                Subscription.Status.PENDING,
                Subscription.Status.ACTIVE,
                Subscription.Status.SUSPENDED,
            ]
        )
        .select_related("internet_plan")
        .order_by("-created_at")
    )

    customers = Customer.objects.prefetch_related(
        Prefetch(
            "subscriptions",
            queryset=current_subscriptions,
            to_attr="current_subscriptions",
        )
)

    # Search
    search_query = request.GET.get("q", "").strip()

    if search_query:
        customers = customers.filter(
            Q(customer_id__icontains=search_query)
            | Q(first_name__icontains=search_query)
            | Q(last_name__icontains=search_query)
            | Q(company_name__icontains=search_query)
            | Q(contact_person__icontains=search_query)
            | Q(email__icontains=search_query)
            | Q(contact_number__icontains=search_query)
        )

    # Customer type filter
    customer_type = request.GET.get("type", "").strip()

    valid_types = [
        choice[0] for choice in Customer.CustomerType.choices
    ]

    if customer_type in valid_types:
        customers = customers.filter(customer_type=customer_type)

    # Account status filter
    status = request.GET.get("status", "").strip()

    if status == "active":
        customers = customers.filter(is_active=True)
    elif status == "inactive":
        customers = customers.filter(is_active=False)

    # Pagination
    paginator = Paginator(customers, 10)
    page_obj = paginator.get_page(request.GET.get("page"))

    context = {
        "active_page": "billing_clients",
        "page_obj": page_obj,
        "customers": page_obj.object_list,
        "search_query": search_query,
        "selected_type": customer_type,
        "selected_status": status,
        "customer_types": Customer.CustomerType.choices,
        "total_customers": Customer.objects.count(),
        "active_customers": Customer.objects.filter(
            is_active=True
        ).count(),
        "inactive_customers": Customer.objects.filter(
            is_active=False
        ).count(),
    }

    return render(request, "billing/clients.html", context)


@login_required
def add_client(request):
    if request.session.get("password_recovery_pending"):
        return redirect("password_recovery_choice")

    if request.method == "POST":
        form = CustomerRegistrationForm(request.POST)
        subscription_form = ClientSubscriptionForm(request.POST)

        if form.is_valid() and subscription_form.is_valid():
            with transaction.atomic():
                customer = form.save()

                subscription = subscription_form.save(commit=False)
                subscription.customer = customer
                subscription.save()

            messages.success(
                request,
                f"Client {customer.customer_id} and subscription "
                f"{subscription.subscription_number} were registered successfully."
            )

            return redirect("billing:clients")

        messages.error(
            request,
            "Please correct the errors in the registration form."
        )

    else:
        form = CustomerRegistrationForm()
        subscription_form = ClientSubscriptionForm()

    context = {
        "active_page": "billing_clients",
        "form": form,
        "subscription_form": subscription_form,
    }

    return render(
        request,
        "billing/add_client.html",
        context,
    )

@login_required
def plans(request):
    if request.session.get("password_recovery_pending"):
        return redirect("password_recovery_choice")

    internet_plans = (
        InternetPlan.objects
        .annotate(
            subscription_count=Count("subscriptions")
        )
        .order_by("monthly_price")
    )

    search_query = request.GET.get("q", "").strip()
    status = request.GET.get("status", "").strip()

    if search_query:
        internet_plans = internet_plans.filter(
            Q(plan_name__icontains=search_query)
            | Q(description__icontains=search_query)
        )

    if status == "active":
        internet_plans = internet_plans.filter(is_active=True)
    elif status == "inactive":
        internet_plans = internet_plans.filter(is_active=False)

    paginator = Paginator(internet_plans, 10)
    page_obj = paginator.get_page(request.GET.get("page"))

    context = {
        "active_page": "billing_plans",
        "page_obj": page_obj,
        "plans": page_obj.object_list,
        "search_query": search_query,
        "selected_status": status,
        "total_plans": InternetPlan.objects.count(),
        "active_plans": InternetPlan.objects.filter(is_active=True).count(),
        "inactive_plans": InternetPlan.objects.filter(is_active=False).count(),
    }

    return render(request, "billing/plans.html", context)


@login_required
def edit_client(request, pk):
    if not (
        request.user.is_superuser
        or request.user.role == "admin"
    ):
        raise PermissionDenied

    if request.session.get("password_recovery_pending"):
        return redirect("password_recovery_choice")

    customer = get_object_or_404(Customer, pk=pk)

    # Get the customer's current subscription.
    # Disconnected and cancelled subscriptions are treated as history.
    current_subscription = (
        customer.subscriptions
        .filter(status__in=[
            Subscription.Status.PENDING,
            Subscription.Status.ACTIVE,
            Subscription.Status.SUSPENDED,
        ])
        .order_by("-created_at")
        .first()
    )

    if request.method == "POST":
        form = CustomerRegistrationForm(
            request.POST,
            instance=customer,
        )

        subscription_form = ClientSubscriptionForm(
            request.POST,
            instance=current_subscription,
        )

        if form.is_valid() and subscription_form.is_valid():
            with transaction.atomic():
                customer = form.save()

                subscription = subscription_form.save(commit=False)
                subscription.customer = customer
                subscription.save()

                BillingActivity.objects.create(
                    user=request.user,
                    customer=customer,
                    action=BillingActivity.ActionType.CUSTOMER_UPDATED,
                    description=f"Updated client {customer.customer_id}.",
                )

            messages.success(
                request,
                f"Client {customer.customer_id} was updated successfully."
            )

            return redirect("billing:clients")

        messages.error(
            request,
            "Please correct the errors in the registration form."
        )

    else:
        form = CustomerRegistrationForm(instance=customer)

        subscription_form = ClientSubscriptionForm(
            instance=current_subscription,
        )

    return render(request, "billing/edit_client.html", {
        "active_page": "billing_clients",
        "form": form,
        "subscription_form": subscription_form,
        "customer": customer,
    })



@login_required
def toggle_client_status(request, pk):
    if not request.user.is_superuser:
        raise PermissionDenied

    if request.session.get("password_recovery_pending"):
        return redirect("password_recovery_choice")

    if request.method != "POST":
        raise PermissionDenied

    customer = get_object_or_404(Customer, pk=pk)

    customer.is_active = not customer.is_active
    customer.save(update_fields=["is_active", "updated_at"])

    action = "activated" if customer.is_active else "deactivated"

    BillingActivity.objects.create(
        user=request.user,
        customer=customer,
        action=BillingActivity.ActionType.CUSTOMER_UPDATED,
        description=f"Client {customer.customer_id} was {action}.",
    )

    messages.success(
        request,
        f"Client {customer.customer_id} was successfully {action}."
    )

    return_to = request.POST.get("return_to", "clients")

    if return_to == "edit":
        return redirect("billing:edit_client", pk=customer.pk)

    return redirect("billing:clients")

@login_required
def add_plan(request):
    if request.session.get("password_recovery_pending"):
        return redirect("password_recovery_choice")

    if request.method == "POST":
        form = InternetPlanForm(request.POST)

        if form.is_valid():
            plan = form.save()

            BillingActivity.objects.create(
                user=request.user,
                action=BillingActivity.ActionType.PLAN_CREATED,
                description=f"Created internet plan: {plan.plan_name}.",
            )

            messages.success(
                request,
                f"Internet plan {plan.plan_name} was created successfully."
            )
            return redirect("billing:plans")

    else:
        form = InternetPlanForm()

    return render(request, "billing/add_plan.html", {
        "active_page": "billing_plans",
        "form": form,
    })

@login_required
def edit_plan(request, pk):
    if not request.user.is_superuser:
        raise PermissionDenied

    if request.session.get("password_recovery_pending"):
        return redirect("password_recovery_choice")

    plan = get_object_or_404(InternetPlan, pk=pk)

    if request.method == "POST":
        form = InternetPlanForm(request.POST, instance=plan)

        if form.is_valid():
            plan = form.save()

            BillingActivity.objects.create(
                user=request.user,
                action=BillingActivity.ActionType.PLAN_UPDATED,
                description=f"Updated internet plan: {plan.plan_name}.",
            )

            messages.success(
                request,
                f"Internet plan {plan.plan_name} was updated successfully."
            )
            return redirect("billing:plans")

    else:
        form = InternetPlanForm(instance=plan)

    return render(request, "billing/edit_plan.html", {
        "active_page": "billing_plans",
        "form": form,
        "plan": plan,
    })

@login_required
def delete_plan(request, pk):
    if not request.user.is_superuser:
        raise PermissionDenied

    if request.session.get("password_recovery_pending"):
        return redirect("password_recovery_choice")

    if request.method != "POST":
        raise PermissionDenied

    plan = get_object_or_404(InternetPlan, pk=pk)
    plan_name = plan.plan_name

    try:
        plan.delete()

        messages.success(
            request,
            f"Internet plan {plan_name} was deleted successfully."
        )

    except ProtectedError:
        messages.error(
            request,
            f"Plan {plan_name} cannot be deleted because existing "
            "subscriptions are using it."
        )

    return redirect("billing:plans")

@login_required
def delete_all_plans(request):
    if not request.user.is_superuser:
        raise PermissionDenied

    if request.session.get("password_recovery_pending"):
        return redirect("password_recovery_choice")

    if request.method != "POST":
        raise PermissionDenied

    try:
        deleted_count, _ = InternetPlan.objects.all().delete()

        messages.success(
            request,
            f"Successfully deleted {deleted_count} database records."
        )

    except ProtectedError:
        messages.error(
            request,
            "Plans cannot be deleted because some are being used by "
            "existing subscriptions. Existing records were preserved."
        )

    return redirect("billing:plans")


