from django.db import transaction

from accounts.models import CustomUser


@transaction.atomic
def synchronize_account_status(user):

    user = CustomUser.objects.select_for_update().get(
        pk=user.pk
    )

    # Superusers are handled separately.
    if user.is_superuser:
        user.is_active = True

    else:
        user.is_active = (
            user.email_verified
            and user.is_approved
        )

    user.save(update_fields=['is_active'])

    return user