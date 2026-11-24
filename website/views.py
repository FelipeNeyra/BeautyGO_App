from datetime import datetime, timedelta
from functools import wraps
from math import isfinite

from django.shortcuts import redirect, render, get_object_or_404
from django.http import Http404
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Q, Sum
from django.db.models import Prefetch
from .forms import (
    EditarUsuarioForm,
    RegistroForm,
    RegistroClienteForm,
    RegistroPrestadorForm,
    ServicioForm,
)
from .models import (
    Administrador,
    Cliente,
    Liquidacion,
    Pago,
    Prestador,
    Reserva,
    Servicio,
    SuscripcionPrestador,
)

from django.contrib import messages

from django.contrib.auth.views import LoginView, PasswordChangeView
from django.contrib.messages.views import SuccessMessageMixin
from django.urls import reverse_lazy
from django.utils import timezone
from unicodedata import normalize as unicode_normalize


def _reservation_datetime(reservation_date, reservation_time):
    return timezone.make_aware(
        datetime.combine(reservation_date, reservation_time),
        timezone.get_current_timezone(),
    )

SERVICE_CATALOG = [
    {
        'category': 'Faciales', 'name': 'Facial hidratación profunda',
        'provider': 'Beauty Go Spa', 'duration': '60 min', 'price': '$32.000',
        'time': 'Hoy, 12:30', 'distance': '0,5 km', 'rating': '4.8 (24)',
        'badge': 'Más elegido',
        'image': 'https://images.unsplash.com/photo-1570172619644-dfd03ed5d881?w=700&q=80',
    },
    {
        'category': 'Peluquería', 'name': 'Corte y brushing',
        'provider': 'Marena Studio', 'duration': '90 min', 'price': '$28.000',
        'time': 'Hoy, 13:15', 'distance': '0,9 km', 'rating': '4.8 (16)',
        'badge': 'Disponible ahora',
        'image': 'https://images.unsplash.com/photo-1562322140-8baeececf3df?w=700&q=80',
    },
    {
        'category': 'Uñas', 'name': 'Manicure permanente',
        'provider': 'Casa Lila', 'duration': '60 min', 'price': '$18.000',
        'time': 'Hoy, 14:00', 'distance': '1,2 km', 'rating': '4.8 (12)',
        'badge': '20% dto.',
        'image': 'https://images.unsplash.com/photo-1610992015732-2449b76344bc?w=700&q=80',
    },
    {
        'category': 'Cejas', 'name': 'Lifting de pestañas',
        'provider': 'Blink Atelier', 'duration': '60 min', 'price': '$26.000',
        'time': 'Hoy, 15:30', 'distance': '1 km', 'rating': '4.9 (18)',
        'badge': 'Mejor evaluado',
        'image': 'https://images.unsplash.com/photo-1583001931096-959e9a1a6223?w=700&q=80',
    },
]

CATEGORIES = [
    ('todo', '✦ Todo'), ('peluqueria', '◒ Peluquería'), ('unas', '◌ Uñas'),
    ('faciales', '◉ Faciales'), ('cejas', '◍ Cejas'), ('pestanas', '◉ Pestañas'),
]

MONTHLY_SUBSCRIPTION_PRICE = 5000
LIQUIDATION_COMMISSION_PERCENTAGE = 15.0

# --- VISTA DE LOGIN ---
class BeautyGoLoginView(LoginView):
    def get_success_url(self):
        user = self.request.user
        if user.is_superuser or Administrador.objects.filter(usuario_id=user.pk).exists():
            return self.get_redirect_url() or reverse_lazy('vista_administrador')
        return super().get_success_url()

# --- VERIFICACIÓN DE USUARIO ADMIN ---
def admin_required(view_func):
    @login_required
    @wraps(view_func)
    def wrapped_view(request, *args, **kwargs):
        if not (
            request.user.is_superuser
            or Administrador.objects.filter(usuario_id=request.user.pk).exists()
        ):
            raise PermissionDenied
        return view_func(request, *args, **kwargs)

    return wrapped_view


def _format_clp(amount):
    return f'${amount:,.0f}'.replace(',', '.')


def _create_liquidation_for_completed_reservation(reservation, administrator):
    services = list(reservation.servicios.select_related(
        'prestador_idprestador',
    ))
    if not services:
        raise ValueError('La reserva no tiene servicios asociados.')

    for service in services:
        existing_liquidation = Liquidacion.objects.filter(
            servicios=service,
            servicios__reservas=reservation,
        ).distinct().first()
        if existing_liquidation:
            continue

        gross_amount = service.precio_base
        commission_amount = round(
            gross_amount * LIQUIDATION_COMMISSION_PERCENTAGE / 100
        )
        liquidation = Liquidacion.objects.create(
            idliquidacion=(Liquidacion.objects.order_by('-idliquidacion')
                           .values_list('idliquidacion', flat=True).first() or 0) + 1,
            monto_bruto_total=gross_amount,
            porcentaje_comision=LIQUIDATION_COMMISSION_PERCENTAGE,
            monto_comision_spa=commission_amount,
            monto_neto_prestador=gross_amount - commission_amount,
            administrador_idadministrador=administrator,
        )
        liquidation.servicios.add(service)


def _service_image(category, index=0):
    category_keys = _catalog_category_keys(category)
    if category_keys:
        for item in SERVICE_CATALOG:
            if category_keys[0] in _catalog_category_keys(item['category']):
                return item['image']
    return SERVICE_CATALOG[index % len(SERVICE_CATALOG)]['image']


