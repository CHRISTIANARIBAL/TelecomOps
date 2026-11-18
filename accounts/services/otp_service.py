import secrets

from datetime import timedelta

from django.conf import settings
from django.contrib.auth.hashers import make_password, check_password
from django.core.mail import send_mail
from django.utils import timezone

from accounts.models import EmailVerification, PasswordResetOTP


OTP_EXPIRY_MINUTES = 15
OTP_RESEND_SECONDS = 60
OTP_MAX_ATTEMPTS = 5


def generate_otp():
    return f"{secrets.randbelow(1000000):06d}"


def send_verification_email(user):
    now = timezone.now()
    
    latest = EmailVerification.objects.filter(
        user=user
    ).order_by('-created_at').first()

    if latest:
        elapsed = (now - latest.created_at).total_seconds()

        if elapsed < OTP_RESEND_SECONDS:
            raise ValueError(
                "Please wait before requesting another verification code."
            )

    code = generate_otp()

    # Invalidate previous unused codes.
    EmailVerification.objects.filter(
        user=user,
        is_used=False
    ).update(is_used=True)

    EmailVerification.objects.create(
        user=user,
        code_hash=make_password(code),
        expires_at=now + timedelta(minutes=OTP_EXPIRY_MINUTES)
    )

    send_mail(
        subject='Verify your TelecomOps account',
        message=(
            f'Hello {user.first_name or user.username},\n\n'
            f'Your TelecomOps verification code is: {code}\n\n'
            f'This code expires in {OTP_EXPIRY_MINUTES} minutes.\n\n'
            'If you did not request this registration, you can ignore this email.'
        ),
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[user.email],
        fail_silently=False,
    )

    return True



def verify_registration_otp(user, submitted_code):
    verification = EmailVerification.objects.filter(
        user=user,
        is_used=False
    ).order_by('-created_at').first()

    if verification is None:
        return False, "No active verification code was found."

    if not verification.is_valid():
        return False, "Your verification code has expired or reached its attempt limit."

    if not check_password(submitted_code, verification.code_hash):
        verification.attempts += 1

        if verification.attempts >= OTP_MAX_ATTEMPTS:
            verification.is_used = True

        verification.save(update_fields=['attempts', 'is_used'])

        remaining = OTP_MAX_ATTEMPTS - verification.attempts

        if remaining > 0:
            return False, (
                f"Incorrect verification code. "
                f"You have {remaining} attempts remaining."
            )

        return False, (
            "Too many incorrect attempts. "
            "Your verification code has been locked. "
            "Please request a new code."
        )

    verification.is_used = True
    verification.save(update_fields=['is_used'])

    user.email_verified = True
    user.save(update_fields=['email_verified'])

    user.update_activation_status()

    return True, "Email verified successfully."


def send_password_reset_otp(user):
    now = timezone.now()

    latest = PasswordResetOTP.objects.filter(
        user=user,
        is_used=False
    ).order_by('-created_at').first()

    if latest:
        elapsed = (now - latest.created_at).total_seconds()

        if elapsed < OTP_RESEND_SECONDS:
            raise ValueError(
                "Please wait before requesting another code."
            )

    code = generate_otp()

    # Invalidate older recovery codes.
    PasswordResetOTP.objects.filter(
        user=user,
        is_used=False
    ).update(is_used=True)

    otp = PasswordResetOTP.objects.create(
        user=user,
        code_hash=make_password(code),
        expires_at=now + timedelta(minutes=OTP_EXPIRY_MINUTES)
    )

    try:
        send_mail(
            subject="TelecomOps Password Recovery",
            message=(
                f"Hello {user.first_name or user.username},\n\n"
                f"Your password recovery code is: {code}\n\n"
                f"This code expires in {OTP_EXPIRY_MINUTES} minutes.\n\n"
                "If you did not request this, please ignore this email."
            ),
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[user.email],
            fail_silently=False,
        )
    except Exception:
        otp.is_used = True
        otp.save(update_fields=['is_used'])
        raise

    return True


def verify_password_reset_otp(user, submitted_code):
    otp = PasswordResetOTP.objects.filter(
        user=user,
        is_used=False
    ).order_by('-created_at').first()

    if otp is None:
        return False, "No active recovery code was found."

    if not otp.is_valid():
        return False, "Your code has expired or reached its attempt limit."

    if not check_password(submitted_code, otp.code_hash):
        otp.attempts += 1

        if otp.attempts >= OTP_MAX_ATTEMPTS:
            otp.is_used = True

        otp.save(update_fields=['attempts', 'is_used'])

        remaining = OTP_MAX_ATTEMPTS - otp.attempts

        if remaining > 0:
            return False, f"Incorrect code. You have {remaining} attempts remaining."

        return False, "Too many incorrect attempts. Please request a new code."

    otp.is_used = True
    otp.save(update_fields=['is_used'])

    return True, "Your email has been verified successfully."