from datetime import date, datetime, time, timedelta

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from website.models import (
    Administrador,
    Cliente,
    Liquidacion,
    Pago,
    Prestador,
    Reserva,
    Servicio,
    ServicioHasLiquidacion,
    SuscripcionPrestador,
)


User = get_user_model()
PASSWORD = 'Demo12345!'


class Command(BaseCommand):
    help = 'Carga datos ficticios amplios para probar RG Beauty.'

    @transaction.atomic
    def handle(self, *args, **options):
        admin_user = self._user(
            'admin_demo',
            'admin@rgbeauty.demo',
            'Camila',
            'Administración',
        )
        administrador = Administrador.objects.filter(usuario=admin_user).first()
        if administrador is None:
            administrador = Administrador.objects.create(
                idadministrador=self._free_admin_id(),
                usuario=admin_user,
                nivel_acceso='administrador',
            )
        else:
            administrador.nivel_acceso = 'administrador'
            administrador.save(update_fields=['nivel_acceso'])

        client_data = [
            ('sofia.cliente', 'sofia.cliente@rgbeauty.demo', 'Sofía Martínez', 'Pasaje Los Aromos 245', '+56987654321'),
            ('valentina.cliente', 'valentina.cliente@rgbeauty.demo', 'Valentina Rojas', 'Avenida Copayapu 1180', '+56976543210'),
            ('martina.cliente', 'martina.cliente@rgbeauty.demo', 'Martina Flores', 'Los Carrera 620', '+56971234567'),
            ('fernanda.cliente', 'fernanda.cliente@rgbeauty.demo', 'Fernanda Gómez', 'O’Higgins 315', '+56969876543'),
            ('javier.cliente', 'javier.cliente@rgbeauty.demo', 'Javier Muñoz', 'Colón 880', '+56966778899'),
        ]
        clients = []
        for username, email, name, address, phone in client_data:
            user = self._user(
                username,
                email,
                name.split()[0],
                ' '.join(name.split()[1:]),
            )
            client, _ = Cliente.objects.update_or_create(
                usuario=user,
                defaults={
                    'nombre': name,
                    'correo': email,
                    'direccion_domicilio': address,
                    'telefono': phone,
                    'nivel_acceso': 'cliente',
                },
            )
            clients.append(client)

        provider_data = [
            ('marena.studio', 'marena.studio@rgbeauty.demo', 'Marena Studio', 'Peluquería', 'CERT-PEL-001', '5 km', True),
            ('camila.soto', 'camila.soto@rgbeauty.demo', 'Camila Soto', 'Peluquería', 'CERT-PEL-005', '3 km', True),
            ('estilo.norte', 'estilo.norte@rgbeauty.demo', 'Estilo Norte', 'Peluquería', 'CERT-PEL-009', '8 km', True),
            ('casa.lila', 'casa.lila@rgbeauty.demo', 'Casa Lila', 'Uñas', 'CERT-UNA-002', '4 km', True),
            ('sofia.nails', 'sofia.nails@rgbeauty.demo', 'Sofía Nails', 'Uñas', 'CERT-UNA-007', '7 km', True),
            ('nails.arcoiris', 'nails.arcoiris@rgbeauty.demo', 'Nails Arcoíris', 'Uñas', 'CERT-UNA-010', '6 km', True),
            ('rg.spa', 'rg.spa@rgbeauty.demo', 'RG Beauty Spa', 'Faciales', 'CERT-FAC-004', '5 km', True),
            ('antonia.perez', 'antonia.perez@rgbeauty.demo', 'Antonia Pérez', 'Faciales', 'CERT-FAC-006', '4 km', True),
            ('piel.radiante', 'piel.radiante@rgbeauty.demo', 'Piel Radiante', 'Faciales', 'CERT-FAC-011', '9 km', True),
            ('blink.atelier', 'blink.atelier@rgbeauty.demo', 'Blink Atelier', 'Cejas', 'CERT-CEJ-003', '6 km', True),
            ('cejas.vale', 'cejas.vale@rgbeauty.demo', 'Valentina Beauty', 'Cejas', 'CERT-CEJ-008', '5 km', True),
            ('miradas.studio', 'miradas.studio@rgbeauty.demo', 'Miradas Studio', 'Pestañas', 'CERT-PES-012', '7 km', True),
            ('lashes.lab', 'lashes.lab@rgbeauty.demo', 'Lashes Lab', 'Pestañas', 'CERT-PES-013', '5 km', True),
            ('glow.mobile', 'glow.mobile@rgbeauty.demo', 'Glow Mobile', 'Otros', 'CERT-OTR-014', '15 km', True),
            ('belleza.conecta', 'belleza.conecta@rgbeauty.demo', 'Belleza Conecta', 'Otros', 'CERT-OTR-015', '12 km', True),
            ('nuevo.brillo', 'nuevo.brillo@rgbeauty.demo', 'Nuevo Brillo', 'Faciales', 'CERT-FAC-016', '10 km', None),
            ('casa.venus', 'casa.venus@rgbeauty.demo', 'Casa Venus', 'Uñas', 'CERT-UNA-017', '11 km', False),
        ]
        providers = {}
        for username, email, name, specialty, certificate, coverage, approved in provider_data:
            user = self._user(
                username,
                email,
                name.split()[0],
                ' '.join(name.split()[1:]),
            )
            provider, _ = Prestador.objects.update_or_create(
                usuario=user,
                defaults={
                    'especialidad': specialty,
                    'numCertificacion_sanitaria': certificate,
                    'radio_cobertura': coverage,
                    'estado_aprobacion': approved,
                    'nivel_acceso': 'prestador',
                },
            )
            providers[username] = provider

        service_catalog = [
            ('marena.studio', 'Peluquería', 'Corte clásico y brushing', 'Corte personalizado lavado y peinado.', 90, 28000),
            ('camila.soto', 'Peluquería', 'Coloración completa', 'Aplicación de color, lavado y peinado.', 120, 42000),
            ('estilo.norte', 'Peluquería', 'Alisado profesional', 'Tratamiento de alisado con protección térmica.', 150, 55000),
            ('casa.lila', 'Uñas', 'Manicure permanente', 'Manicure y esmaltado semipermanente.', 60, 18000),
            ('sofia.nails', 'Uñas', 'Kapping de uñas', 'Estructura reforzada con gel para uñas naturales.', 75, 24000),
            ('nails.arcoiris', 'Uñas', 'Nail art personalizado', 'Diseño artístico y esmalte permanente.', 90, 30000),
            ('rg.spa', 'Faciales', 'Facial hidratación profunda', 'Limpieza, hidratación y mascarilla nutritiva.', 60, 32000),
            ('antonia.perez', 'Faciales', 'Limpieza facial express', 'Purificación facial en formato express.', 40, 18000),
            ('piel.radiante', 'Faciales', 'Peeling básico', 'Exfoliación profesional y tratamiento calmante.', 60, 36000),
            ('blink.atelier', 'Cejas', 'Diseño de cejas', 'Medición, perfilado y depilación precisa.', 45, 14000),
            ('cejas.vale', 'Cejas', 'Henna para cejas', 'Diseño con pigmentación temporal.', 50, 20000),
            ('miradas.studio', 'Pestañas', 'Lifting de pestañas', 'Elevación y fijación de pestañas naturales.', 60, 26000),
            ('lashes.lab', 'Pestañas', 'Extensiones volumen clásico', 'Colocación de extensiones una a una.', 90, 30000),
            ('glow.mobile', 'Otros', 'Maquillaje social', 'Maquillaje completo para eventos.', 75, 35000),
            ('belleza.conecta', 'Otros', 'Masaje corporal relajante', 'Masaje suave de espalda y extremidades.', 60, 29000),
            ('nuevo.brillo', 'Faciales', 'Radiofrecuencia facial', 'Terapia reafirmante facial no invasiva.', 60, 38000),
            ('casa.venus', 'Uñas', 'Recubrimiento de acrílico', 'Colocación y nivelación de acrílico.', 90, 27000),
        ]
        services = []
        for provider_key, category, name, description, duration, price in service_catalog:
            provider = providers[provider_key]
            service, _ = Servicio.objects.update_or_create(
                nombre=name,
                prestador_idprestador=provider,
                defaults={
                    'idservicio': self._service_id(name, provider),
                    'categoria': category,
                    'descripcion': description,
                    'duracion': duration,
                    'precio_base': price,
                },
            )
            services.append(service)

        today = timezone.localdate()
        reservation_specs = [
            (0, -18, 10, 30, 'Completada', [0, 3]),
            (1, -12, 11, 30, 'Completada', [6, 9]),
            (2, -8, 16, 0, 'Completada', [12, 13]),
            (3, -5, 15, 30, 'Completada', [4, 7]),
            (0, -3, 12, 0, 'Rechazada', [1]),
            (1, 1, 10, 30, 'Pendiente', [5, 10]),
            (2, 2, 14, 0, 'Confirmada', [8, 11]),
            (3, 3, 9, 30, 'Pendiente', [2]),
            (4, 4, 17, 0, 'Confirmada', [14, 6]),
            (0, 5, 13, 0, 'Pendiente', [9, 12]),
            (1, 7, 11, 30, 'Confirmada', [3, 13]),
            (2, 9, 18, 0, 'Pendiente', [15]),
            (4, 11, 10, 0, 'Pendiente', [16]),
        ]
        reservations = []
        for index, (client_index, day_offset, hour, minute, status, service_indexes) in enumerate(reservation_specs):
            reservation_date = today + timedelta(days=day_offset)
            naive_datetime = datetime.combine(reservation_date, time(hour, minute))
            hora_bloque = timezone.make_aware(naive_datetime, timezone.get_current_timezone())
            reservation, _ = Reserva.objects.update_or_create(
                cliente_idcliente=clients[client_index],
                fecha=reservation_date,
                hora_bloque=hora_bloque,
                defaults={
                    'idreserva': self._reservation_id(index),
                    'direccion_visita': clients[client_index].direccion_domicilio,
                    'estado': status,
                },
            )
            reservation.servicios.set([services[i] for i in service_indexes])
            reservations.append(reservation)

            if status in {'Completada', 'Confirmada', 'Pendiente'}:
                total = sum(services[i].precio_base for i in service_indexes)
                payment, _ = Pago.objects.update_or_create(
                    reserva_idreserva=reservation,
                    defaults={
                        'idpago': self._payment_id(reservation),
                        'monto_total': total,
                        'metodo_pago': 'Webpay' if index % 2 == 0 else 'Transferencia',
                    },
                )

        for service in services:
            liquidation, _ = Liquidacion.objects.get_or_create(
                administrador_idadministrador=administrador,
                monto_bruto_total=service.precio_base,
                porcentaje_comision=15.0,
                defaults={
                    'idliquidacion': self._liquidation_id(service),
                    'monto_comision_spa': round(service.precio_base * 0.15),
                    'monto_neto_prestador': round(service.precio_base * 0.85),
                },
            )
            ServicioHasLiquidacion.objects.get_or_create(
                servicio=service,
                liquidacion=liquidation,
            )

        current_period = today.replace(day=1)
        for index, provider in enumerate(providers.values()):
            if provider.estado_aprobacion is not True:
                continue
            SuscripcionPrestador.objects.update_or_create(
                prestador=provider,
                periodo=current_period,
                defaults={
                    'monto': 5000,
                    'estado': 'pagada' if index % 3 != 1 else 'pendiente',
                    'fecha_pago': timezone.now() if index % 3 != 1 else None,
                    'registrado_por': administrador.usuario,
                },
            )
            if index % 2 == 0:
                previous_period = (current_period - timedelta(days=1)).replace(day=1)
                SuscripcionPrestador.objects.update_or_create(
                    prestador=provider,
                    periodo=previous_period,
                    defaults={
                        'monto': 5000,
                        'estado': 'pagada',
                        'fecha_pago': timezone.now() - timedelta(days=20),
                        'registrado_por': administrador.usuario,
                    },
                )

        self.stdout.write(self.style.SUCCESS(
            f'Datos demo cargados: {len(providers)} prestadores, '
            f'{len(services)} servicios, {len(clients)} clientes y '
            f'{len(reservations)} reservas.\n'
            'Usuarios demo y contraseña: Demo12345!'
        ))

    @staticmethod
    def _user(username, email, first_name, last_name):
        user, created = User.objects.get_or_create(username=username)
        user.email = email
        user.first_name = first_name
        user.last_name = last_name
        user.set_password(PASSWORD)
        user.save()
        return user

    @staticmethod
    def _free_admin_id():
        existing = Administrador.objects.order_by('-idadministrador').values_list(
            'idadministrador', flat=True
        ).first()
        return (existing or 0) + 1

    @staticmethod
    def _service_id(name, provider):
        service = Servicio.objects.filter(
            nombre=name,
            prestador_idprestador=provider,
        ).first()
        if service:
            return service.idservicio
        last = Servicio.objects.order_by('-idservicio').values_list(
            'idservicio', flat=True
        ).first()
        return (last or 0) + 1

    @staticmethod
    def _reservation_id(index):
        reservation = Reserva.objects.filter(idreserva=1000 + index).first()
        if reservation:
            return reservation.idreserva
        last = Reserva.objects.order_by('-idreserva').values_list(
            'idreserva', flat=True
        ).first()
        if last and last >= 1000:
            return last + 1
        return 1000 + index

    @staticmethod
    def _payment_id(reservation):
        payment = Pago.objects.filter(reserva_idreserva=reservation).first()
        if payment:
            return payment.idpago
        last = Pago.objects.order_by('-idpago').values_list(
            'idpago', flat=True
        ).first()
        return (last or 0) + 1

    @staticmethod
    def _liquidation_id(service):
        liquidation = Liquidacion.objects.filter(servicios=service).first()
        if liquidation:
            return liquidation.idliquidacion
        last = Liquidacion.objects.order_by('-idliquidacion').values_list(
            'idliquidacion', flat=True
        ).first()
        return (last or 0) + 1
