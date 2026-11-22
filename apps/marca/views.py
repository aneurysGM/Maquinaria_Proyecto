from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db import transaction
from django.db.models import Count
from django.db.models.deletion import ProtectedError
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy
from django.views.generic import CreateView, ListView, UpdateView, View

from apps.inventario.views import InventarioRegistroRequiredMixin
from .forms import MarcaForm
from .models import Marca


class MarcaListaView(
    LoginRequiredMixin, InventarioRegistroRequiredMixin, ListView
):
    model = Marca
    template_name = 'marca/marca_lista.html'
    context_object_name = 'marcas'

    def get_queryset(self):
        return Marca.objects.annotate(
            cantidad_maquinarias=Count('maquinarias'),
        )


class MarcaCrearView(
    LoginRequiredMixin, InventarioRegistroRequiredMixin, CreateView
):
    form_class = MarcaForm
    template_name = 'marca/marca_form.html'
    success_url = reverse_lazy('marca:marca_lista')

    def form_valid(self, form):
        respuesta = super().form_valid(form)
        messages.success(self.request, 'La marca se registró correctamente.')
        return respuesta


class MarcaEditarView(
    LoginRequiredMixin, InventarioRegistroRequiredMixin, UpdateView
):
    model = Marca
    form_class = MarcaForm
    template_name = 'marca/marca_form.html'
    success_url = reverse_lazy('marca:marca_lista')
    pk_url_kwarg = 'marca_id'

    def form_valid(self, form):
        respuesta = super().form_valid(form)
        messages.success(self.request, 'La marca se actualizó correctamente.')
        return respuesta


class MarcaEliminarView(
    LoginRequiredMixin, InventarioRegistroRequiredMixin, View
):
    http_method_names = ['get', 'post', 'head', 'options']

    def get(self, request, marca_id):
        marca = get_object_or_404(Marca, pk=marca_id)
        return render(request, 'marca/marca_confirmar_eliminar.html', {
            'marca': marca,
            'equipos_asociados': marca.maquinarias.count(),
        })

    def post(self, request, marca_id):
        try:
            with transaction.atomic():
                marca = get_object_or_404(
                    Marca.objects.select_for_update(),
                    pk=marca_id,
                )
                if marca.maquinarias.exists():
                    messages.error(
                        request,
                        'No se puede borrar una marca asignada a maquinaria.',
                    )
                    return redirect('marca:marca_lista')
                marca.delete()
        except ProtectedError:
            messages.error(
                request,
                'No se puede borrar una marca asignada a maquinaria.',
            )
        else:
            messages.success(request, 'La marca se borró correctamente.')
        return redirect('marca:marca_lista')