def _filtered_services(request):
    query = request.GET.get('q', '').strip().lower()
    category = request.GET.get('categoria', '').strip().lower()
    ordering = request.GET.get('orden', 'nombre').strip().lower()
    provider_id = request.GET.get('prestador', '').strip()
    price_min = _query_range_value(request.GET.get('precio_min'), 1000, 1000, 100000)
    price_max = _query_range_value(request.GET.get('precio_max'), 100000, 1000, 100000)
    rating_min = _query_range_value(request.GET.get('calificacion_min'), 1, 1, 5)
    rating_max = _query_range_value(request.GET.get('calificacion_max'), 5, 1, 5)
    if price_min > price_max:
        price_min, price_max = price_max, price_min
    if rating_min > rating_max:
        rating_min, rating_max = rating_max, rating_min
    database_services = Servicio.objects.select_related(
        'prestador_idprestador__usuario'
    ).filter(
        prestador_idprestador__estado_aprobacion=True,
        prestador_idprestador__usuario__isnull=False,
    )
    if provider_id.isdigit():
        database_services = database_services.filter(
            prestador_idprestador_id=int(provider_id),
        )
    services = [
        {
            'id': service.idservicio,
            'provider_id': service.prestador_idprestador_id,
            'category': service.categoria or service.prestador_idprestador.especialidad.split(' y ')[0],
            'category_keys': _service_category_keys(service),
            'name': service.nombre,
            'description': service.descripcion,
            'provider': service.prestador_idprestador.usuario.get_full_name()
            or service.prestador_idprestador.usuario.username,
            'duration': f'{service.duracion} min',
            'duration_minutes': service.duracion,
            'price': f'${service.precio_base:,.0f}'.replace(',', '.'),
            'price_value': service.precio_base,
            'time': 'Disponible hoy',
            'distance': service.prestador_idprestador.radio_cobertura,
            'rating': '5.0',
            'rating_value': 5.0,
            'badge': 'Disponible ahora',
            'image': _service_image(
                service.categoria or service.prestador_idprestador.especialidad,
                index,
            ),
        }
        for index, service in enumerate(database_services)
    ]
    if category and category != 'todo':
        services = [item for item in services if category in item['category_keys']]
    if query:
        services = [
            item for item in services
            if query in ' '.join((
                item['category'],
                item['name'],
                item['description'],
                item['provider'],
            )).lower()
        ]
    services = [
        item for item in services
        if price_min <= item['price_value'] <= price_max
        and rating_min <= item['rating_value'] <= rating_max
    ]
    ordering_key = {
        'precio': lambda item: int(
            item['price'].replace('$', '').replace('.', '')
        ),
        'duracion': lambda item: int(item['duration'].split()[0]),
        'nombre': lambda item: item['name'].lower(),
    }.get(ordering, lambda item: item['name'].lower())
    services.sort(key=ordering_key)
    return services


def _query_range_value(value, default, minimum, maximum):
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    if not isfinite(parsed):
        return default
    if parsed.is_integer():
        parsed = int(parsed)
    return max(minimum, min(parsed, maximum))


def _paginated_services(services, request, per_page=8):
    paginator = Paginator(services, per_page)
    page_obj = paginator.get_page(request.GET.get('page'))
    query_params = request.GET.copy()
    query_params.pop('page', None)
    return page_obj, query_params.urlencode()


def _service_category_keys(service):
    value = unicode_normalize(
        'NFKD',
        f'{service.categoria}'
        f'{service.nombre} {service.descripcion}',
    ).encode('ascii', 'ignore').decode().lower()
    terms = {
        'peluqueria': ('peluquer', 'corte', 'brushing'),
        'unas': ('una', 'manicure', 'pedicure'),
        'faciales': ('facial', 'limpieza', 'masaje facial'),
        'cejas': ('ceja',),
        'pestanas': ('pestana', 'lifting'),
    }
    return [
        category for category, keywords in terms.items()
        if any(keyword in value for keyword in keywords)
    ]


def _catalog_category_keys(category):
    value = unicode_normalize('NFKD', category).encode('ascii', 'ignore').decode().lower()
    return {
        'peluqueria': ['peluqueria'],
        'unas': ['unas'],
        'faciales': ['faciales'],
        'cejas': ['cejas'],
        'pestanas': ['pestanas'],
    }.get(value, [])


