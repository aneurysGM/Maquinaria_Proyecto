from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import DatabaseError, transaction
from django.db.models import Q
from django.urls import reverse_lazy
from django.views.generic import ListView, CreateView, UpdateView, DetailView, View
from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect
from django.http import HttpResponseRedirect
from .models import Categoria, Maquinaria, Unidad
from .forms import (
    CategoriaForm,
    MaquinariaComentarioForm,
    MaquinariaImagenFormSet,
    MaquinariaIntegralForm,
)


class CatalogoPublicoView(ListView):
    model = Unidad
    template_name = 'publico/catalogo.html'
    context_object_name = 'maquinarias'

    def get_queryset(self):
        queryset = Unidad.objects.select_related(
            'maquinaria__categoria'
        ).filter(
            activo=True,
            estado='Disponible',
            maquinaria__activo=True,
        )

        query = self.request.GET.get('q', '').strip()
        if query:
            queryset = queryset.filter(
                Q(maquinaria__nombre__icontains=query)
                | Q(maquinaria__codigo__icontains=query)
                | Q(maquinaria__marca__icontains=query)
                | Q(maquinaria__categoria__nombre__icontains=query)
            )

        categoria_id = self.request.GET.get('categoria', '')
        if categoria_id:
            if categoria_id.isdecimal():
                queryset = queryset.filter(maquinaria__categoria_id=categoria_id)
            else:
                queryset = queryset.none()

        orden = self.request.GET.get('orden', 'recientes')
        ordenes = {
            'recientes': '-maquinaria__fecha_modificacion',
            'precio_bajo': 'maquinaria__tarifa_diaria',
            'precio_alto': '-maquinaria__tarifa_diaria',
        }
        return queryset.order_by(ordenes.get(orden, ordenes['recientes']))

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['categorias'] = Categoria.objects.all()
        return context


# --- Mixins de permisos para el módulo de Inventario ---
class InventarioConsultaRequiredMixin(UserPassesTestMixin):
    """Permite consultar el inventario solo a cuentas con un rol vigente."""

    def test_func(self):
        return self.request.user.puede_consultar_maquinaria


class InventarioRegistroRequiredMixin(UserPassesTestMixin):
    """Permite modificar el inventario únicamente al Administrador."""

    def test_func(self):
        return self.request.user.puede_registrar_maquinaria


class MaquinariaImagenesMixin:
    def get_imagenes_formset(self, form=None):
        if not hasattr(self, '_imagenes_formset'):
            if form is not None:
                maquinaria = form.instance
            elif isinstance(self.object, Unidad):
                maquinaria = self.object.maquinaria
            else:
                maquinaria = self.object

            data = self.request.POST if self.request.method == 'POST' else None
            files = self.request.FILES if self.request.method == 'POST' else None
            self._imagenes_formset = MaquinariaImagenFormSet(
                data=data,
                files=files,
                instance=maquinaria,
            )
        return self._imagenes_formset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['imagenes_formset'] = self.get_imagenes_formset(
            context.get('form')
        )
        return context

    def form_valid(self, form):
        imagenes_formset = self.get_imagenes_formset(form)
        if not imagenes_formset.is_valid():
            return self.form_invalid(form)

        es_edicion = bool(form.unidad_instancia)
        if not form.instance.pk or form.maquinaria_reactivada:
            form.instance.registrada_por = self.request.user

        try:
            with transaction.atomic():
                self.object = form.save()
                imagenes_formset.instance = self.object
                imagenes_formset.save()
        except ValidationError as error:
            for mensaje in error.messages:
                form.add_error(None, mensaje)
            return self.form_invalid(form)
        except DatabaseError:
            form.add_error(None, 'No se pudo guardar. Actualiza el formulario e inténtalo de nuevo.')
            return self.form_invalid(form)

        if getattr(form, 'maquinaria_reactivada', None):
            mensaje = 'La maquinaria y su unidad se reactivaron correctamente.'
        elif es_edicion:
            mensaje = 'Los datos de la maquinaria se actualizaron correctamente.'
        else:
            mensaje = 'La maquinaria y unidad se guardaron correctamente.'
        messages.success(self.request, mensaje)
        return HttpResponseRedirect(self.get_success_url())

# --- Vistas de Categorías ---
class CategoriaListaView(LoginRequiredMixin, InventarioRegistroRequiredMixin, ListView):
    model = Categoria
    template_name = 'inventario/categoria_lista.html'
    context_object_name = 'categorias'

class CategoriaCrearView(LoginRequiredMixin, InventarioRegistroRequiredMixin, CreateView):
    model = Categoria
    form_class = CategoriaForm
    template_name = 'inventario/categoria_form.html'
    success_url = reverse_lazy('inventario:categoria_lista')


