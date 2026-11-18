from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login, logout
from django.contrib import messages
from django.contrib.messages import get_messages
from django.contrib.auth import get_user_model, login
from django.views.decorators.http import require_POST
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import SetPasswordForm
from django.contrib.auth import update_session_auth_hash
from django.utils import timezone
from datetime import timedelta
from functools import wraps
from django.db import transaction
from django.db.models import Q
from .models import LoginAttempt, IPLoginAttempt
from .forms import EmployeeRegistrationForm, SuperAdminAccountUpdateForm
from .services.otp_service import (
    send_verification_email,
    verify_registration_otp,
    send_password_reset_otp,
    verify_password_reset_otp,
)

User = get_user_model()
LOGIN_MAX_ATTEMPTS = 5
LOGIN_LOCKOUT_MINUTES = 15
IP_MAX_ATTEMPTS = 10
IP_WINDOW_MINUTES = 15

def get_client_ip(request):
    return request.META.get('REMOTE_ADDR', '0.0.0.0')

def get_login_attempt(username, ip_address):
    return LoginAttempt.objects.filter(
        username=username.lower(),
        ip_address=ip_address
    ).first()

def get_ip_login_attempt(ip_address):
    return IPLoginAttempt.objects.filter(
        ip_address=ip_address
    ).first()

def record_failed_login(username, ip_address):
    now = timezone.now()

    with transaction.atomic():
        # Username + IP protection
        attempt, created = LoginAttempt.objects.get_or_create(
            username=username.lower(),
            ip_address=ip_address
        )

        attempt = LoginAttempt.objects.select_for_update().get(
            pk=attempt.pk
        )

        if attempt.locked_until and now >= attempt.locked_until:
            attempt.failed_attempts = 0
            attempt.locked_until = None

        attempt.failed_attempts += 1

        if attempt.failed_attempts >= LOGIN_MAX_ATTEMPTS:
            attempt.locked_until = now + timedelta(
                minutes=LOGIN_LOCKOUT_MINUTES
            )

        attempt.save()

        # IP-wide protection
        ip_attempt, created = IPLoginAttempt.objects.get_or_create(
            ip_address=ip_address
        )

        ip_attempt = IPLoginAttempt.objects.select_for_update().get(
            pk=ip_attempt.pk
        )

        # Reset the IP counter when its 15-minute window expires.
        if now >= ip_attempt.window_started_at + timedelta(
            minutes=IP_WINDOW_MINUTES
        ):
            ip_attempt.failed_attempts = 0
            ip_attempt.window_started_at = now
            ip_attempt.locked_until = None

        ip_attempt.failed_attempts += 1

        if ip_attempt.failed_attempts >= IP_MAX_ATTEMPTS:
            ip_attempt.locked_until = now + timedelta(
                minutes=LOGIN_LOCKOUT_MINUTES
            )

        ip_attempt.save()

        return attempt, ip_attempt


def clear_login_attempt(username, ip_address):
    # Clear only the username-specific counter.
    # Do not clear the IP-wide counter because other accounts
    # may have generated failures from the same address.
    LoginAttempt.objects.filter(
        username=username.lower(),
        ip_address=ip_address
    ).delete()



