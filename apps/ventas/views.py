from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.core import signing
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import DatabaseError, transaction
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect
from django.utils import timezone
from django.views.generic import DetailView, ListView

from apps.alquileres.reservas import expirar_solicitud_si_corresponde, puede_aprobar_reserva, solicitudes_afectadas
from apps.alquileres.bloqueos import bloquear_unidad
from apps.alquileres.models import SolicitudAlquiler
from apps.inventario.models import Unidad
from .forms import PagoAlquilerForm, ReembolsoDepositoForm, MotivosReservaForm
from .models import PresupuestoAlquiler, ReembolsoDeposito
from .consultas import presupuestos_con_pago_vencido


class AdministradorRequiredMixin(LoginRequiredMixin, UserPassesTestMixin):
    login_url = 'cuentas:login'

    def test_func(self):
        return self.request.user.es_administrador


class PresupuestoListaView(AdministradorRequiredMixin, ListView):
    model = PresupuestoAlquiler
    template_name = 'ventas/presupuesto_lista.html'
    context_object_name = 'presupuestos'
    paginate_by = 25

    def get_queryset(self):
        if self.request.GET.get('vencidos') == '1':
            return presupuestos_con_pago_vencido()
        return PresupuestoAlquiler.objects.select_related(
            'solicitud__cliente',
            'solicitud__unidad__maquinaria',
        ).prefetch_related('pagos')


class PresupuestoDetalleView(LoginRequiredMixin, DetailView):
    model = PresupuestoAlquiler
    template_name = 'ventas/presupuesto_detalle.html'
    context_object_name = 'presupuesto'
    pk_url_kwarg = 'presupuesto_id'

    def get_queryset(self):
        queryset = PresupuestoAlquiler.objects.select_related(
            'solicitud__cliente',
            'solicitud__unidad__maquinaria__categoria',
        ).prefetch_related('pagos__registrado_por')
        if self.request.user.es_administrador:
            return queryset
        if self.request.user.es_cliente:
            return queryset.filter(solicitud__cliente=self.request.user)
        return queryset.none()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.setdefault('pago_form', PagoAlquilerForm())
        context.setdefault('reembolso_form', ReembolsoDepositoForm())
        solicitud = self.object.solicitud
        context['mora_estimada'] = self.object.calcular_mora(
            solicitud.dias_atraso_actual
        )
        if self.request.user.es_administrador:
            afectadas = list(solicitudes_afectadas(solicitud)) if not solicitud.pago_inicial_completo else []
            motivos = context.setdefault('motivos_form', MotivosReservaForm(afectadas, self.request.POST if self.request.method == 'POST' else None))
            context['afectadas'] = [(s, motivos[f'motivo_{s.pk}']) for s in afectadas]
            context['revision_reserva'] = signing.dumps(datos_revision(solicitud, afectadas), salt='confirmar-reserva')
        return context


def datos_revision(solicitud, afectadas):
    return {
        'solicitud': solicitud.pk, 'unidad': solicitud.unidad_id,
        'inicio': solicitud.fecha_inicio.isoformat(), 'fin': solicitud.fecha_fin.isoformat(),
        'afectadas': [[s.pk, s.fecha_inicio.isoformat(), s.fecha_fin.isoformat(), s.estado] for s in afectadas],
    }


def mostrar_pago(request, presupuesto_id, form):
    vista = PresupuestoDetalleView()
    vista.setup(request, presupuesto_id=presupuesto_id)
    vista.object = vista.get_object()
    extras = {'pago_form': form}
    return vista.render_to_response(vista.get_context_data(**extras))


