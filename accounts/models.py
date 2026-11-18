from django.db import models
from django.contrib.auth.models import AbstractUser, UserManager
from django.utils import timezone
from datetime import timedelta
import secrets


# ==========================================
# CUSTOM USER MANAGER
# ==========================================


class CustomUserManager(UserManager):
    def create_superuser(self, username, email=None, password=None, **extra_fields):
        # Enforce single Super Admin account.
        if self.model.objects.filter(is_superuser=True).exists():
            raise ValueError(
                "A Super Admin account already exists. "
                "Only one Super Admin is allowed."
            )
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('is_active', True)
        extra_fields.setdefault('email_verified', True)
        extra_fields.setdefault('is_approved', True)
        extra_fields.setdefault('role', 'super_admin')
        extra_fields.setdefault('approval_status', 'approved')

        return super().create_superuser(
            username=username,
            email=email,
            password=password,
            **extra_fields
        )


# ==========================================
# CUSTOM USER MODEL
# ==========================================

class CustomUser(AbstractUser):

    class Role(models.TextChoices):
        SUPER_ADMIN = 'super_admin', 'Super Admin'
        ADMIN = 'admin', 'Admin'
        EMPLOYEE = 'employee', 'Employee'

    class ApprovalStatus(models.TextChoices):
        PENDING = 'pending', 'Pending Approval'
        APPROVED = 'approved', 'Approved'
        REJECTED = 'rejected', 'Rejected'
        SUSPENDED = 'suspended', 'Suspended'

    email = models.EmailField(
        unique=True,
        blank=False
    )
    is_active = models.BooleanField(default=False)

    role = models.CharField(
        max_length=30,
        choices=Role.choices,
        default=Role.EMPLOYEE
    )
    approval_status = models.CharField(
        max_length=20,
        choices=ApprovalStatus.choices,
        default=ApprovalStatus.PENDING
    )

    email_verified = models.BooleanField(
        default=False
    )

    is_approved = models.BooleanField(
        default=False
    )

    objects = CustomUserManager()


    def save(self, *args, **kwargs):
        # Prevent creating another Super Admin outside createsuperuser.
        if self._state.adding and self.role == self.Role.SUPER_ADMIN:
            if not self.is_superuser:
                raise ValueError(
                    "Super Admin accounts must be created through createsuperuser."
                )

            if CustomUser.objects.filter(is_superuser=True).exists():
                raise ValueError("Only one Super Admin account is allowed.")

        # Prevent creating a second regular Admin.
        if self._state.adding and self.role == self.Role.ADMIN:
            if CustomUser.objects.filter(role=self.Role.ADMIN).exists():
                raise ValueError("Only one Admin account is allowed.")

        # Prevent changing an existing account into another Super Admin.
        if not self._state.adding and self.role == self.Role.SUPER_ADMIN:
            if not self.is_superuser:
                raise ValueError(
                    "Only the terminal-created Super Admin can have this role."
                )

        super().save(*args, **kwargs)

    REQUIRED_FIELDS = ['email']
    
    def update_activation_status(self):
        if self.is_superuser:
            self.approval_status = self.ApprovalStatus.APPROVED
            self.is_approved = True
            self.is_active = True

        else:
            self.is_approved = (
                self.approval_status == self.ApprovalStatus.APPROVED
            )

            self.is_active = (
                self.email_verified and self.is_approved
            )

        self.save(update_fields=[
            'approval_status',
            'is_approved',
            'is_active',
        ])

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['role'],
                condition=models.Q(role='super_admin'),
                name='unique_super_admin_role',
            ),
            models.UniqueConstraint(
                fields=['role'],
                condition=models.Q(role='admin'),
                name='unique_regular_admin_role',
            ),
        ]

    def __str__(self):
        return f"{self.username} ({self.get_role_display()})"

# ==========================================
# EMAIL VERIFICATION
# ==========================================

class EmailVerification(models.Model):

    user = models.ForeignKey(
        CustomUser,
        on_delete=models.CASCADE,
        related_name='email_verifications'
    )

    code_hash = models.CharField(max_length=255)
    expires_at = models.DateTimeField()
    attempts = models.PositiveSmallIntegerField(default=0)
    is_used = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    @staticmethod
    def generate_code():
        return f"{secrets.randbelow(1000000):06d}"

    def is_valid(self):

        return (
            not self.is_used
            and self.attempts < 5
            and timezone.now() < self.expires_at
        )

    @staticmethod
    def expiration_time():
        return timezone.now() + timedelta(minutes=15)

    def __str__(self):
        return f"Email verification - {self.user.username}"


# ==========================================
# LOGIN OTP
# ==========================================

class LoginOTP(models.Model):

    user = models.ForeignKey(
        CustomUser,
        on_delete=models.CASCADE,
        related_name='login_otps'
    )

    code_hash = models.CharField(max_length=255)
    expires_at = models.DateTimeField()
    attempts = models.PositiveSmallIntegerField(default=0)
    is_used = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    @staticmethod
    def generate_code():
        return f"{secrets.randbelow(1000000):06d}"

    def is_valid(self):

        return (
            not self.is_used
            and self.attempts < 5
            and timezone.now() < self.expires_at
        )

    @staticmethod
    def expiration_time():
        return timezone.now() + timedelta(minutes=5)

    def __str__(self):
        return f"Login OTP - {self.user.username}"

class PasswordResetOTP(models.Model):
    user = models.ForeignKey(
        CustomUser,
        on_delete=models.CASCADE,
        related_name='password_reset_otps'
    )

    code_hash = models.CharField(max_length=255)
    expires_at = models.DateTimeField()
    attempts = models.PositiveSmallIntegerField(default=0)
    is_used = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def is_valid(self):
        return (
            not self.is_used
            and self.attempts < 5
            and timezone.now() < self.expires_at
        )

    def __str__(self):
        return f"Password reset OTP - {self.user.username}"


class LoginAttempt(models.Model):
    username = models.CharField(max_length=150)
    ip_address = models.GenericIPAddressField()
    failed_attempts = models.PositiveSmallIntegerField(default=0)
    locked_until = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['username', 'ip_address'],
                name='unique_login_attempt_username_ip'
            )
        ]

    def is_locked(self):
        return (
            self.locked_until is not None
            and timezone.now() < self.locked_until
        )

    def __str__(self):
        return f"{self.username} - {self.ip_address}"


class IPLoginAttempt(models.Model):
    ip_address = models.GenericIPAddressField(unique=True)
    failed_attempts = models.PositiveSmallIntegerField(default=0)
    window_started_at = models.DateTimeField(default=timezone.now)
    locked_until = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    def is_locked(self):
        return (
            self.locked_until is not None
            and timezone.now() < self.locked_until
        )

    def __str__(self):
        return f"{self.ip_address} - {self.failed_attempts} failures"