def login_view(request):
    if request.user.is_authenticated:
        return redirect('network_monitoring:dashboard')
    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        password = request.POST.get('password', '')
        ip_address = get_client_ip(request)
        if not username or not password:
            messages.error(
                request,
                'Please enter your username and password.'
            )
            return render(request, 'accounts/login.html')
        # Check IP-wide lockout first.
        ip_attempt = get_ip_login_attempt(ip_address)
        if ip_attempt and ip_attempt.is_locked():
            remaining_seconds = (
                ip_attempt.locked_until - timezone.now()
            ).total_seconds()
            remaining_minutes = max(
                1,
                int((remaining_seconds + 59) // 60)
            )
            messages.error(
                request,
                f'This network has reached its login attempt limit. '
                f'Please try again in approximately '
                f'{remaining_minutes} minute(s).'
            )
            return render(request, 'accounts/login.html')
        # Check username + IP lockout.
        attempt = get_login_attempt(username, ip_address)
        if attempt and attempt.is_locked():
            remaining_seconds = (
                attempt.locked_until - timezone.now()
            ).total_seconds()
            remaining_minutes = max(
                1,
                int((remaining_seconds + 59) // 60)
            )
            messages.error(
                request,
                f'Too many failed attempts for this username. '
                f'Please try again in approximately '
                f'{remaining_minutes} minute(s).'
            )
            return render(request, 'accounts/login.html')
        user = User.objects.filter(
            username__iexact=username
        ).first()
        if user and user.check_password(password):
            clear_login_attempt(username, ip_address)
            if user.is_superuser or user.is_active:
                authenticated_user = authenticate(
                    request,
                    username=user.username,
                    password=password
                )
                if authenticated_user is not None:
                    login(request, authenticated_user)
                    return redirect('network_monitoring:dashboard')
            else:
                if not user.email_verified:
                    messages.warning(
                        request,
                        'Your email address has not been verified. '
                        'Please complete email verification first.'
                    )
                elif user.approval_status == User.ApprovalStatus.REJECTED:
                    messages.error(
                        request,
                        'Your registration was not approved. '
                        'Please contact your system administrator.'
                    )
                elif user.approval_status == User.ApprovalStatus.SUSPENDED:
                    messages.error(
                        request,
                        'Your account has been suspended. '
                        'Please contact your system administrator.'
                    )
                elif user.approval_status == User.ApprovalStatus.PENDING:
                    messages.warning(
                        request,
                        'Your email has been verified, but your account '
                        'is still awaiting administrator approval.'
                    )
                else:
                    messages.error(
                        request,
                        'Your account is currently inactive. '
                        'Please contact your system administrator.'
                    )
        else:
            attempt, ip_attempt = record_failed_login(
                username,
                ip_address
            )
            if ip_attempt.is_locked():
                messages.error(
                    request,
                    'Too many failed login attempts from this network. '
                    'Login has been temporarily restricted for 15 minutes.'
                )
            elif attempt.is_locked():
                messages.error(
                    request,
                    'Too many incorrect login attempts for this username. '
                    'Please try again in 15 minutes.'
                )
            else:
                remaining_user = (
                    LOGIN_MAX_ATTEMPTS - attempt.failed_attempts
                )
                remaining_ip = (
                    IP_MAX_ATTEMPTS - ip_attempt.failed_attempts
                )
                messages.error(
                    request,
                    f'Invalid username or password. '
                    f'{remaining_user} username attempt(s) and '
                    f'{remaining_ip} network attempt(s) remaining.'
                )
    return render(request, 'accounts/login.html')


def admin_login_view(request):
    if request.user.is_authenticated:
        if request.user.role in [
            User.Role.SUPER_ADMIN,
            User.Role.ADMIN,
        ]:
            return redirect('admin_dashboard')

        messages.error(
            request,
            'You are already signed in with an employee account. '
            'Please log out first.'
        )
        return redirect('network_monitoring:dashboard')

    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        password = request.POST.get('password', '')
        ip_address = get_client_ip(request)

        if not username or not password:
            messages.error(
                request,
                'Please enter your username and password.'
            )
            return render(request, 'accounts/admin_login.html')

        # Check IP-wide lockout.
        ip_attempt = get_ip_login_attempt(ip_address)

        if ip_attempt and ip_attempt.is_locked():
            messages.error(
                request,
                'This network has reached its login attempt limit. '
                'Please try again later.'
            )
            return render(request, 'accounts/admin_login.html')

        # Check username + IP lockout.
        attempt = get_login_attempt(username, ip_address)

        if attempt and attempt.is_locked():
            messages.error(
                request,
                'Too many failed attempts for this username. '
                'Please try again later.'
            )
            return render(request, 'accounts/admin_login.html')

        user = User.objects.filter(
            username__iexact=username
        ).first()

        if user and user.check_password(password):
            authenticated_user = authenticate(
                request,
                username=user.username,
                password=password
            )

            if authenticated_user is not None:
                is_admin_role = authenticated_user.role in [
                    User.Role.SUPER_ADMIN,
                    User.Role.ADMIN,
                ]

                is_eligible = (
                    authenticated_user.is_active
                    and authenticated_user.email_verified
                    and authenticated_user.is_approved
                    and authenticated_user.approval_status
                    == User.ApprovalStatus.APPROVED
                )

                if is_admin_role and is_eligible:
                    clear_login_attempt(username, ip_address)
                    login(request, authenticated_user)
                    return redirect('admin_dashboard')

            # Use a generic error for invalid credentials or ineligible accounts.
            attempt, ip_attempt = record_failed_login(
                username,
                ip_address
            )

            if ip_attempt.is_locked():
                messages.error(
                    request,
                    'Too many failed login attempts from this network. '
                    'Login has been temporarily restricted for 15 minutes.'
                )

            elif attempt.is_locked():
                messages.error(
                    request,
                    'Too many incorrect login attempts for this username. '
                    'Please try again in 15 minutes.'
                )

            else:
                remaining_user = LOGIN_MAX_ATTEMPTS - attempt.failed_attempts
                remaining_ip = IP_MAX_ATTEMPTS - ip_attempt.failed_attempts

                messages.error(
                    request,
                    'Invalid administrator credentials or account access denied. '
                    f'{remaining_user} username attempt(s) and '
                    f'{remaining_ip} network attempt(s) remaining.'
                )

        else:
            attempt, ip_attempt = record_failed_login(
                username,
                ip_address
            )

            if ip_attempt.is_locked():
                messages.error(
                    request,
                    'Too many failed login attempts from this network. '
                    'Login has been temporarily restricted for 15 minutes.'
                )

            elif attempt.is_locked():
                messages.error(
                    request,
                    'Too many incorrect login attempts for this username. '
                    'Please try again in 15 minutes.'
                )

            else:
                remaining_user = LOGIN_MAX_ATTEMPTS - attempt.failed_attempts
                remaining_ip = IP_MAX_ATTEMPTS - ip_attempt.failed_attempts

                messages.error(
                    request,
                    'Invalid administrator credentials or account access denied. '
                    f'{remaining_user} username attempt(s) and '
                    f'{remaining_ip} network attempt(s) remaining.'
                )

    return render(request, 'accounts/admin_login.html')


@require_POST
@login_required
def logout_view(request):

    # Clear pending notifications before ending the session.
    list(get_messages(request))

    logout(request)

    return redirect('login')

# ==========================================
# EMPLOYEE REGISTRATION
# ==========================================

def register_view(request):

    if request.user.is_authenticated:
        return redirect('network_monitoring:dashboard')

    if request.method == 'POST':

        form = EmployeeRegistrationForm(request.POST)

        if form.is_valid():

            user = form.save()

            request.session['registration_user_id'] = user.pk

            try:
                send_verification_email(user)

                messages.success(
                    request,
                    'Your account was created. '
                    'We sent a verification code to your email.'
                )

                return redirect('verify_registration')

            except Exception:
                # Keep the account inactive if email delivery fails.
                messages.error(
                    request,
                    'Your registration was saved, but we could not send '
                    'the verification email. Please try again shortly.'
                )

                return redirect('verify_registration')

    else:
        form = EmployeeRegistrationForm()

    return render(
        request,
        'accounts/register.html',
        {'form': form}
    )

# ==========================================
# FORGOT PASSWORD
# ==========================================

def forgot_password_view(request):
    if request.user.is_authenticated:
        return redirect('network_monitoring:dashboard')

    if request.method == 'POST':
        email = request.POST.get('email', '').strip()

        user = User.objects.filter(
            email__iexact=email,
            is_active=True,
            email_verified=True,
            approval_status=User.ApprovalStatus.APPROVED,
            is_approved=True,
        ).first()

        request.session.pop('recovery_user_id', None)

        if user:
            try:
                send_password_reset_otp(user)
                request.session['recovery_user_id'] = user.pk
            except Exception:
                pass

        messages.info(
            request,
            'If an eligible account exists for that email, '
            'a recovery code will be sent.'
        )

        return redirect('verify_password_otp')

    return render(request, 'accounts/forgot_password.html')


# ==========================================
# PASSWORD RECOVERY OTP
# ==========================================

from django.contrib import messages
from django.shortcuts import render, redirect
from django.contrib.auth import get_user_model

from .services.otp_service import verify_password_reset_otp

User = get_user_model()


def verify_password_otp_view(request):
    user_id = request.session.get('recovery_user_id')

    if not user_id:
        messages.error(request, "Please request a new recovery code.")
        return redirect('forgot_password')

    user = User.objects.filter(
        pk=user_id,
        is_active=True,
        email_verified=True,
        is_approved=True,
        approval_status=User.ApprovalStatus.APPROVED,
    ).first()

    if not user:
        request.session.pop('recovery_user_id', None)
        messages.error(request, "Your recovery session is invalid. Please start again.")
        return redirect('forgot_password')

    if request.method == 'POST':
        code = request.POST.get('code', '').strip()

        if not code.isdigit() or len(code) != 6:
            messages.error(request, "Please enter a valid six-digit code.")
            return render(request, 'accounts/verify_password_otp.html', {
                'entered_code': code,
            })

        success, message = verify_password_reset_otp(user, code)

        if success:
            request.session.pop('recovery_user_id', None)

            login(
                request,
                user,
                backend='django.contrib.auth.backends.ModelBackend'
            )

            request.session['password_recovery_pending'] = True

            return redirect('password_recovery_choice')

        messages.error(request, message)

        return render(request, 'accounts/verify_password_otp.html', {
            'entered_code': code,
        })

    return render(request, 'accounts/verify_password_otp.html')

@require_POST
def resend_password_reset_otp(request):
    user_id = request.session.get('recovery_user_id')

    user = User.objects.filter(
        pk=user_id,
        is_active=True,
        email_verified=True,
        is_approved=True,
        approval_status=User.ApprovalStatus.APPROVED,
    ).first() if user_id else None

    if user:
        try:
            send_password_reset_otp(user)
        except ValueError as error:
            messages.warning(request, str(error))
        except Exception:
            messages.error(
                request,
                'Unable to send a recovery code. Please try again later.'
            )

    return redirect('verify_password_otp')

# ==========================================
# RECOVERY PASSWORD DECISION
# ==========================================

@login_required
def password_recovery_choice_view(request):

    if not request.session.get('password_recovery_pending'):
        return redirect('network_monitoring:dashboard')

    form = SetPasswordForm(request.user)

    if request.method == 'POST':
        action = request.POST.get('action')

        if action == 'skip':
            request.session.pop('password_recovery_pending', None)
            return redirect('network_monitoring:dashboard')

        if action == 'change':
            form = SetPasswordForm(request.user, request.POST)

            if form.is_valid():
                form.save()
                update_session_auth_hash(request, request.user)

                request.session.pop(
                    'password_recovery_pending',
                    None
                )

                messages.success(
                    request,
                    'Your password has been changed successfully.'
                )

                return redirect('network_monitoring:dashboard')

    return render(
        request,
        'accounts/password_recovery_choice.html',
        {'form': form}
    )
# ==========================================
# REGISTRATION EMAIL VERIFICATION
# ==========================================


def verify_registration_view(request):
    user_id = request.session.get('registration_user_id')

    if not user_id:
        messages.error(
            request,
            'Please register first before verifying your email.'
        )
        return redirect('register')

    user = User.objects.filter(
        pk=user_id,
        is_active=False
    ).first()

    if user is None:
        request.session.pop('registration_user_id', None)
        return redirect('login')

    if user.email_verified:
        return redirect('registration_status')

    entered_code = ''

    if request.method == 'POST':
        code = request.POST.get('code', '').strip()
        entered_code = code

        if not code.isdigit() or len(code) != 6:
            messages.error(
                request,
                'Please enter a valid six-digit verification code.'
            )
        else:
            success, message = verify_registration_otp(user, code)

            if success:
                messages.success(
                    request,
                    'Your email has been verified. '
                    'Your registration is now awaiting administrator approval.'
                )
                return redirect('registration_status')

            messages.error(request, message)

    return render(
        request,
        'accounts/verify_email.html',
        {
            'user': user,
            'entered_code': entered_code,
        }
    )



# ==========================================
# RESEND REGISTRATION OTP
# ==========================================

@require_POST
def resend_registration_otp(request):

    user_id = request.session.get('registration_user_id')

    if not user_id:
        messages.error(request, 'Registration session not found.')
        return redirect('register')

    user = User.objects.filter(
        pk=user_id,
        email_verified=False,
        is_active=False
    ).first()

    if not user:
        return redirect('login')

    try:
        send_verification_email(user)

        messages.success(
            request,
            'A new verification code has been sent.'
        )

    except ValueError as error:
        messages.warning(request, str(error))

    except Exception:
        messages.error(
            request,
            'Unable to send your verification code. Please try again later.'
        )

    return redirect('verify_registration')


# ==========================================
# REGISTRATION STATUS
# ==========================================

def registration_status_view(request):

    user_id = request.session.get('registration_user_id')

    if not user_id:
        messages.info(
            request,
            'Please register or sign in to view your account status.'
        )
        return redirect('login')

    user = User.objects.filter(pk=user_id).first()

    if not user:
        request.session.pop('registration_user_id', None)
        return redirect('register')

    return render(
        request,
        'accounts/registration_status.html',
        {'user': user}
    )

def super_admin_required(view_func):
    @wraps(view_func)
    @login_required
    def _wrapped_view(request, *args, **kwargs):
        user = request.user

        is_super_admin = (
            user.is_authenticated
            and user.is_superuser
            and user.role == User.Role.SUPER_ADMIN
            and user.is_active
            and user.email_verified
            and user.is_approved
            and user.approval_status == User.ApprovalStatus.APPROVED
        )

        if not is_super_admin:
            messages.error(
                request,
                'Only the Super Admin is authorized to access this page.'
            )

            if user.role in [User.Role.SUPER_ADMIN, User.Role.ADMIN]:
                return redirect('admin_dashboard')

            return redirect('network_monitoring:dashboard')

        return view_func(request, *args, **kwargs)

    return _wrapped_view

@super_admin_required
def registration_approvals_view(request):
    pending_employees = User.objects.filter(
        role=User.Role.EMPLOYEE,
        approval_status=User.ApprovalStatus.PENDING,
        email_verified=True
    ).order_by('-date_joined')

    context = {
        'pending_employees': pending_employees,
        'pending_count': pending_employees.count(),
        'active_page': 'registration_approvals',
    }

    return render(
        request,
        'accounts/registration_approvals.html',
        context
    )

@login_required
def admin_dashboard(request):
    user = request.user

    # Only approved administrators can access this portal.
    is_admin_role = user.role in [
        User.Role.SUPER_ADMIN,
        User.Role.ADMIN,
    ]

    is_eligible = (
        user.is_active
        and user.email_verified
        and user.is_approved
        and user.approval_status == User.ApprovalStatus.APPROVED
    )

    if not is_admin_role or not is_eligible:
        messages.error(
            request,
            'You are not authorized to access the administrator portal.'
        )
        return redirect('network_monitoring:dashboard')

    return render(
        request,
        'accounts/admin_dashboard.html',
        {
            'active_page': 'admin_dashboard',
        }
    )


@super_admin_required
def user_accounts_view(request):
    all_accounts = User.objects.all()

    # Get search input.
    search_query = request.GET.get('search', '').strip()

    # Apply database search.
    accounts = all_accounts

    if search_query:
        search_filter = (
            Q(username__icontains=search_query)
            | Q(first_name__icontains=search_query)
            | Q(last_name__icontains=search_query)
            | Q(email__icontains=search_query)
        )

        # Allow searching by exact account ID.
        if search_query.isdigit():
            search_filter |= Q(pk=int(search_query))

        accounts = accounts.filter(search_filter)

    accounts = accounts.order_by('-date_joined')

    context = {
        'accounts': accounts,
        'search_query': search_query,

        # Summary cards always show totals for all accounts.
        'total_accounts': all_accounts.count(),
        'active_accounts': all_accounts.filter(
            is_active=True
        ).count(),
        'pending_accounts': all_accounts.filter(
            approval_status=User.ApprovalStatus.PENDING
        ).count(),
        'suspended_accounts': all_accounts.filter(
            approval_status=User.ApprovalStatus.SUSPENDED
        ).count(),

        'active_page': 'user_accounts',
    }

    return render(
        request,
        'accounts/user_accounts.html',
        context
    )


# ==========================================
# SUPER ADMIN - MANAGE USER ACCOUNT
# ==========================================

@super_admin_required
def manage_user_account_view(request, user_id):

    account = get_object_or_404(
        User,
        pk=user_id
    )

    # Protect the single Super Admin account.
    if (
        account.is_superuser
        or account.role == User.Role.SUPER_ADMIN
    ):
        messages.error(
            request,
            'The Super Admin account cannot be managed from this page.'
        )
        return redirect('user_accounts')

    if request.method == 'POST':

        form = SuperAdminAccountUpdateForm(
            request.POST,
            instance=account
        )

        
        if form.is_valid():
            form.save()

            # Automatically synchronize account activation
            # with email verification and approval status.
            account.update_activation_status()

            messages.success(
                request,
                f'{account.username} account has been updated successfully.'
            )

            return redirect('user_accounts')


    else:

        form = SuperAdminAccountUpdateForm(
            instance=account
        )

    context = {
        'account': account,
        'form': form,
        'active_page': 'user_accounts',
    }

    return render(
        request,
        'accounts/manage_user_account.html',
        context
    )
