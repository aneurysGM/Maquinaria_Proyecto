from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase


class ConservacionDatosMantenimientoTests(TransactionTestCase):
    def test_migraciones_conservan_perfiles_y_mantenimientos_previos(self):
        executor = MigrationExecutor(connection)
        anteriores = [
            ('cuentas', '0004_usuariopersonalizado_primer_inicio_sesion'),
            ('mantenimiento', '0001_initial'),
            ('tecnico_mantenimiento', None),
        ]
        finales = executor.loader.graph.leaf_nodes()
        executor.migrate(anteriores)
        try:
            executor = MigrationExecutor(connection)
            apps = executor.loader.project_state(list(executor.loader.applied_migrations)).apps
            Usuario = apps.get_model('cuentas', 'UsuarioPersonalizado')
            Categoria = apps.get_model('inventario', 'Categoria')
            Maquinaria = apps.get_model('inventario', 'Maquinaria')
            Unidad = apps.get_model('inventario', 'Unidad')
            Mantenimiento = apps.get_model('mantenimiento', 'Mantenimiento')
            tecnico = Usuario.objects.create(
                email='historico-tecnico@example.com', rol='Técnico', especialidad='Motores antiguos',
                first_name='Técnico previo', password='conservar-hash', is_active=False,
            )
            admin = Usuario.objects.create(email='historico-admin@example.com', rol='Administrador')
            categoria = Categoria.objects.create(nombre='Histórica')
            maquinaria = Maquinaria.objects.create(
                categoria=categoria, codigo='HIST-001', nombre='Histórica', costo_adquisicion=1000,
                tarifa_diaria=100, tarifa_semanal=700, tarifa_mensual=3000,
            )
            unidad = Unidad.objects.create(maquinaria=maquinaria, numero_serie='HIST-001', estado='Mantenimiento')
            for autor in (tecnico, admin, None):
                Mantenimiento.objects.create(
                    unidad=unidad, tecnico=autor, fecha='2026-10-01', tipo='Preventivo',
                    descripcion='Registro previo', costo='50.00',
                )
            usuarios_antes = list(Usuario.objects.order_by('pk').values())
            mantenimientos_antes = list(Mantenimiento.objects.order_by('pk').values())
        finally:
            executor = MigrationExecutor(connection)
            executor.migrate(finales)

        apps = executor.loader.project_state(finales).apps
        Usuario = apps.get_model('cuentas', 'UsuarioPersonalizado')
        Mantenimiento = apps.get_model('mantenimiento', 'Mantenimiento')
        Especialidad = apps.get_model('tecnico_mantenimiento', 'EspecialidadTecnica')
        usuarios_despues = list(Usuario.objects.order_by('pk').values())
        for usuario in usuarios_despues:
            self.assertTrue(usuario.pop('disponible'))
        self.assertEqual(usuarios_antes, usuarios_despues)
        mantenimientos_despues = list(Mantenimiento.objects.order_by('pk').values())
        for mantenimiento in mantenimientos_despues:
            self.assertEqual(mantenimiento.pop('registrado_por_id'), mantenimiento['tecnico_id'])
        self.assertEqual(mantenimientos_antes, mantenimientos_despues)
        self.assertSetEqual(set(Especialidad.objects.values_list('nombre', flat=True)), {
            'Hidráulica', 'Electricidad', 'Mecánica', 'Motores antiguos',
        })