# Vista principal
def home(request):
    client_profile = getattr(request.user, 'perfil_cliente', None)
    prestador_profile = getattr(request.user, 'perfil_prestador', None)
    user_prestador_id = (
        prestador_profile.idprestador if prestador_profile is not None else None
    )

    confirmed_booking = None
    if request.GET.get('reserva') == 'confirmada' and client_profile:
        confirmed_booking = Reserva.objects.filter(
            idreserva=request.GET.get('id'),
            cliente_idcliente=client_profile,
        ).prefetch_related('servicios').first()
    confirmed_payment = (
        Pago.objects.filter(reserva_idreserva=confirmed_booking).first()
        if confirmed_booking else None
    )
    services_page, service_querystring = _paginated_services(
        _filtered_services(request),
        request,
    )
    service_price_min = _query_range_value(
        request.GET.get('precio_min'), 1000, 1000, 100000,
    )
    service_price_max = _query_range_value(
        request.GET.get('precio_max'), 100000, 1000, 100000,
    )
    service_rating_min = _query_range_value(
        request.GET.get('calificacion_min'), 1, 1, 5,
    )
    service_rating_max = _query_range_value(
        request.GET.get('calificacion_max'), 5, 1, 5,
    )
    if service_price_min > service_price_max:
        service_price_min, service_price_max = service_price_max, service_price_min
    if service_rating_min > service_rating_max:
        service_rating_min, service_rating_max = service_rating_max, service_rating_min
    booking_dates = [
        timezone.localdate() + timedelta(days=offset)
        for offset in range(1, 8)
    ]
    occupied_intervals = {}
    reservations = Reserva.objects.filter(
        fecha__in=booking_dates,
        estado__in=['Pendiente', 'Confirmada', 'Completada'],
    ).prefetch_related('servicios')
    for reservation in reservations:
        date_key = reservation.fecha.isoformat()
        local_start = timezone.localtime(
            reservation.hora_bloque,
            timezone.get_current_timezone(),
        )
        start_minute = local_start.hour * 60 + local_start.minute
        services_by_provider = {}
        for reservation_service in reservation.servicios.all():
            provider_key = str(reservation_service.prestador_idprestador_id)
            services_by_provider.setdefault(provider_key, 0)
            services_by_provider[provider_key] += reservation_service.duracion
        for provider_key, duration in services_by_provider.items():
            interval_key = f'{provider_key}|{date_key}'
            occupied_intervals.setdefault(interval_key, []).append({
                'start': start_minute,
                'end': start_minute + duration,
            })
    return render(request, 'website/home.html', {
        'prestador_user': user_prestador_id,
        'services_page': services_page,
        'services_page_range': services_page.paginator.get_elided_page_range(
            services_page.number,
        ),
        'services': services_page.object_list,
        'service_querystring': service_querystring,
        'categories': CATEGORIES,
        'service_query': request.GET.get('q', '').strip(),
        'service_category': request.GET.get('categoria', 'todo').strip().lower(),
        'service_order': request.GET.get('orden', 'nombre').strip().lower(),
        'service_provider': request.GET.get('prestador', '').strip(),
        'service_price_min': service_price_min,
        'service_price_max': service_price_max,
        'service_rating_min': service_rating_min,
        'service_rating_max': service_rating_max,
        'service_providers': Prestador.objects.filter(
            estado_aprobacion=True,
            usuario__isnull=False,
            servicios__isnull=False,
        ).select_related('usuario').distinct().order_by(
            'usuario__first_name', 'usuario__last_name', 'pk',
        ),
        'booking_dates': booking_dates,
        'booking_occupied_intervals': occupied_intervals,
        'booking_client': client_profile,
        'confirmed_booking': confirmed_booking,
        'confirmed_payment': confirmed_payment,
    })

def detalle_servicio(request, pk):
    service = get_object_or_404(
        Servicio.objects.select_related(
            'prestador_idprestador__usuario',
        ),
        pk=pk,
        prestador_idprestador__estado_aprobacion=True,
    )
    provider = service.prestador_idprestador
    return render(request, 'website/detalle_servicio.html', {
        'service': service,
        'provider': provider,
        'service_image': _service_image(service.categoria),
    })


