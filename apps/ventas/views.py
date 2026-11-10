from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect
from django.views.generic import DetailView, ListView

from apps.alquileres.reservas import expirar_solicitud_si_corresponde
from .forms import PagoAlquilerForm, ReembolsoDepositoForm
from .models import PresupuestoAlquiler, ReembolsoDeposito


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
        return context


@login_required
@transaction.atomic
def pago_registrar(request, presupuesto_id):
    if not request.user.es_administrador:
        raise PermissionDenied('Solo los administradores pueden registrar pagos.')
    if request.method != 'POST':
        return redirect('ventas:presupuesto_detalle', presupuesto_id=presupuesto_id)

    solicitud_id = PresupuestoAlquiler.objects.filter(
        pk=presupuesto_id,
    ).values_list('solicitud_id', flat=True).first()
    if solicitud_id is None:
        get_object_or_404(PresupuestoAlquiler, pk=presupuesto_id)

    expirar_solicitud_si_corresponde(solicitud_id)
    presupuesto = get_object_or_404(
        PresupuestoAlquiler.objects.select_for_update().select_related('solicitud'),
        pk=presupuesto_id,
    )
    if presupuesto.solicitud.estado != 'Aprobada':
        messages.error(
            request,
            'Solo se pueden registrar pagos de solicitudes aprobadas y vigentes.',
        )
        return redirect('ventas:presupuesto_detalle', presupuesto_id=presupuesto.pk)

    form = PagoAlquilerForm(request.POST)
    if form.is_valid():
        pago = form.save(commit=False)
        pago.presupuesto = presupuesto
        pago.registrado_por = request.user
        try:
            pago.save()
        except ValidationError as error:
            for mensaje in error.messages:
                form.add_error(None, mensaje)
        else:
            messages.success(request, 'El pago se registró correctamente.')
            return redirect('ventas:presupuesto_detalle', presupuesto_id=presupuesto.pk)

    messages.error(
        request,
        '; '.join(
            error
            for errors in form.errors.values()
            for error in errors
        ),
    )
    return redirect('ventas:presupuesto_detalle', presupuesto_id=presupuesto.pk)


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