# --- Vistas de Maquinaria / Unidad Física ---
class MaquinariaListaView(LoginRequiredMixin, InventarioConsultaRequiredMixin, ListView):
    model = Unidad
    template_name = 'inventario/maquinaria_lista.html' 
    context_object_name = 'unidades'
    
    def get_queryset(self):
        # Traemos la unidad junto con los datos de su maquinaria base
        queryset = Unidad.objects.select_related('maquinaria__categoria').filter(
            activo=True,
            maquinaria__activo=True,
        )
        if self.request.user.es_cliente:
            queryset = queryset.filter(estado='Disponible')
        
        # Capturar parámetros de la URL (GET)
        q = self.request.GET.get('q', '').strip()
        categoria_id = self.request.GET.get('categoria', '')
        estado = self.request.GET.get('estado', '')

        # Filtrar por texto (código, nombre del equipo, número de serie o marca)
        if q:
            queryset = queryset.filter(
                Q(maquinaria__codigo__icontains=q) |
                Q(maquinaria__nombre__icontains=q) |
                Q(numero_serie__icontains=q) |
                Q(maquinaria__marca__icontains=q)
            )
        
        # Filtrar por categoría
        if categoria_id:
            queryset = queryset.filter(maquinaria__categoria_id=categoria_id)
            
        # Filtrar por estado
        if estado:
            queryset = queryset.filter(estado=estado)
            
        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # Pasamos las categorías y los estados disponibles al template para poblar los selectores
        context['categorias'] = Categoria.objects.all()
        context['estados'] = Unidad.ESTADOS
        # Mantener los valores actuales en el contexto para rellenar el formulario de filtros
        context['request_get'] = self.request.GET
        return context

class MaquinariaCrearView(
    LoginRequiredMixin,
    InventarioRegistroRequiredMixin,
    MaquinariaImagenesMixin,
    CreateView,
):
    form_class = MaquinariaIntegralForm
    template_name = 'inventario/maquinaria_form.html'
    success_url = reverse_lazy('inventario:maquinaria_lista')

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        # En la creación no pasamos ninguna instancia de unidad
        return kwargs

class MaquinariaEditarView(
    LoginRequiredMixin,
    InventarioRegistroRequiredMixin,
    MaquinariaImagenesMixin,
    UpdateView,
):
    model = Unidad
    form_class = MaquinariaIntegralForm
    template_name = 'inventario/maquinaria_form.html'
    success_url = reverse_lazy('inventario:maquinaria_lista')
    pk_url_kwarg = 'unidad_id' # Usaremos el ID de la unidad en la URL

    def get_object(self, queryset=None):
        return get_object_or_404(
            Unidad.objects.select_related('maquinaria').filter(
                activo=True,
                maquinaria__activo=True,
            ),
            pk=self.kwargs.get(self.pk_url_kwarg),
        )

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        # Le pasamos la unidad al form en lugar de 'instance' (como pide nuestro form personalizado)
        kwargs.pop('instance', None)
        kwargs['unidad'] = self.object
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['unidad'] = self.object
        return context

class MaquinariaDetalleView(DetailView):
    model = Unidad
    template_name = 'inventario/maquinaria_detalle.html'
    context_object_name = 'unidad'
    pk_url_kwarg = 'unidad_id' # Coincide con el <int:unidad_id> de la URL

    def get_object(self, queryset=None):
        # Optimizamos trayendo la unidad, su maquinaria y la categoría en una sola consulta
        unidades = Unidad.objects.select_related(
            'maquinaria__categoria',
        ).prefetch_related(
            'maquinaria__imagenes',
            'maquinaria__comentarios__cliente',
        ).filter(
            activo=True,
            maquinaria__activo=True,
        )
        usuario = self.request.user
        if not (
            usuario.is_authenticated
            and usuario.puede_consultar_maquinaria
            and not usuario.es_cliente
        ):
            unidades = unidades.filter(estado='Disponible')
        return get_object_or_404(unidades, pk=self.kwargs.get(self.pk_url_kwarg))

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        usuario = self.request.user
        context['comentario_form'] = kwargs.get(
            'comentario_form', MaquinariaComentarioForm()
        )
        context['puede_comentar'] = (
            usuario.is_authenticated and usuario.es_cliente
        )
        context['puede_solicitar_alquiler'] = (
            self.object.estado == 'Disponible'
            and (not usuario.is_authenticated or usuario.es_cliente)
        )
        return context

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()
        if not request.user.is_authenticated or not request.user.es_cliente:
            raise PermissionDenied(
                'Solo los clientes pueden comentar sobre la maquinaria.'
            )

        form = MaquinariaComentarioForm(request.POST)
        if form.is_valid():
            comentario = form.save(commit=False)
            comentario.maquinaria = self.object.maquinaria
            comentario.cliente = request.user
            comentario.save()
            messages.success(request, 'Tu comentario se publicó correctamente.')
            return redirect('inventario:maquinaria_detalle', unidad_id=self.object.pk)

        return self.render_to_response(
            self.get_context_data(comentario_form=form)
        )


class MaquinariaEliminarView(LoginRequiredMixin, InventarioRegistroRequiredMixin, View):
    http_method_names = ['post']

    @transaction.atomic
    def post(self, request, unidad_id):
        unidad = get_object_or_404(
            Unidad.objects.select_for_update().select_related('maquinaria'),
            pk=unidad_id,
            activo=True,
            maquinaria__activo=True,
        )
        maquinaria = unidad.maquinaria
        maquinaria.activo = False
        maquinaria.save(update_fields=['activo'])
        maquinaria.unidades.update(activo=False)

        messages.success(
            request,
            f'La maquinaria {maquinaria.codigo} se retiró del inventario. '
            'Sus registros se conservaron y podrá reactivarse con el mismo código.',
        )
        return redirect('inventario:maquinaria_lista')