@login_required
def pago_registrar(request, presupuesto_id):
    if not request.user.es_administrador:
        raise PermissionDenied('Solo los administradores pueden registrar pagos.')
    if request.method != 'POST':
        return redirect('ventas:presupuesto_detalle', presupuesto_id=presupuesto_id)

    form = PagoAlquilerForm(request.POST)
    if not form.is_valid():
        return mostrar_pago(request, presupuesto_id, form)
    motivos = None
    try:
        with transaction.atomic():
            # Siempre unidad -> solicitud -> presupuesto, igual que entregas y retornos.
            referencia = SolicitudAlquiler.objects.filter(presupuesto__pk=presupuesto_id).values('unidad_id')
            try:
                unidad = bloquear_unidad(pk__in=referencia)
            except Unidad.DoesNotExist:
                raise Http404('Presupuesto no encontrado.')
            solicitud = get_object_or_404(SolicitudAlquiler.objects.select_for_update(), presupuesto__pk=presupuesto_id)
            expirar_solicitud_si_corresponde(solicitud.pk)
            solicitud.refresh_from_db()
            presupuesto = get_object_or_404(PresupuestoAlquiler.objects.select_for_update(), pk=presupuesto_id)
            presupuesto.solicitud = solicitud
            if solicitud.estado != 'Aprobada':
                messages.error(request, 'Solo se pueden registrar pagos de solicitudes aprobadas y vigentes.')
                return redirect('ventas:presupuesto_detalle', presupuesto_id=presupuesto_id)

            pago = form.save(commit=False)
            pago.presupuesto = presupuesto
            pago.registrado_por = request.user
            pago.full_clean()
            confirma = not solicitud.pago_inicial_completo and (
                presupuesto.renta_pendiente <= (pago.monto if pago.concepto == 'renta' else 0)
                and presupuesto.deposito_pendiente <= (pago.monto if pago.concepto == 'deposito' else 0)
            )
            if confirma:
                if not puede_aprobar_reserva(solicitud, unidad):
                    raise ValidationError('La unidad ya no está disponible en estas fechas. Revisa la reserva antes de guardar.')
                afectadas = list(solicitudes_afectadas(solicitud))
                motivos = MotivosReservaForm(afectadas, request.POST)
                try:
                    revision = signing.loads(request.POST.get('revision_reserva', ''), salt='confirmar-reserva')
                except signing.BadSignature:
                    revision = None
                if revision != datos_revision(solicitud, afectadas):
                    raise ValidationError('Cambió la lista de solicitudes afectadas o falta su revisión. Revisa el formulario antes de confirmar el pago y la reserva.')
                if not motivos.is_valid():
                    raise ValidationError('Escribe un motivo para cada solicitud afectada antes de confirmar el pago y la reserva.')
            pago.save()
            if confirma:
                ahora = timezone.now()
                solicitud.fecha_confirmacion = ahora
                solicitud.save(update_fields=['fecha_confirmacion'])
                unidad.estado = 'Alquilado'
                unidad.save(update_fields=['estado'])
                for afectada in afectadas:
                    afectada.estado = 'Rechazada'
                    afectada.motivo_rechazo = motivos.cleaned_data[f'motivo_{afectada.pk}']
                    afectada.revisado_por = request.user
                    afectada.fecha_revision = ahora
                    afectada.save(update_fields=['estado', 'motivo_rechazo', 'revisado_por', 'fecha_revision'])
        messages.success(request, 'El pago y la reserva se confirmaron correctamente.' if confirma else 'El pago se registró correctamente.')
        return redirect('ventas:presupuesto_detalle', presupuesto_id=presupuesto_id)
    except ValidationError as error:
        for mensaje in error.messages:
            form.add_error(None, mensaje)
    except DatabaseError:
        messages.error(request, 'No se guardaron cambios. Otra operación pudo cambiar la disponibilidad; revisa el formulario e inténtalo de nuevo.')
        # No volver a consultar mientras la confirmación concurrente conserva el bloqueo.
        return redirect('ventas:presupuesto_detalle', presupuesto_id=presupuesto_id)
    return mostrar_pago(request, presupuesto_id, form)


@login_required
@transaction.atomic
def reembolso_registrar(request, presupuesto_id):
    if not request.user.es_administrador:
        raise PermissionDenied(
            'Solo los administradores pueden registrar reembolsos.'
        )
    if request.method != 'POST':
        return redirect('ventas:presupuesto_detalle', presupuesto_id=presupuesto_id)

    presupuesto = get_object_or_404(
        PresupuestoAlquiler.objects.select_for_update().select_related('solicitud'),
        pk=presupuesto_id,
    )
    if not presupuesto.solicitud.fecha_retorno:
        messages.error(
            request,
            'El depósito solo se puede devolver después de registrar el retorno.',
        )
        return redirect('ventas:presupuesto_detalle', presupuesto_id=presupuesto.pk)

    form = ReembolsoDepositoForm(request.POST)
    if form.is_valid():
        reembolso = form.save(commit=False)
        reembolso.presupuesto = presupuesto
        reembolso.registrado_por = request.user
        try:
            reembolso.save()
        except ValidationError as error:
            for mensaje in error.messages:
                form.add_error(None, mensaje)
        else:
            messages.success(request, 'El reembolso del depósito se registró correctamente.')
            return redirect('ventas:presupuesto_detalle', presupuesto_id=presupuesto.pk)

    mensajes = '; '.join(
        error
        for errores in form.errors.values()
        for error in errores
    )
    messages.error(request, mensajes)
    return redirect('ventas:presupuesto_detalle', presupuesto_id=presupuesto.pk)