@login_required
def reservas(request):
    if request.method == 'POST':
        cliente = getattr(request.user, 'perfil_cliente', None)
        service_id = request.POST.get('service_id')
        selected_date = request.POST.get('date')
        selected_time = request.POST.get('time')
        contact_name = request.POST.get('contact_name', '').strip()
        contact_email = request.POST.get('contact_email', '').strip()
        contact_phone = request.POST.get('contact_phone', '').strip()
        address = request.POST.get('address', '').strip()
        payment_status = request.POST.get('payment_status')
        is_administrator = (
            request.user.is_superuser
            or Administrador.objects.filter(usuario_id=request.user.pk).exists()
        )
        if not all((service_id, selected_date, selected_time, contact_name,
                    contact_email, contact_phone, address)):
            messages.error(request, 'Completa todos los datos de la reserva.')
            return redirect('home')
        if cliente is None and not is_administrator:
            messages.error(
                request,
                'Debes tener un perfil de cliente para agendar un servicio.',
            )
            return redirect('home')
        if '@' not in contact_email or len(contact_phone) < 8:
            messages.error(request, 'Revisa tu correo y teléfono antes de continuar.')
            return redirect('home')
        if payment_status != 'success':
            messages.error(request, 'El pago no fue aprobado. La reserva no fue creada.')
            return redirect('home')
        service = get_object_or_404(
            Servicio,
            pk=service_id,
            prestador_idprestador__estado_aprobacion=True,
        )
        try:
            reservation_date = datetime.strptime(selected_date, '%Y-%m-%d').date()
            reservation_time = datetime.strptime(selected_time, '%H:%M').time()
        except ValueError:
            messages.error(request, 'La fecha u hora seleccionada no es válida.')
            return redirect('home')
        with transaction.atomic():
            if cliente is None:
                account_email = request.user.email or contact_email
                if Cliente.objects.filter(correo__iexact=account_email).exists():
                    messages.error(
                        request,
                        'El correo de esta cuenta ya está asociado a otro perfil '
                        'de cliente. Contacta al equipo para revisar la cuenta.',
                    )
                    return redirect('home')
                cliente = Cliente.objects.create(
                    nombre=contact_name[:45],
                    correo=account_email,
                    direccion_domicilio=address[:45],
                    telefono=contact_phone[:12],
                    usuario=request.user,
                )
            reservation_datetime = _reservation_datetime(
                reservation_date,
                reservation_time,
            )
            provider = Prestador.objects.select_for_update().get(
                pk=service.prestador_idprestador_id,
            )
            candidate_end = reservation_datetime + timedelta(
                minutes=service.duracion,
            )
            existing_reservations = Reserva.objects.filter(
                fecha=reservation_date,
                estado__in=['Pendiente', 'Confirmada', 'Completada'],
                servicios__prestador_idprestador=provider,
            ).distinct().prefetch_related('servicios')
            occupied = False
            for existing in existing_reservations:
                existing_services = [
                    existing_service
                    for existing_service in existing.servicios.all()
                    if existing_service.prestador_idprestador_id == provider.pk
                ]
                existing_duration = sum(
                    existing_service.duracion
                    for existing_service in existing_services
                )
                existing_start = timezone.localtime(
                    existing.hora_bloque,
                    timezone.get_current_timezone(),
                )
                existing_end = existing_start + timedelta(
                    minutes=existing_duration,
                )
                if (
                    reservation_datetime < existing_end
                    and existing_start < candidate_end
                ):
                    occupied = True
                    break
            if occupied:
                messages.error(
                    request,
                    'Ese horario se solapa con otra reserva. '
                    'Selecciona otro horario.',
                )
                return redirect('home')
            reservation = Reserva.objects.create(
                idreserva=(Reserva.objects.order_by('-idreserva').values_list(
                    'idreserva', flat=True
                ).first() or 0) + 1,
                fecha=reservation_date,
                hora_bloque=reservation_datetime,
                direccion_visita=address[:45],
                estado='Pendiente',
                cliente_idcliente=cliente,
            )
            reservation.servicios.add(service)
            Pago.objects.create(
                idpago=(Pago.objects.order_by('-idpago').values_list(
                    'idpago', flat=True
                ).first() or 0) + 1,
                monto_total=round(service.precio_base * 0.3),
                metodo_pago='Simulación Webpay aprobada',
                reserva_idreserva=reservation,
            )
        return redirect(f'/?reserva=confirmada&id={reservation.idreserva}')

    cliente = getattr(request.user, 'perfil_cliente', None)
    user_reservas = Reserva.objects.filter(
        cliente_idcliente=cliente
    ).prefetch_related(
        Prefetch(
            'servicios',
            queryset=Servicio.objects.select_related(
                'prestador_idprestador__usuario',
            ),
            to_attr='servicios_cargados',
        ),
        Prefetch(
            'pago_set',
            queryset=Pago.objects.order_by('idpago'),
            to_attr='pagos_cargados',
        ),
    ).order_by('-fecha', '-hora_bloque') if cliente else Reserva.objects.none()
    reservation_cards = []
    for index, reserva in enumerate(user_reservas):
        services = reserva.servicios_cargados
        service = services[0] if services else None
        payments = reserva.pagos_cargados
        payment = payments[0] if payments else None
        if service:
            provider = service.prestador_idprestador
            reservation_cards.append({
                'reservation': reserva,
                'service': service,
                'provider': provider.usuario.get_full_name() or provider.usuario.username,
                'specialty': provider.especialidad,
                'payment': payment,
                'image': SERVICE_CATALOG[index % len(SERVICE_CATALOG)]['image'],
            })
    return render(request, 'website/reservas.html', {
        'reservations': reservation_cards,
        'booking_client': cliente,
    })


@login_required
def favoritos(request):
    return render(request, 'website/favoritos.html', {
        'services': _filtered_services(request),
    })

# --------- REGISTRO -------
#Vista de Formulario de Registro (Usuario_Cliente)
def vista_registro(request):
    user_form = RegistroForm(request.POST or None)
    cliente_form = RegistroClienteForm(request.POST or None)

    if request.method == 'POST':
        if user_form.is_valid() and cliente_form.is_valid():
            with transaction.atomic():
                user = user_form.save()
                cliente = cliente_form.save(commit=False)
                cliente.usuario = user
                cliente.correo = user.email
                cliente.save()
            login(request, user)
            return redirect('home')

    return render(
        request,
        'website/usuario_formulario.html',
        {
            'user_form': user_form,
            'cliente_form': cliente_form,
            'es_registro': True
        },
    )

@login_required
def vista_editar_informacion_usuario(request):
    user = request.user
    cliente = getattr(user, 'perfil_cliente', None)

    if cliente is None:
        messages.error(request, 'No existe un perfil de cliente asociado.')
        return redirect('home')

    user_form = EditarUsuarioForm(
        request.POST or None,
        instance=user,
    )
    cliente_form = RegistroClienteForm(
        request.POST or None,
        instance=cliente,
    )

    if request.method == 'POST':
        if user_form.is_valid() and cliente_form.is_valid():
            with transaction.atomic():
                user = user_form.save()
                cliente = cliente_form.save(commit=False)
                cliente.usuario = user
                cliente.correo = user.email
                cliente.save()
            messages.success(request, f'Datos actualizados correctamente')
            return redirect('home')

    return render(
        request,
        'website/usuario_formulario.html',
        {
            'user_form': user_form,
            'cliente_form': cliente_form,
            'es_registro': False
        },
    )

class CambiarPasswordView(SuccessMessageMixin, PasswordChangeView):
    template_name = 'cambiar_contraseña.html'
    success_url = reverse_lazy('cambiar_contraseña/hecho')
    success_message = 'Tu contraseña fue actualizada.'


