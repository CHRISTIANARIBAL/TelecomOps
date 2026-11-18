from django.urls import path
from . import views

urlpatterns = [
    path('', views.login_view, name='login'),

    path('admin-login/', views.admin_login_view, name='admin_login'),
    path('admin-portal/', views.admin_dashboard, name='admin_dashboard'),
    path('admin-portal/registration-approvals/', views.registration_approvals_view, name='registration_approvals'),
    path('admin-portal/user-accounts/', views.user_accounts_view, name='user_accounts'),
    path('admin-portal/user-accounts/<int:user_id>/', views.manage_user_account_view, name='manage_user_account'),

    path('logout/', views.logout_view, name='logout'),
    path('register/', views.register_view, name='register'),
    path('verify-email/', views.verify_registration_view, name='verify_registration'),
    path('resend-verification/', views.resend_registration_otp, name='resend_registration_otp'),
    path('registration-status/', views.registration_status_view, name='registration_status'),
    path('forgot-password/', views.forgot_password_view, name='forgot_password'),
    path('verify-password-otp/', views.verify_password_otp_view, name='verify_password_otp'),
    path('resend-password-otp/', views.resend_password_reset_otp, name='resend_password_reset_otp'),
    path('password-recovery-choice/', views.password_recovery_choice_view, name='password_recovery_choice'),
]