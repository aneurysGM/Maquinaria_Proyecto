from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend
from django.utils import timezone


def reactivar_suspensiones_vencidas():
    return get_user_model().objects.filter(
        is_active=False,
        suspension_hasta__lte=timezone.localdate(),
    ).update(is_active=True, suspension_hasta=None)


class SuspensionBackend(ModelBackend):
    def authenticate(self, request, username=None, password=None, **kwargs):
        if username is None:
            username = kwargs.get('email')
        if username is None or password is None:
            return None

        user_model = get_user_model()
        try:
            user = user_model._default_manager.get_by_natural_key(username)
        except user_model.DoesNotExist:
            user_model().set_password(password)
            return None

        if not user.check_password(password):
            return None

        if (
            not user.is_active
            and user.suspension_hasta
            and user.suspension_hasta <= timezone.localdate()
        ):
            user.is_active = True
            user.suspension_hasta = None
            user.save(update_fields=['is_active', 'suspension_hasta'])

        if self.user_can_authenticate(user):
            return user
        return None