# --------- SECCIÓN DE PRESTADORES -------
#Vista de Solicitud para Prestadores
@login_required
def vista_solicitud_prestadores(request):
    if not hasattr(request.user, 'perfil_cliente'):
        messages.error(
            request,
            'Para postular como prestador primero debes completar tu registro '
            'como cliente.',
        )
        return redirect('datos_usuario')

    if hasattr(request.user, 'perfil_prestador'):
        prestador = request.user.perfil_prestador

        if prestador.estado_aprobacion is None:
            messages.info(
                request,
                'Ya tienes una solicitud enviada y en estado de evaluación.',
            )
            return redirect('home')
        if prestador.estado_aprobacion:
            return redirect('vista_prestador')
        messages.info(
            request,
            'Tu solicitud fue rechazada. Contacta al equipo para obtener ayuda.',
        )
        return redirect('home')
    
    prestador_form = RegistroPrestadorForm(request.POST or None)

    if request.method == 'POST':
        if prestador_form.is_valid():
            current_user = request.user

            prestador = prestador_form.save(commit=False)
            prestador.usuario = current_user
            prestador.save()
            messages.success(
                request,
                'Tu solicitud fue enviada y está pendiente de revisión.',
            )
            return redirect('home')

    return render(
        request,
        'website/solicitud_prestador.html',
        {
            'prestador_form': prestador_form
        },
    )

