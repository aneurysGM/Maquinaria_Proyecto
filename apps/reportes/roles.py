def puede_ver_reportes(usuario):
    return bool(
        usuario.is_authenticated
        and usuario.is_active
        and usuario.is_superuser
    )
