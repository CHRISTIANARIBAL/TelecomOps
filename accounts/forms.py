from django import forms
from django.contrib.auth.forms import UserCreationForm, UserChangeForm

from .models import CustomUser


class CustomUserCreationForm(UserCreationForm):

    class Meta:
        model = CustomUser

        fields = (
            'username',
            'email',
            'first_name',
            'last_name',
            'role',
        )


class CustomUserChangeForm(UserChangeForm):

    class Meta:
        model = CustomUser

        fields = '__all__'



class SuperAdminAccountUpdateForm(forms.ModelForm):

    class Meta:
        model = CustomUser
        fields = (
            'first_name',
            'last_name',
            'username',
            'email',
            'role',
            'approval_status',
            'email_verified',
        )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Super Admin can never be assigned through the website.
        self.fields['role'].choices = [
            choice for choice in CustomUser.Role.choices
            if choice[0] != CustomUser.Role.SUPER_ADMIN
        ]

        # Dark-theme styling.
        for field_name, field in self.fields.items():
            widget = field.widget

            if isinstance(widget, forms.CheckboxInput):
                widget.attrs.update({
                    'class': 'telecomops-form-checkbox',
                })

            elif isinstance(widget, forms.Select):
                widget.attrs.update({
                    'class': 'telecomops-form-select',
                })

            else:
                widget.attrs.update({
                    'class': 'telecomops-form-input',
                })

    def clean_role(self):
        role = self.cleaned_data['role']

        # Employees cannot be promoted to Admin if one already exists.
        if role == CustomUser.Role.ADMIN:
            existing_admin = CustomUser.objects.filter(
                role=CustomUser.Role.ADMIN
            ).exclude(pk=self.instance.pk).exists()

            if existing_admin:
                raise forms.ValidationError(
                    'An Admin account already exists. '
                    'Only one Admin account is permitted.'
                )
        return role

    def clean_username(self):
        username = self.cleaned_data['username'].strip()

        existing_user = CustomUser.objects.filter(
            username__iexact=username
        ).exclude(pk=self.instance.pk)

        if existing_user.exists():
            raise forms.ValidationError(
                'This username is already taken.'
            )

        return username

    def clean_email(self):
        email = self.cleaned_data['email'].strip().lower()

        existing_user = CustomUser.objects.filter(
            email__iexact=email
        ).exclude(pk=self.instance.pk)

        if existing_user.exists():
            raise forms.ValidationError(
                'This email address is already registered.'
            )

        return email



class EmployeeRegistrationForm(UserCreationForm):

    email = forms.EmailField(required=True)

    first_name = forms.CharField(max_length=150, required=True)

    last_name = forms.CharField(max_length=150, required=True)

    class Meta:
        model = CustomUser

        fields = (
            'first_name',
            'last_name',
            'username',
            'email',
            'password1',
            'password2',
        )

    def clean_email(self):
        email = self.cleaned_data['email'].strip().lower()

        if CustomUser.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError(
                "This email address is already registered."
            )

        return email

    def clean_username(self):
        username = self.cleaned_data['username'].strip()

        if CustomUser.objects.filter(
            username__iexact=username
        ).exists():
            raise forms.ValidationError(
                "This username is already taken."
            )

        return username

    def save(self, commit=True):

        user = super().save(commit=False)

        user.email = self.cleaned_data['email']
        user.first_name = self.cleaned_data['first_name']
        user.last_name = self.cleaned_data['last_name']

        # Self-registration cannot choose privileged roles.
        user.role = CustomUser.Role.EMPLOYEE

        user.email_verified = False
        user.is_approved = False
        user.approval_status = CustomUser.ApprovalStatus.PENDING
        user.is_active = False
        user.is_staff = False
        user.is_superuser = False

        if commit:
            user.save()

        return user