#Vista de Prestadores (Tras Iniciar Sesión)
@login_required
def vista_prestador(request):
    prestador = getattr(request.user, 'perfil_prestador', None)
    if prestador is None:
        raise PermissionDenied

    section = request.GET.get('section', 'servicios')
    if section not in {'servicios', 'reservas', 'suscripcion'}:
        section = 'servicios'

    service_form = ServicioForm()
    editing_service = None
    deleting_service = None
    requested_service_id = request.GET.get('editar')
    requested_delete_service_id = request.GET.get('eliminar')
    if requested_service_id and section == 'servicios':
        if not requested_service_id.isdigit():
            raise Http404
        editing_service = get_object_or_404(
            Servicio,
            pk=int(requested_service_id),
            prestador_idprestador=prestador,
        )
        service_form = ServicioForm(instance=editing_service)

    if requested_delete_service_id and section == 'servicios':
        if not requested_delete_service_id.isdigit():
            raise Http404
        deleting_service = get_object_or_404(
            Servicio,
            pk=int(requested_delete_service_id),
            prestador_idprestador=prestador,
        )

    if request.method == 'POST':
        if prestador.estado_aprobacion is not True:
            messages.error(
                request,
                'Solo los perfiles aprobados pueden administrar servicios, '
                'reservas y suscripciones.',
            )
            return redirect('vista_prestador')

        action = request.POST.get('action')
        if action == 'pagar_suscripcion':
            current_period = timezone.localdate().replace(day=1)
            subscription, _ = SuscripcionPrestador.objects.get_or_create(
                prestador=prestador,
                periodo=current_period,
                defaults={'monto': MONTHLY_SUBSCRIPTION_PRICE},
            )
            if subscription.estado == SuscripcionPrestador.PAGADA:
                messages.info(request, 'La suscripción de este mes ya está pagada.')
            else:
                subscription.estado = SuscripcionPrestador.PAGADA
                subscription.monto = MONTHLY_SUBSCRIPTION_PRICE
                subscription.fecha_pago = timezone.now()
                subscription.registrado_por = request.user
                subscription.save(update_fields=[
                    'estado',
                    'monto',
                    'fecha_pago',
                    'registrado_por',
                ])
                messages.success(
                    request,
                    'Pago simulado correctamente. Tu suscripción está al día.',
                )
            return redirect(f"{reverse_lazy('vista_prestador')}?section=suscripcion")
        elif action == 'guardar_servicio':
            service_id = request.POST.get('service_id')
            if service_id and not service_id.isdigit():
                messages.error(request, 'El servicio seleccionado no es válido.')
                return redirect('vista_prestador')
            editing_service = (
                get_object_or_404(
                    Servicio,
                    pk=int(service_id),
                    prestador_idprestador=prestador,
                )
                if service_id else None
            )
            service_form = ServicioForm(
                request.POST,
                instance=editing_service,
            )
            if service_form.is_valid():
                with transaction.atomic():
                    service = service_form.save(commit=False)
                    if editing_service is None:
                        service.idservicio = (
                            Servicio.objects.order_by('-idservicio')
                            .values_list('idservicio', flat=True)
                            .first() or 0
                        ) + 1
                    service.prestador_idprestador = prestador
                    service.save()
                messages.success(request, 'El servicio fue guardado correctamente.')
                return redirect('vista_prestador')
            section = 'servicios'
        elif action == 'eliminar_servicio':
            service_id = request.POST.get('service_id', '')
            if not service_id.isdigit():
                messages.error(request, 'El servicio seleccionado no es válido.')
                return redirect('vista_prestador')
            service = get_object_or_404(
                Servicio,
                pk=int(service_id),
                prestador_idprestador=prestador,
            )
            service.delete()
            messages.success(request, 'El servicio fue eliminado correctamente.')
            return redirect('vista_prestador')
        elif action == 'actualizar_reserva':
            status = request.POST.get('estado')
            reservation_id = request.POST.get('reserva_id', '')
            if not reservation_id.isdigit():
                messages.error(request, 'La reserva seleccionada no es válida.')
                return redirect(f"{reverse_lazy('vista_prestador')}?section=reservas")
            if status not in {'Confirmada', 'Rechazada', 'Completada'}:
                messages.error(request, 'El estado de la reserva no es válido.')
            else:
                reservation = get_object_or_404(
                    Reserva.objects.filter(
                        servicios__prestador_idprestador=prestador,
                    ).distinct(),
                    pk=int(reservation_id),
                )
                if status == 'Completada':
                    if timezone.now() <= reservation.hora_bloque:
                        messages.error(
                            request,
                            'No puedes marcar esta reserva como completada antes '
                            'de que llegue la fecha y hora programadas.',
                        )
                        return redirect(
                            f"{reverse_lazy('vista_prestador')}?section=reservas"
                        )
                    with transaction.atomic():
                        reservation_services = list(
                            reservation.servicios.select_related(
                                'prestador_idprestador',
                            )
                        )
                        if not reservation_services:
                            messages.error(
                                request,
                                'La reserva no tiene servicios asociados.',
                            )
                            return redirect(
                                f"{reverse_lazy('vista_prestador')}?section=reservas"
                            )

                        total_amount = sum(
                            service.precio_base
                            for service in reservation_services
                        )
                        payment = Pago.objects.filter(
                            reserva_idreserva=reservation,
                        ).first()
                        if payment is None:
                            Pago.objects.create(
                                idpago=(Pago.objects.order_by('-idpago')
                                        .values_list('idpago', flat=True).first() or 0) + 1,
                                monto_total=total_amount,
                                metodo_pago='Pago total del servicio',
                                reserva_idreserva=reservation,
                            )
                        else:
                            payment.monto_total = total_amount
                            payment.save(update_fields=['monto_total'])

                        administrator = Administrador.objects.select_related(
                            'usuario',
                        ).order_by('pk').first()
                        if administrator is None:
                            messages.error(
                                request,
                                'No se pudo generar la liquidación: no existe '
                                'un administrador registrado.',
                            )
                            return redirect(
                                f"{reverse_lazy('vista_prestador')}?section=reservas"
                            )

                        reservation.estado = status
                        reservation.save(update_fields=['estado'])
                        _create_liquidation_for_completed_reservation(
                            reservation,
                            administrator,
                        )
                    messages.success(
                        request,
                        'La reserva fue completada, el pago total fue actualizado '
                        'y se generaron sus liquidaciones.',
                    )
                else:
                    reservation.estado = status
                    reservation.save(update_fields=['estado'])
                    messages.success(request, 'El estado de la reserva fue actualizado.')
            return redirect(f"{reverse_lazy('vista_prestador')}?section=reservas")
        else:
            messages.error(request, 'La acción solicitada no es válida.')
            return redirect('vista_prestador')

    provider_services = list(
        Servicio.objects.select_related(
            'prestador_idprestador__usuario',
        ).filter(prestador_idprestador=prestador)
        .order_by('nombre')
    )
    provider_query = request.GET.get('q', '').strip().lower()
    provider_category = request.GET.get('categoria', '').strip().lower()
    provider_order = request.GET.get('orden', 'nombre').strip().lower()
    if provider_query:
        provider_services = [
            service for service in provider_services
            if provider_query in ' '.join((
                service.nombre,
                service.descripcion,
                service.categoria,
                prestador.especialidad,
            )).lower()
        ]
    if provider_category and provider_category != 'todo':
        provider_services = [
            service for service in provider_services
            if provider_category in _service_category_keys(service)
        ]
    if provider_order == 'precio':
        provider_services.sort(key=lambda service: service.precio_base)
    elif provider_order == 'duracion':
        provider_services.sort(key=lambda service: service.duracion)
    else:
        provider_services.sort(key=lambda service: service.nombre.lower())
    provider_services_page, provider_querystring = _paginated_services(
        provider_services,
        request,
    )
    services = [
        {
            'service': service,
            'image': _service_image(service.categoria, index),
            'price_display': _format_clp(service.precio_base),
        }
        for index, service in enumerate(provider_services_page.object_list)
    ]
    reservation_list = list(
        Reserva.objects.filter(
            servicios__prestador_idprestador=prestador,
        ).distinct().select_related('cliente_idcliente').prefetch_related(
            Prefetch(
                'servicios',
                queryset=Servicio.objects.select_related(
                    'prestador_idprestador__usuario',
                ),
                to_attr='servicios_cargados',
            ),
        )
        .order_by('-fecha', '-hora_bloque')
    )
    for reservation in reservation_list:
        reservation.provider_services = [
            service for service in reservation.servicios_cargados
            if service.prestador_idprestador_id == prestador.pk
        ]
    current_period = timezone.localdate().replace(day=1)
    subscription = SuscripcionPrestador.objects.filter(
        prestador=prestador,
        periodo=current_period,
    ).first()
    subscription_history = []
    for history_item in SuscripcionPrestador.objects.filter(
        prestador=prestador,
    ).exclude(periodo=current_period):
        subscription_history.append({
            'subscription': history_item,
            'amount_display': _format_clp(history_item.monto),
            'is_overdue': (
                history_item.periodo < current_period
                and history_item.estado == SuscripcionPrestador.PENDIENTE
            ),
        })

    return render(request, 'website/vista_prestador.html', {
        'prestador': prestador,
        'section': section,
        'service_form': service_form,
        'editing_service': editing_service,
        'deleting_service': deleting_service,
        'services': services,
        'service_page': provider_services_page,
        'provider_page_range': provider_services_page.paginator.get_elided_page_range(
            provider_services_page.number,
        ),
        'service_querystring': provider_querystring,
        'service_query': request.GET.get('q', '').strip(),
        'service_category': provider_category or 'todo',
        'service_order': provider_order,
        'categories': CATEGORIES,
        'service_count': len(provider_services),
        'reservations': reservation_list,
        'reservation_count': len(reservation_list),
        'current_period': current_period,
        'subscription': subscription,
        'subscription_history': subscription_history,
        'monthly_subscription_price': _format_clp(MONTHLY_SUBSCRIPTION_PRICE),
    })


