from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.core.exceptions import PermissionDenied
from .models import CustomUser, EmailVerification, LoginOTP
from .forms import CustomUserCreationForm, CustomUserChangeForm


@admin.register(CustomUser)
class CustomUserAdmin(UserAdmin):
    def save_model(self, request, obj, form, change):
        # Protect the existing Super Admin account.
        if change and obj.pk:
            original_user = CustomUser.objects.get(pk=obj.pk)

            if original_user.is_superuser:
                obj.role = CustomUser.Role.SUPER_ADMIN
                obj.is_superuser = True
                obj.is_staff = True
                obj.approval_status = CustomUser.ApprovalStatus.APPROVED
                obj.is_approved = True
                obj.is_active = True
                obj.email_verified = True

        super().save_model(request, obj, form, change)

        obj.update_activation_status()

    form = CustomUserChangeForm
    add_form = CustomUserCreationForm

    actions = [
        'approve_selected_users',
        'reject_selected_users',
        'suspend_selected_users',
    ]

    def get_actions(self, request):

        actions = super().get_actions(request)

        # Only the single Super Admin can manage employee approvals.
        is_super_admin = (
            request.user.is_authenticated
            and request.user.is_superuser
            and request.user.role == CustomUser.Role.SUPER_ADMIN
        )

        if not is_super_admin:
            actions.pop('approve_selected_users', None)
            actions.pop('reject_selected_users', None)
            actions.pop('suspend_selected_users', None)

        return actions


    list_display = ('username', 'email', 'role', 'email_verified', 'approval_status', 'is_approved', 'is_active', 'is_staff')
    list_filter = ('role', 'email_verified', 'is_approved', 'is_active', 'is_staff')
    search_fields = ('username', 'email', 'first_name', 'last_name')
    ordering = ('username',)
    readonly_fields = ('is_approved', 'is_active')
    
    fieldsets = (
        ('Account Information', {
            'fields': (
                'username','password','first_name','last_name','email',
            )
        }),

        ('Employee Permissions', {
            'fields': (
                'role','approval_status','email_verified','is_approved','is_active','is_staff','is_superuser','groups','user_permissions',
            )
        }),

        ('Important Dates', {
            'fields': (
                'last_login',
                'date_joined',
            )
        }),
    )


    add_fieldsets = (
        ('Create Employee Account', {
            'classes': ('wide',),
            'fields': (
                'username',
                'email',
                'first_name',
                'last_name',
                'role',
                'password1',
                'password2',
            ),
        }),
    )

    @admin.action(description='Approve selected employee accounts')
    def approve_selected_users(self, request, queryset):
        if not (
            request.user.is_authenticated
            and request.user.is_superuser
            and request.user.role == CustomUser.Role.SUPER_ADMIN
        ):
            raise PermissionDenied(
                "Only the Super Admin can approve employee accounts."
            )

        updated = 0

        for user in queryset:

            if user.is_superuser:
                continue

            user.is_approved = True
            user.approval_status = CustomUser.ApprovalStatus.APPROVED

            user.update_activation_status()

            updated += 1

        self.message_user(
            request,
            f'{updated} employee account(s) approved.'
        )


    @admin.action(description='Reject selected employee accounts')
    def reject_selected_users(self, request, queryset):
        if not (
            request.user.is_authenticated
            and request.user.is_superuser
            and request.user.role == CustomUser.Role.SUPER_ADMIN
        ):
            raise PermissionDenied(
                "Only the Super Admin can reject employee accounts."
            )

        updated = 0

        for user in queryset:

            if user.is_superuser:
                continue

            user.is_approved = False
            user.approval_status = CustomUser.ApprovalStatus.REJECTED

            user.update_activation_status()

            updated += 1

        self.message_user(
            request,
            f'{updated} employee account(s) rejected.'
        )


    @admin.action(description='Suspend selected employee accounts')
    def suspend_selected_users(self, request, queryset):
        if not (
            request.user.is_authenticated
            and request.user.is_superuser
            and request.user.role == CustomUser.Role.SUPER_ADMIN
        ):
            raise PermissionDenied(
                "Only the Super Admin can suspend employee accounts."
            )

        updated = 0

        for user in queryset:

            if user.is_superuser:
                continue

            user.is_approved = False
            user.approval_status = CustomUser.ApprovalStatus.SUSPENDED

            user.update_activation_status()

            updated += 1

        self.message_user(
            request,
            f'{updated} employee account(s) suspended.'
        )


@admin.register(EmailVerification)
class EmailVerificationAdmin(admin.ModelAdmin):

    list_display = (
        'user',
        'expires_at',
        'attempts',
        'is_used',
        'created_at',
    )

    readonly_fields = (
        'user',
        'code_hash',
        'expires_at',
        'attempts',
        'is_used',
        'created_at',
    )


@admin.register(LoginOTP)
class LoginOTPAdmin(admin.ModelAdmin):

    list_display = (
        'user',
        'expires_at',
        'attempts',
        'is_used',
        'created_at',
    )

    readonly_fields = (
        'user',
        'code_hash',
        'expires_at',
        'attempts',
        'is_used',
        'created_at',
    )