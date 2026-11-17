"""Guard authentication form writes when an account is erased concurrently."""
from django.contrib.auth.forms import AdminPasswordChangeForm, PasswordChangeForm, SetPasswordForm
from django.contrib.auth.hashers import check_password
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils.crypto import constant_time_compare
from django.views.decorators.debug import sensitive_variables

from .models import User


class LockedPasswordSave:
    must_be_active = True

    @transaction.atomic
    def save(self, commit=True):
        saved_user = self.user
        locked = User.objects.select_for_update().get(pk=saved_user.pk)
        if locked.erased_at or (self.must_be_active and not locked.is_active) or not constant_time_compare(saved_user.password, locked.password):
            raise PermissionDenied
        self.user = locked
        changed = super().save(commit=False)
        if commit:
            changed.save(update_fields=['password'])
        return changed


class LockedPasswordChangeForm(LockedPasswordSave, PasswordChangeForm):
    @sensitive_variables('password')
    def clean_old_password(self):
        password = self.cleaned_data['old_password']
        if not check_password(password, self.user.password):
            raise ValidationError(self.error_messages['password_incorrect'], code='password_incorrect')
        return password


class LockedSetPasswordForm(LockedPasswordSave, SetPasswordForm):
    pass


class LockedAdminPasswordChangeForm(LockedPasswordSave, AdminPasswordChangeForm):
    must_be_active = False