# --------- SECCIÓN DE ADMINISTRADORES -------
@admin_required
def vista_administrador(request):
    providers = Prestador.objects.select_related('usuario').filter(
        usuario__isnull=False,
    )
    pending_requests = providers.filter(
        estado_aprobacion__isnull=True,
    ).order_by('usuario__date_joined', 'pk')
    approved_providers = providers.filter(
        estado_aprobacion=True,
    ).order_by('usuario__first_name', 'usuario__last_name', 'pk')
    rejected_requests = providers.filter(
        estado_aprobacion=False,
    ).order_by('usuario__first_name', 'usuario__last_name', 'pk')

    section = request.GET.get('section', 'solicitudes')
    if section not in {'solicitudes', 'suscripciones', 'liquidaciones'}:
        section = 'solicitudes'
    request_status = request.GET.get('estado_solicitud', 'pendientes')
    if request_status not in {'pendientes', 'aprobadas', 'rechazadas'}:
        request_status = 'pendientes'
    request_status_lists = {
        'pendientes': pending_requests,
        'aprobadas': approved_providers,
        'rechazadas': rejected_requests,
    }
    filtered_requests = request_status_lists[request_status]

    request_page, request_querystring = _paginated_services(
        filtered_requests.prefetch_related(
            Prefetch(
                'servicios',
                queryset=Servicio.objects.order_by('nombre'),
            ),
        ),
        request,
        per_page=6,
    )
    provider_list = list(request_page.object_list)
    selected_provider = None
    requested_provider_id = request.GET.get('prestador')
    if requested_provider_id:
        selected_provider = next(
            (provider for provider in provider_list
             if str(provider.pk) == requested_provider_id),
            None,
        )
    if selected_provider is None and provider_list:
        selected_provider = provider_list[0]
    decided_request_count = (
        approved_providers.count() + rejected_requests.count()
    )
    approved_request_percentage = (
        round(approved_providers.count() * 100 / decided_request_count, 1)
        if decided_request_count else 0
    )
    rejected_request_percentage = (
        round(rejected_requests.count() * 100 / decided_request_count, 1)
        if decided_request_count else 0
    )

    current_period = timezone.localdate().replace(day=1)
    requested_subscription_month = request.GET.get('mes_suscripcion', '')
    try:
        selected_subscription_month = datetime.strptime(
            requested_subscription_month,
            '%Y-%m',
        ).date().replace(day=1)
    except ValueError:
        selected_subscription_month = current_period
    all_subscriptions = SuscripcionPrestador.objects.all()
    paid_subscriptions = all_subscriptions.filter(
        estado=SuscripcionPrestador.PAGADA,
    )
    paid_subscription_total = paid_subscriptions.aggregate(
        total=Sum('monto'),
    )['total'] or 0
    available_subscription_months = list(
        all_subscriptions.order_by().values_list('periodo', flat=True).distinct()
    )
    if current_period not in available_subscription_months:
        available_subscription_months.insert(0, current_period)
    monthly_subscription_total = paid_subscriptions.filter(
        periodo=selected_subscription_month,
    ).aggregate(total=Sum('monto'))['total'] or 0
    subscriptions = {
        subscription.prestador_id: subscription
        for subscription in all_subscriptions.filter(
            periodo=selected_subscription_month,
            prestador__estado_aprobacion=True,
        )
    }
    subscription_rows = []
    for provider in approved_providers:
        subscription = subscriptions.get(provider.pk)
        subscription_rows.append({
            'prestador': provider,
            'subscription': subscription,
            'amount_display': _format_clp(
                subscription.monto if subscription else MONTHLY_SUBSCRIPTION_PRICE
            ),
        })
    pending_subscriptions = sum(
        row['subscription'] is None
        or row['subscription'].estado == SuscripcionPrestador.PENDIENTE
        for row in subscription_rows
    )
    subscription_payment_filter = request.GET.get(
        'estado_pago_suscripcion',
        'todas',
    )
    if subscription_payment_filter not in {'todas', 'pendientes', 'pagadas'}:
        subscription_payment_filter = 'todas'
    if subscription_payment_filter == 'pendientes':
        subscription_rows = [
            row for row in subscription_rows
            if row['subscription'] is None
            or row['subscription'].estado == SuscripcionPrestador.PENDIENTE
        ]
    elif subscription_payment_filter == 'pagadas':
        subscription_rows = [
            row for row in subscription_rows
            if row['subscription']
            and row['subscription'].estado == SuscripcionPrestador.PAGADA
        ]
    liquidation_query = request.GET.get('q', '').strip()
    liquidation_provider = request.GET.get('prestador', '').strip()
    liquidation_queryset = Liquidacion.objects.filter(
        servicios__reservas__estado='Completada',
    )
    if liquidation_provider.isdigit():
        liquidation_queryset = liquidation_queryset.filter(
            servicios__prestador_idprestador_id=int(liquidation_provider),
        )
    if liquidation_query:
        search_filter = (
            Q(servicios__nombre__icontains=liquidation_query)
            | Q(servicios__prestador_idprestador__usuario__first_name__icontains=liquidation_query)
            | Q(servicios__prestador_idprestador__usuario__last_name__icontains=liquidation_query)
            | Q(servicios__prestador_idprestador__usuario__username__icontains=liquidation_query)
        )
        if liquidation_query.isdigit():
            search_filter |= Q(idliquidacion=int(liquidation_query))
        liquidation_queryset = liquidation_queryset.filter(search_filter)
    filtered_liquidation_services = (
        _filtered_services(request)
        if section == 'liquidaciones' else []
    )
    filtered_liquidation_provider_ids = {
        item['provider_id'] for item in filtered_liquidation_services
    }
    liquidation_providers = Prestador.objects.filter(
        estado_aprobacion=True,
        usuario__isnull=False,
        servicios__liquidaciones__servicios__reservas__estado='Completada',
        pk__in=filtered_liquidation_provider_ids,
    ).select_related('usuario').distinct().order_by(
        'usuario__first_name', 'usuario__last_name', 'pk',
    )
    completed_liquidation_queryset = liquidation_queryset.select_related(
        'administrador_idadministrador__usuario',
    ).prefetch_related(
        'servicios__prestador_idprestador__usuario',
    ).order_by('-idliquidacion').distinct()
    liquidation_count = completed_liquidation_queryset.count()
    completed_liquidation_page, liquidation_querystring = _paginated_services(
        list(completed_liquidation_queryset),
        request,
        per_page=10,
    )
    liquidations = (
        list(completed_liquidation_page.object_list)
        if section == 'liquidaciones' else []
    )
    liquidation_rows = [
        {
            'liquidation': liquidation,
            'gross_display': _format_clp(liquidation.monto_bruto_total),
            'commission_display': _format_clp(liquidation.monto_comision_spa),
            'net_display': _format_clp(liquidation.monto_neto_prestador),
        }
        for liquidation in liquidations
    ]

    return render(request, 'website/vista_admin.html', {
        'section': section,
        'pending_requests': pending_requests,
        'approved_providers': approved_providers,
        'rejected_requests': rejected_requests,
        'selected_provider': selected_provider,
        'request_status': request_status,
        'filtered_requests': provider_list,
        'request_page': request_page,
        'request_querystring': request_querystring,
        'approved_request_percentage': approved_request_percentage,
        'rejected_request_percentage': rejected_request_percentage,
        'decided_request_count': decided_request_count,
        'pending_request_count': pending_requests.count(),
        'approved_provider_count': approved_providers.count(),
        'rejected_request_count': rejected_requests.count(),
        'subscription_rows': subscription_rows,
        'pending_subscription_count': pending_subscriptions,
        'paid_subscription_total': _format_clp(paid_subscription_total),
        'monthly_subscription_total': _format_clp(monthly_subscription_total),
        'subscription_months': available_subscription_months,
        'selected_subscription_month': selected_subscription_month,
        'subscription_payment_filter': subscription_payment_filter,
        'current_period': current_period,
        'monthly_subscription_price': _format_clp(MONTHLY_SUBSCRIPTION_PRICE),
        'liquidation_count': liquidation_count,
        'liquidation_rows': liquidation_rows,
        'liquidation_query': liquidation_query,
        'liquidation_provider': liquidation_provider,
        'liquidation_providers': liquidation_providers,
        'liquidation_total_commission': _format_clp(
            sum(
                liquidation.monto_comision_spa
                for liquidation in completed_liquidation_queryset
            )
        ),
        'liquidation_page': completed_liquidation_page,
        'liquidation_page_range': completed_liquidation_page.paginator.get_elided_page_range(
            completed_liquidation_page.number,
        ),
        'liquidation_querystring': liquidation_querystring,
    })


@admin_required
def vista_aprobar_rechazar_solicitud(request, pk):
    if request.method != 'POST':
        return redirect('vista_administrador')

    estado = request.POST.get('estado')
    if estado not in {'True', 'False'}:
        messages.error(request, 'El estado de la solicitud no es válido.')
        return redirect('vista_administrador')

    solicitud = get_object_or_404(Prestador, pk=pk)
    solicitud.estado_aprobacion = estado == 'True'
    solicitud.save(update_fields=['estado_aprobacion'])

    messages.success(request, 'El estado de la solicitud fue actualizado.')
    return redirect(f"{reverse_lazy('vista_administrador')}?section=solicitudes&prestador={pk}")


@admin_required
def vista_actualizar_suscripcion(request, pk):
    if request.method != 'POST':
        return redirect('vista_administrador')

    estado = request.POST.get('estado')
    if estado not in {SuscripcionPrestador.PENDIENTE, SuscripcionPrestador.PAGADA}:
        messages.error(request, 'El estado de suscripción no es válido.')
        return redirect(
            f"{reverse_lazy('vista_administrador')}?section=suscripciones"
        )

    prestador = get_object_or_404(
        Prestador,
        pk=pk,
        estado_aprobacion=True,
    )
    requested_period = request.POST.get('periodo')
    if requested_period:
        try:
            periodo = datetime.strptime(requested_period, '%Y-%m').date().replace(day=1)
        except ValueError:
            messages.error(request, 'El período de suscripción no es válido.')
            return redirect(
                f"{reverse_lazy('vista_administrador')}?section=suscripciones"
            )
    else:
        periodo = timezone.localdate().replace(day=1)
    subscription, _ = SuscripcionPrestador.objects.get_or_create(
        prestador=prestador,
        periodo=periodo,
        defaults={'monto': MONTHLY_SUBSCRIPTION_PRICE},
    )
    subscription.estado = estado
    subscription.monto = MONTHLY_SUBSCRIPTION_PRICE
    subscription.fecha_pago = (
        timezone.now() if estado == SuscripcionPrestador.PAGADA else None
    )
    subscription.registrado_por = request.user
    subscription.save(update_fields=[
        'estado',
        'monto',
        'fecha_pago',
        'registrado_por',
    ])

    messages.success(
        request,
        f'El estado de la suscripción de {periodo:%m/%Y} fue actualizado.',
    )
    return redirect(
        f"{reverse_lazy('vista_administrador')}?section=suscripciones"
        f"&mes_suscripcion={periodo:%Y-%m}"
        f"&estado_pago_suscripcion={request.POST.get('estado_pago_suscripcion', 'todas')}"
    )
