from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from datetime import datetime, timedelta

from .models import (
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


class AdminDashboardTests(TestCase):
    def setUp(self):
        self.admin_user = User.objects.create_user(
            username='panel-admin',
            email='admin@example.com',
            password='secure-test-password',
        )
        self.administrator = Administrador.objects.create(
            idadministrador=1,
            usuario=self.admin_user,
        )
        self.provider_user = User.objects.create_user(
            username='professional',
            email='professional@example.com',
            password='secure-test-password',
            first_name='Constanza',
            last_name='Ramirez',
        )
        self.provider = Prestador.objects.create(
            especialidad='Peluquería',
            numCertificacion_sanitaria='CERT-123',
            radio_cobertura='Copiapó',
            estado_aprobacion=None,
            usuario=self.provider_user,
        )

    def test_admin_can_filter_provider_requests_by_status(self):
        approved_user = User.objects.create_user(
            username='approved-request',
            email='approved-request@example.com',
        )
        approved_provider = Prestador.objects.create(
            especialidad='Uñas',
            numCertificacion_sanitaria='CERT-APPROVED',
            radio_cobertura='Copiapó',
            estado_aprobacion=True,
            usuario=approved_user,
        )
        rejected_user = User.objects.create_user(
            username='rejected-request',
            email='rejected-request@example.com',
        )
        rejected_provider = Prestador.objects.create(
            especialidad='Cejas',
            numCertificacion_sanitaria='CERT-REJECTED',
            radio_cobertura='Copiapó',
            estado_aprobacion=False,
            usuario=rejected_user,
        )
        self.client.force_login(self.admin_user)

        pending = self.client.get(
            reverse('vista_administrador'),
            {'section': 'solicitudes', 'estado_solicitud': 'pendientes'},
        )
        approved = self.client.get(
            reverse('vista_administrador'),
            {'section': 'solicitudes', 'estado_solicitud': 'aprobadas'},
        )
        rejected = self.client.get(
            reverse('vista_administrador'),
            {'section': 'solicitudes', 'estado_solicitud': 'rechazadas'},
        )

        self.assertEqual(pending.status_code, 200)
        self.assertIn(self.provider, pending.context['filtered_requests'])
        self.assertNotIn(approved_provider, pending.context['filtered_requests'])
        self.assertNotIn(rejected_provider, pending.context['filtered_requests'])
        self.assertIn(approved_provider, approved.context['filtered_requests'])
        self.assertIn(rejected_provider, rejected.context['filtered_requests'])

    def test_request_dashboard_has_decision_metrics_and_pagination(self):
        for index in range(8):
            user = User.objects.create_user(
                username=f'pending-request-{index}',
                email=f'pending-request-{index}@example.com',
            )
            Prestador.objects.create(
                especialidad='Faciales',
                numCertificacion_sanitaria=f'CERT-PENDING-{index}',
                radio_cobertura='Copiapó',
                estado_aprobacion=None,
                usuario=user,
            )
        approved_user = User.objects.create_user(
            username='metrics-approved',
            email='metrics-approved@example.com',
        )
        Prestador.objects.create(
            especialidad='Uñas',
            numCertificacion_sanitaria='CERT-METRIC-APPROVED',
            radio_cobertura='Copiapó',
            estado_aprobacion=True,
            usuario=approved_user,
        )
        rejected_user = User.objects.create_user(
            username='metrics-rejected',
            email='metrics-rejected@example.com',
        )
        Prestador.objects.create(
            especialidad='Cejas',
            numCertificacion_sanitaria='CERT-METRIC-REJECTED',
            radio_cobertura='Copiapó',
            estado_aprobacion=False,
            usuario=rejected_user,
        )
        self.client.force_login(self.admin_user)

        response = self.client.get(
            reverse('vista_administrador'),
            {'section': 'solicitudes', 'estado_solicitud': 'pendientes'},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context['filtered_requests']), 6)
        self.assertTrue(response.context['request_page'].has_next())
        self.assertEqual(response.context['approved_provider_count'], 1)
        self.assertEqual(response.context['rejected_request_count'], 1)
        self.assertEqual(response.context['decided_request_count'], 2)
        self.assertEqual(response.context['approved_request_percentage'], 50.0)
        self.assertEqual(response.context['rejected_request_percentage'], 50.0)

    def test_admin_login_redirects_to_dashboard(self):
        response = self.client.post(reverse('login'), {
            'username': 'admin@example.com',
            'password': 'secure-test-password',
        })

        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse('vista_administrador'), response['Location'])

    def test_superuser_login_redirects_to_dashboard(self):
        User.objects.create_superuser(
            username='root-admin',
            email='root@example.com',
            password='secure-test-password',
        )

        response = self.client.post(reverse('login'), {
            'username': 'root@example.com',
            'password': 'secure-test-password',
        })

        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse('vista_administrador'), response['Location'])

    def test_dashboard_requires_an_administrator(self):
        regular_user = User.objects.create_user(
            username='regular',
            password='secure-test-password',
        )
        self.client.force_login(regular_user)

        response = self.client.get(reverse('vista_administrador'))

        self.assertEqual(response.status_code, 403)

    def test_admin_can_review_and_decide_on_applications(self):
        self.client.force_login(self.admin_user)
        dashboard = self.client.get(reverse('vista_administrador'))

        self.assertEqual(dashboard.status_code, 200)
        self.assertContains(dashboard, 'Constanza Ramirez')
        self.assertContains(dashboard, 'CERT-123')

        response = self.client.post(
            reverse('estado_solicitud', args=[self.provider.pk]),
            {'estado': 'True'},
        )

        self.provider.refresh_from_db()
        self.assertTrue(self.provider.estado_aprobacion)
        self.assertEqual(response.status_code, 302)

    def test_admin_can_register_and_revert_monthly_subscription_payment(self):
        self.client.force_login(self.admin_user)
        self.provider.estado_aprobacion = True
        self.provider.save(update_fields=['estado_aprobacion'])
        self.client.get(reverse('vista_administrador') + '?section=suscripciones')

        self.assertFalse(SuscripcionPrestador.objects.exists())

        response = self.client.post(
            reverse('actualizar_suscripcion', args=[self.provider.pk]),
            {'estado': SuscripcionPrestador.PAGADA},
        )
        subscription = SuscripcionPrestador.objects.get(prestador=self.provider)

        self.assertEqual(subscription.monto, 5000)
        self.assertEqual(subscription.estado, SuscripcionPrestador.PAGADA)
        self.assertIsNotNone(subscription.fecha_pago)
        self.assertEqual(subscription.registrado_por, self.admin_user)
        self.assertEqual(response.status_code, 302)

        self.client.post(
            reverse('actualizar_suscripcion', args=[self.provider.pk]),
            {'estado': SuscripcionPrestador.PENDIENTE},
        )
        subscription.refresh_from_db()
        self.assertEqual(subscription.estado, SuscripcionPrestador.PENDIENTE)
        self.assertIsNone(subscription.fecha_pago)

    def test_subscription_dashboard_totals_only_paid_amounts_by_selected_month(self):
        self.provider.estado_aprobacion = True
        self.provider.save(update_fields=['estado_aprobacion'])
        selected_month = timezone.localdate().replace(day=1)
        previous_month = (
            selected_month.replace(year=selected_month.year - 1, month=12)
            if selected_month.month == 1
            else selected_month.replace(month=selected_month.month - 1)
        )
        SuscripcionPrestador.objects.create(
            prestador=self.provider,
            periodo=selected_month,
            monto=7000,
            estado=SuscripcionPrestador.PAGADA,
            fecha_pago=timezone.now(),
        )
        SuscripcionPrestador.objects.create(
            prestador=self.provider,
            periodo=previous_month,
            monto=6000,
            estado=SuscripcionPrestador.PAGADA,
            fecha_pago=timezone.now(),
        )
        SuscripcionPrestador.objects.create(
            prestador=self.provider,
            periodo=selected_month.replace(year=selected_month.year - 1),
            monto=9000,
            estado=SuscripcionPrestador.PENDIENTE,
        )
        self.client.force_login(self.admin_user)

        response = self.client.get(
            reverse('vista_administrador'),
            {
                'section': 'suscripciones',
                'mes_suscripcion': previous_month.strftime('%Y-%m'),
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['paid_subscription_total'], '$13.000')
        self.assertEqual(response.context['monthly_subscription_total'], '$6.000')
        self.assertEqual(
            response.context['selected_subscription_month'],
            previous_month,
        )
        self.assertContains(response, 'Mes consultado:')

    def test_subscription_table_can_filter_unpaid_providers(self):
        self.provider.estado_aprobacion = True
        self.provider.save(update_fields=['estado_aprobacion'])
        paid_user = User.objects.create_user(
            username='paid-provider',
            email='paid-provider@example.com',
        )
        paid_provider = Prestador.objects.create(
            especialidad='Uñas',
            numCertificacion_sanitaria='CERT-PAID',
            radio_cobertura='Copiapó',
            estado_aprobacion=True,
            usuario=paid_user,
        )
        pending_user = User.objects.create_user(
            username='pending-provider',
            email='pending-provider@example.com',
        )
        pending_provider = Prestador.objects.create(
            especialidad='Cejas',
            numCertificacion_sanitaria='CERT-PENDING',
            radio_cobertura='Copiapó',
            estado_aprobacion=True,
            usuario=pending_user,
        )
        current_period = timezone.localdate().replace(day=1)
        SuscripcionPrestador.objects.create(
            prestador=paid_provider,
            periodo=current_period,
            monto=5000,
            estado=SuscripcionPrestador.PAGADA,
            fecha_pago=timezone.now(),
        )
        SuscripcionPrestador.objects.create(
            prestador=pending_provider,
            periodo=current_period,
            monto=5000,
            estado=SuscripcionPrestador.PENDIENTE,
        )
        self.client.force_login(self.admin_user)

        response = self.client.get(
            reverse('vista_administrador'),
            {
                'section': 'suscripciones',
                'estado_pago_suscripcion': 'pendientes',
            },
        )

        visible_providers = [
            row['prestador'] for row in response.context['subscription_rows']
        ]
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            set(visible_providers),
            {self.provider, pending_provider},
        )
        self.assertNotIn(paid_provider, visible_providers)
        self.assertEqual(response.context['pending_subscription_count'], 2)

    def test_admin_subscription_action_updates_the_selected_month(self):
        self.provider.estado_aprobacion = True
        self.provider.save(update_fields=['estado_aprobacion'])
        current_period = timezone.localdate().replace(day=1)
        previous_period = (
            current_period.replace(year=current_period.year - 1, month=12)
            if current_period.month == 1
            else current_period.replace(month=current_period.month - 1)
        )
        self.client.force_login(self.admin_user)
        response = self.client.post(
            reverse('actualizar_suscripcion', args=[self.provider.pk]),
            {
                'estado': SuscripcionPrestador.PAGADA,
                'periodo': previous_period.strftime('%Y-%m'),
                'mes_suscripcion': previous_period.strftime('%Y-%m'),
                'estado_pago_suscripcion': 'pendientes',
            },
        )

        subscription = SuscripcionPrestador.objects.get(
            prestador=self.provider,
            periodo=previous_period,
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn(
            f'mes_suscripcion={previous_period:%Y-%m}',
            response['Location'],
        )
        self.assertEqual(subscription.estado, SuscripcionPrestador.PAGADA)
        self.assertFalse(
            SuscripcionPrestador.objects.filter(
                prestador=self.provider,
                periodo=current_period,
            ).exists()
        )

    def test_subscription_payment_cannot_be_changed_by_non_admin(self):
        regular_user = User.objects.create_user(
            username='regular',
            password='secure-test-password',
        )
        self.provider.estado_aprobacion = True
        self.provider.save(update_fields=['estado_aprobacion'])
        self.client.force_login(regular_user)

        response = self.client.post(
            reverse('actualizar_suscripcion', args=[self.provider.pk]),
            {'estado': SuscripcionPrestador.PAGADA},
        )

        self.assertEqual(response.status_code, 403)
        self.assertFalse(SuscripcionPrestador.objects.exists())

    def test_liquidations_are_visible_in_dashboard(self):
        self.client.force_login(self.admin_user)
        self.provider.estado_aprobacion = True
        self.provider.save(update_fields=['estado_aprobacion'])
        service = Servicio.objects.create(
            idservicio=1,
            nombre='Corte y brushing',
            duracion=90,
            precio_base=28000,
            prestador_idprestador=self.provider,
        )
        liquidation = Liquidacion.objects.create(
            idliquidacion=1,
            monto_bruto_total=28000,
            porcentaje_comision=15.0,
            monto_comision_spa=4200,
            monto_neto_prestador=23800,
            administrador_idadministrador=self.administrator,
        )
        ServicioHasLiquidacion.objects.create(
            servicio=service,
            liquidacion=liquidation,
        )
        client_user = User.objects.create_user(
            username='liquidation-client',
            password='secure-test-password',
        )
        client_profile = Cliente.objects.create(
            nombre='Cliente Liquidación',
            correo='liquidation-client@example.com',
            direccion_domicilio='Copiapó',
            telefono='912345678',
            usuario=client_user,
        )
        completed_reservation = Reserva.objects.create(
            idreserva=21,
            fecha='2026-01-10',
            hora_bloque='2026-01-10T10:00:00Z',
            direccion_visita='Copiapó',
            estado='Completada',
            cliente_idcliente=client_profile,
        )
        completed_reservation.servicios.add(service)

        response = self.client.get(
            reverse('vista_administrador') + '?section=liquidaciones'
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Corte y brushing')
        self.assertContains(response, '$28.000')
        self.assertContains(response, '$23.800')

    def test_liquidations_can_be_filtered_by_provider_and_service(self):
        self.client.force_login(self.admin_user)
        other_user = User.objects.create_user(
            username='other-professional',
            first_name='Otra',
            last_name='Profesional',
        )
        other_provider = Prestador.objects.create(
            especialidad='Uñas',
            numCertificacion_sanitaria='CERT-OTHER',
            radio_cobertura='Copiapó',
            estado_aprobacion=True,
            usuario=other_user,
        )
        other_service = Servicio.objects.create(
            idservicio=2,
            nombre='Manicure permanente',
            duracion=60,
            precio_base=18000,
            prestador_idprestador=other_provider,
        )
        other_liquidation = Liquidacion.objects.create(
            idliquidacion=2,
            monto_bruto_total=18000,
            porcentaje_comision=15.0,
            monto_comision_spa=2700,
            monto_neto_prestador=15300,
            administrador_idadministrador=self.administrator,
        )
        ServicioHasLiquidacion.objects.create(
            servicio=other_service,
            liquidacion=other_liquidation,
        )
        client_user = User.objects.create_user(
            username='filtered-liquidation-client',
            password='secure-test-password',
        )
        client_profile = Cliente.objects.create(
            nombre='Cliente Filtrado',
            correo='filtered-liquidation-client@example.com',
            direccion_domicilio='Copiapó',
            telefono='912345678',
            usuario=client_user,
        )
        completed_reservation = Reserva.objects.create(
            idreserva=22,
            fecha='2026-01-11',
            hora_bloque='2026-01-11T10:00:00Z',
            direccion_visita='Copiapó',
            estado='Completada',
            cliente_idcliente=client_profile,
        )
        completed_reservation.servicios.add(other_service)

        response = self.client.get(
            reverse('vista_administrador'),
            {
                'section': 'liquidaciones',
                'prestador': str(other_provider.pk),
                'q': 'Manicure',
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Manicure permanente')
        self.assertNotContains(response, 'Corte y brushing')
        self.assertEqual(
            [row['liquidation'].pk for row in response.context['liquidation_rows']],
            [other_liquidation.pk],
        )


class ProviderDashboardTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='provider-client',
            email='provider@example.com',
            password='secure-test-password',
            first_name='Constanza',
            last_name='Ramirez',
        )
        self.client_profile = Cliente.objects.create(
            nombre='Constanza Ramirez',
            correo=self.user.email,
            direccion_domicilio='Copiapó',
            telefono='912345678',
            usuario=self.user,
        )
        self.provider = Prestador.objects.create(
            especialidad='Peluquería',
            numCertificacion_sanitaria='CERT-456',
            radio_cobertura='Copiapó',
            estado_aprobacion=True,
            usuario=self.user,
        )
        self.service = Servicio.objects.create(
            idservicio=5,
            nombre='Corte y brushing',
            duracion=90,
            precio_base=28000,
            prestador_idprestador=self.provider,
        )
        self.client.force_login(self.user)

    def test_provider_dashboard_shows_services_and_account_panel_link(self):
        response = self.client.get(reverse('vista_prestador'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Tu perfil fue aprobado')
        self.assertContains(response, 'Corte y brushing')
        self.assertContains(response, 'Agregar dirección de atención')
        self.assertContains(response, 'Ir a la página web')
        self.assertNotContains(response, '>Prestador</a>')

    def test_provider_services_are_searchable_and_paginated(self):
        for service_id in range(6, 14):
            Servicio.objects.create(
                idservicio=service_id,
                nombre=f'Servicio {service_id}',
                descripcion='Servicio para paginación',
                duracion=60,
                precio_base=10000 + service_id,
                prestador_idprestador=self.provider,
            )

        response = self.client.get(
            reverse('vista_prestador'),
            {'q': 'paginación', 'orden': 'precio'},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Página 1 de 2')
        self.assertContains(response, 'q=paginaci%C3%B3n')
        self.assertContains(response, 'orden=precio')

        response = self.client.get(
            reverse('vista_prestador'),
            {'q': 'Corte', 'categoria': 'peluqueria'},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Corte y brushing')
        self.assertNotContains(response, 'Servicio 6')

    def test_any_visitor_can_view_details_of_an_approved_service(self):
        self.client.logout()

        response = self.client.get(
            reverse('detalle_servicio', args=[self.service.pk])
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Corte y brushing')
        self.assertContains(response, 'Peluquería')
        self.assertContains(response, 'Constanza Ramirez')
        self.assertContains(response, '90 minutos')

    def test_home_catalog_is_searchable_and_paginated(self):
        self.client.logout()
        for service_id in range(6, 13):
            Servicio.objects.create(
                idservicio=service_id,
                nombre=f'Catálogo {service_id}',
                descripcion='Servicio facial disponible',
                categoria='Faciales',
                duracion=45,
                precio_base=12000,
                prestador_idprestador=self.provider,
            )

        response = self.client.get(
            reverse('home'),
            {'q': 'facial', 'categoria': 'faciales', 'orden': 'precio'},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Página 1 de 2')
        self.assertContains(response, 'q=facial')
        self.assertContains(response, 'categoria=faciales')
        self.assertContains(response, 'orden=precio')

    def test_home_shows_empty_message_when_no_service_matches(self):
        response = self.client.get(
            reverse('home'),
            {'q': 'servicio inexistente'},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'No hay registros disponibles')
        self.assertNotContains(response, 'Próximamente')

    def test_home_includes_services_below_ten_thousand_pesos(self):
        self.service.precio_base = 5000
        self.service.save(update_fields=['precio_base'])

        response = self.client.get(reverse('home'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Corte y brushing')

    def test_home_catalog_can_be_filtered_by_provider(self):
        other_user = User.objects.create_user(
            username='other-catalog-provider',
            first_name='Otra',
            last_name='Profesional',
        )
        other_provider = Prestador.objects.create(
            especialidad='Uñas',
            numCertificacion_sanitaria='CERT-OTHER-CATALOG',
            radio_cobertura='Copiapó',
            estado_aprobacion=True,
            usuario=other_user,
        )
        other_service = Servicio.objects.create(
            idservicio=90,
            nombre='Manicure de prueba',
            duracion=60,
            precio_base=18000,
            prestador_idprestador=other_provider,
        )

        response = self.client.get(
            reverse('home'),
            {'prestador': str(other_provider.pk)},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            [service['id'] for service in response.context['services']],
            [other_service.pk],
        )

    def test_home_catalog_price_and_rating_ranges_filter_services(self):
        response = self.client.get(
            reverse('home'),
            {
                'precio_min': '20000',
                'precio_max': '30000',
                'calificacion_min': '4.8',
                'calificacion_max': '5',
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            [service['id'] for service in response.context['services']],
            [self.service.pk],
        )
        self.assertEqual(response.context['service_price_min'], 20000)
        self.assertEqual(response.context['service_rating_min'], 4.8)

        response = self.client.get(
            reverse('home'),
            {'precio_min': '30000', 'precio_max': '100000'},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(list(response.context['services']), [])

    def test_unapproved_service_is_not_visible_in_service_details(self):
        self.provider.estado_aprobacion = None
        self.provider.save(update_fields=['estado_aprobacion'])

        response = self.client.get(
            reverse('detalle_servicio', args=[self.service.pk])
        )

        self.assertEqual(response.status_code, 404)

    def test_provider_can_publish_and_edit_only_their_own_services(self):
        response = self.client.post(reverse('vista_prestador'), {
            'action': 'guardar_servicio',
            'categoria': 'Uñas',
            'nombre': 'Manicure permanente',
            'descripcion': 'Manicure permanente con nivelación y diseño sencillo.',
            'duracion': '60',
            'precio_base': '18000',
        })

        self.assertEqual(response.status_code, 302)
        created_service = Servicio.objects.get(nombre='Manicure permanente')
        self.assertEqual(created_service.prestador_idprestador, self.provider)
        self.assertEqual(created_service.idservicio, 6)
        self.assertEqual(created_service.categoria, 'Uñas')
        self.assertEqual(created_service.descripcion, 'Manicure permanente con nivelación y diseño sencillo.')

        response = self.client.post(reverse('vista_prestador'), {
            'action': 'guardar_servicio',
            'service_id': str(self.service.pk),
            'categoria': 'Peluquería',
            'nombre': 'Corte actualizado',
            'descripcion': 'Corte personalizado y brushing.',
            'duracion': '60',
            'precio_base': '30000',
        })

        self.assertEqual(response.status_code, 302)
        self.service.refresh_from_db()
        self.assertEqual(self.service.nombre, 'Corte actualizado')

    def test_provider_can_confirm_and_delete_their_own_service(self):
        response = self.client.get(
            reverse('vista_prestador') + f'?section=servicios&eliminar={self.service.pk}'
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '¿Eliminar «Corte y brushing»?')
        self.assertContains(response, 'name="action" value="eliminar_servicio"')

        response = self.client.post(reverse('vista_prestador'), {
            'action': 'eliminar_servicio',
            'service_id': str(self.service.pk),
        })

        self.assertRedirects(response, reverse('vista_prestador'))
        self.assertFalse(Servicio.objects.filter(pk=self.service.pk).exists())

    def test_provider_cannot_delete_another_providers_service(self):
        other_user = User.objects.create_user(
            username='other-provider',
            password='secure-test-password',
        )
        other_provider = Prestador.objects.create(
            especialidad='Uñas',
            numCertificacion_sanitaria='CERT-789',
            radio_cobertura='Copiapó',
            estado_aprobacion=True,
            usuario=other_user,
        )
        other_service = Servicio.objects.create(
            idservicio=8,
            nombre='Servicio ajeno',
            duracion=60,
            precio_base=15000,
            prestador_idprestador=other_provider,
        )

        response = self.client.post(reverse('vista_prestador'), {
            'action': 'eliminar_servicio',
            'service_id': str(other_service.pk),
        })

        self.assertEqual(response.status_code, 404)
        self.assertTrue(Servicio.objects.filter(pk=other_service.pk).exists())

    def test_service_fields_are_validated_before_publishing(self):
        response = self.client.post(reverse('vista_prestador'), {
            'action': 'guardar_servicio',
            'categoria': 'Categoría inválida',
            'nombre': '   ',
            'descripcion': '',
            'duracion': '75',
            'precio_base': '500',
        })

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Selecciona una categoría válida.')
        self.assertContains(response, 'Ingresa el nombre del servicio.')
        self.assertContains(response, 'Ingresa una descripción del servicio.')
        self.assertContains(response, 'Selecciona una duración válida.')
        self.assertContains(response, 'El precio mínimo es $1.000 CLP.')
        self.assertEqual(Servicio.objects.filter(
            prestador_idprestador=self.provider,
        ).count(), 1)

    def test_subscription_section_shows_current_status_and_payment_history(self):
        current_period = timezone.localdate().replace(day=1)
        previous_period = (
            current_period.replace(year=current_period.year - 1, month=12)
            if current_period.month == 1
            else current_period.replace(month=current_period.month - 1)
        )
        SuscripcionPrestador.objects.create(
            prestador=self.provider,
            periodo=previous_period,
            monto=5000,
            estado=SuscripcionPrestador.PAGADA,
            fecha_pago=timezone.now(),
        )

        response = self.client.get(
            reverse('vista_prestador') + '?section=suscripcion'
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Suscripción profesional')
        self.assertContains(response, 'Pago pendiente')
        self.assertContains(response, 'Pagar suscripción · $5.000')
        self.assertContains(response, 'Historial de mensualidades')
        self.assertContains(response, 'Pagos anteriores')
        self.assertContains(response, 'Pagada')

    def test_provider_can_simulate_current_month_subscription_payment_once(self):
        payment_url = reverse('vista_prestador') + '?section=suscripcion'
        response = self.client.post(reverse('vista_prestador'), {
            'action': 'pagar_suscripcion',
        })

        self.assertRedirects(response, payment_url)
        subscription = SuscripcionPrestador.objects.get(prestador=self.provider)
        self.assertEqual(subscription.periodo, timezone.localdate().replace(day=1))
        self.assertEqual(subscription.estado, SuscripcionPrestador.PAGADA)
        self.assertEqual(subscription.monto, 5000)
        self.assertIsNotNone(subscription.fecha_pago)
        self.assertEqual(subscription.registrado_por, self.user)

        payment_date = subscription.fecha_pago
        response = self.client.post(reverse('vista_prestador'), {
            'action': 'pagar_suscripcion',
        })

        self.assertRedirects(response, payment_url)
        self.assertEqual(
            SuscripcionPrestador.objects.filter(prestador=self.provider).count(),
            1,
        )
        subscription.refresh_from_db()
        self.assertEqual(subscription.fecha_pago, payment_date)

    def test_provider_can_manage_only_reservations_for_their_services(self):
        reservation = Reserva.objects.create(
            idreserva=10,
            fecha='2030-01-10',
            hora_bloque='2030-01-10T10:00:00Z',
            direccion_visita='Copiapó',
            estado='Pendiente',
            cliente_idcliente=self.client_profile,
        )
        reservation.servicios.add(self.service)

        response = self.client.get(reverse('vista_prestador') + '?section=reservas')

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Corte y brushing')
        self.assertContains(response, 'Constanza Ramirez')

        response = self.client.post(reverse('vista_prestador'), {
            'action': 'actualizar_reserva',
            'reserva_id': str(reservation.pk),
            'estado': 'Confirmada',
        })

        self.assertEqual(response.status_code, 302)
        reservation.refresh_from_db()
        self.assertEqual(reservation.estado, 'Confirmada')

    def test_provider_cannot_complete_reservation_before_scheduled_time(self):
        reservation = Reserva.objects.create(
            idreserva=11,
            fecha=(timezone.localdate() + timedelta(days=1)),
            hora_bloque=timezone.now() + timedelta(days=1),
            direccion_visita='Copiapó',
            estado='Confirmada',
            cliente_idcliente=self.client_profile,
        )
        reservation.servicios.add(self.service)

        response = self.client.post(reverse('vista_prestador'), {
            'action': 'actualizar_reserva',
            'reserva_id': str(reservation.pk),
            'estado': 'Completada',
        })

        self.assertEqual(response.status_code, 302)
        reservation.refresh_from_db()
        self.assertEqual(reservation.estado, 'Confirmada')
        self.assertFalse(Liquidacion.objects.exists())

    def test_completed_reservation_updates_payment_and_creates_liquidation(self):
        admin_user = User.objects.create_superuser(
            username='liquidation-admin',
            email='liquidation-admin@example.com',
            password='secure-test-password',
        )
        administrator = Administrador.objects.create(
            idadministrador=1,
            usuario=admin_user,
        )
        reservation = Reserva.objects.create(
            idreserva=12,
            fecha=(timezone.localdate() - timedelta(days=1)),
            hora_bloque=timezone.now() - timedelta(hours=1),
            direccion_visita='Copiapó',
            estado='Confirmada',
            cliente_idcliente=self.client_profile,
        )
        reservation.servicios.add(self.service)
        payment = Pago.objects.create(
            idpago=12,
            monto_total=8400,
            metodo_pago='Abono inicial',
            reserva_idreserva=reservation,
        )

        response = self.client.post(reverse('vista_prestador'), {
            'action': 'actualizar_reserva',
            'reserva_id': str(reservation.pk),
            'estado': 'Completada',
        })

        self.assertEqual(response.status_code, 302)
        reservation.refresh_from_db()
        payment.refresh_from_db()
        liquidation = Liquidacion.objects.get()
        self.assertEqual(reservation.estado, 'Completada')
        self.assertEqual(payment.monto_total, 28000)
        self.assertEqual(liquidation.monto_bruto_total, 28000)
        self.assertEqual(liquidation.monto_comision_spa, 4200)
        self.assertEqual(liquidation.monto_neto_prestador, 23800)
        self.assertEqual(liquidation.administrador_idadministrador, administrator)
        self.assertTrue(liquidation.servicios.filter(pk=self.service.pk).exists())

    def test_unapproved_provider_cannot_publish_services(self):
        self.provider.estado_aprobacion = None
        self.provider.save(update_fields=['estado_aprobacion'])

        response = self.client.post(reverse('vista_prestador'), {
            'action': 'guardar_servicio',
            'categoria': 'Peluquería',
            'nombre': 'Servicio pendiente',
            'descripcion': 'Servicio en espera de aprobación.',
            'duracion': '60',
            'precio_base': '10000',
        })

        self.assertEqual(response.status_code, 302)
        self.assertFalse(Servicio.objects.filter(nombre='Servicio pendiente').exists())

    def test_only_a_registered_client_can_apply_as_provider(self):
        new_user = User.objects.create_user(
            username='not-yet-client',
            email='new@example.com',
            password='secure-test-password',
        )
        self.client.force_login(new_user)

        response = self.client.get(reverse('solicitud_prestador'))

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response['Location'], reverse('datos_usuario'))

    def test_registered_client_applies_using_the_same_account_and_email(self):
        new_user = User.objects.create_user(
            username='new-provider-client',
            email='new-provider@example.com',
            password='secure-test-password',
        )
        client_profile = Cliente.objects.create(
            nombre='Nuevo cliente',
            correo=new_user.email,
            direccion_domicilio='Copiapó',
            telefono='912345678',
            usuario=new_user,
        )
        self.client.force_login(new_user)

        response = self.client.post(reverse('solicitud_prestador'), {
            'especialidad': 'Uñas',
            'numCertificacion_sanitaria': 'CERT-NEW',
            'radio_cobertura': 'Copiapó',
        })

        self.assertEqual(response.status_code, 302)
        provider = Prestador.objects.get(usuario=new_user)
        self.assertEqual(provider.usuario.email, client_profile.correo)
        self.assertIsNone(provider.estado_aprobacion)


class PrivilegedBookingTests(TestCase):
    def test_booking_time_is_saved_and_read_as_local_time(self):
        provider_user = User.objects.create_user(
            username='timezone-provider',
            email='timezone-provider@example.com',
        )
        provider = Prestador.objects.create(
            especialidad='Faciales',
            numCertificacion_sanitaria='CERT-TIMEZONE',
            radio_cobertura='Copiapó',
            estado_aprobacion=True,
            usuario=provider_user,
        )
        service = Servicio.objects.create(
            idservicio=44,
            nombre='Horario zona horaria',
            duracion=60,
            precio_base=25000,
            prestador_idprestador=provider,
        )
        client_user = User.objects.create_user(
            username='timezone-client',
            email='timezone-client@example.com',
        )
        Cliente.objects.create(
            nombre='Cliente zona horaria',
            correo=client_user.email,
            direccion_domicilio='Copiapó',
            telefono='912345678',
            usuario=client_user,
        )
        self.client.force_login(client_user)

        reservation_date = timezone.localdate() + timedelta(days=3)
        response = self.client.post(reverse('reservas'), {
            'service_id': str(service.pk),
            'date': reservation_date.isoformat(),
            'time': '11:30',
            'contact_name': 'Cliente zona horaria',
            'contact_email': client_user.email,
            'contact_phone': '912345678',
            'address': 'Copiapó',
            'payment_status': 'success',
        })

        reservation = Reserva.objects.get(
            cliente_idcliente__usuario=client_user,
        )
        local_time = timezone.localtime(
            reservation.hora_bloque,
            timezone.get_current_timezone(),
        ).strftime('%H:%M')

        self.assertEqual(response.status_code, 302)
        self.assertEqual(reservation.fecha, reservation_date)
        self.assertEqual(local_time, '11:30')

    def test_home_exposes_reservation_intervals_to_the_booking_modal(self):
        reservation_date = timezone.localdate() + timedelta(days=2)
        provider_user = User.objects.create_user(
            username='occupied-display-provider',
            email='occupied-display-provider@example.com',
        )
        provider = Prestador.objects.create(
            especialidad='Faciales',
            numCertificacion_sanitaria='CERT-DISPLAY',
            radio_cobertura='Copiapó',
            estado_aprobacion=True,
            usuario=provider_user,
        )
        service = Servicio.objects.create(
            idservicio=43,
            nombre='Facial ocupado',
            duracion=60,
            precio_base=25000,
            prestador_idprestador=provider,
        )
        client_user = User.objects.create_user(
            username='occupied-display-client',
            email='occupied-display-client@example.com',
        )
        client = Cliente.objects.create(
            nombre='Cliente visual',
            correo=client_user.email,
            direccion_domicilio='Copiapó',
            telefono='912345678',
            usuario=client_user,
        )
        reservation = Reserva.objects.create(
            idreserva=43,
            fecha=reservation_date,
            hora_bloque=timezone.make_aware(
                datetime.combine(reservation_date, datetime.strptime('11:30', '%H:%M').time()),
                timezone.get_current_timezone(),
            ),
            direccion_visita='Copiapó',
            estado='Pendiente',
            cliente_idcliente=client,
        )
        reservation.servicios.add(service)
        self.client.force_login(client_user)

        response = self.client.get(reverse('home'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'data-service-duration="60"')
        slot_key = f'{provider.pk}|{reservation_date.isoformat()}'
        self.assertIn(slot_key, response.context['booking_occupied_intervals'])
        self.assertIn(
            {'start': 690, 'end': 750},
            response.context['booking_occupied_intervals'][slot_key],
        )

    def test_reservation_duration_blocks_overlapping_start_times(self):
        provider_user = User.objects.create_user(
            username='overlap-provider',
            email='overlap-provider@example.com',
        )
        provider = Prestador.objects.create(
            especialidad='Faciales',
            numCertificacion_sanitaria='CERT-OVERLAP',
            radio_cobertura='Copiapó',
            estado_aprobacion=True,
            usuario=provider_user,
        )
        hour_service = Servicio.objects.create(
            idservicio=45,
            nombre='Servicio de una hora',
            duracion=60,
            precio_base=25000,
            prestador_idprestador=provider,
        )
        half_hour_service = Servicio.objects.create(
            idservicio=46,
            nombre='Servicio de media hora',
            duracion=30,
            precio_base=18000,
            prestador_idprestador=provider,
        )
        client_user = User.objects.create_user(
            username='overlap-client',
            email='overlap-client@example.com',
            password='secure-test-password',
        )
        Cliente.objects.create(
            nombre='Cliente de prueba',
            correo=client_user.email,
            direccion_domicilio='Copiapó',
            telefono='912345678',
            usuario=client_user,
        )
        self.client.force_login(client_user)
        booking_data = {
            'date': '2030-01-10',
            'contact_name': 'Cliente de prueba',
            'contact_email': client_user.email,
            'contact_phone': '912345678',
            'address': 'Copiapó',
            'payment_status': 'success',
        }

        first_response = self.client.post(reverse('reservas'), {
            **booking_data,
            'service_id': str(hour_service.pk),
            'time': '18:00',
        })
        overlapping_response = self.client.post(reverse('reservas'), {
            **booking_data,
            'service_id': str(half_hour_service.pk),
            'time': '18:30',
        })
        adjacent_response = self.client.post(reverse('reservas'), {
            **booking_data,
            'service_id': str(half_hour_service.pk),
            'time': '19:00',
        })

        self.assertEqual(first_response.status_code, 302)
        self.assertEqual(overlapping_response.status_code, 302)
        self.assertEqual(adjacent_response.status_code, 302)
        self.assertEqual(
            Reserva.objects.filter(
                fecha='2030-01-10',
                servicios__prestador_idprestador=provider,
            ).count(),
            2,
        )
        self.assertEqual(Pago.objects.count(), 2)

    def test_cannot_reserve_the_same_provider_at_the_same_time(self):
        provider_user = User.objects.create_user(
            username='occupied-provider',
            email='occupied-provider@example.com',
        )
        provider = Prestador.objects.create(
            especialidad='Faciales',
            numCertificacion_sanitaria='CERT-OCCUPIED',
            radio_cobertura='Copiapó',
            estado_aprobacion=True,
            usuario=provider_user,
        )
        first_service = Servicio.objects.create(
            idservicio=41,
            nombre='Limpieza facial',
            duracion=60,
            precio_base=25000,
            prestador_idprestador=provider,
        )
        second_service = Servicio.objects.create(
            idservicio=42,
            nombre='Mascarilla facial',
            duracion=30,
            precio_base=18000,
            prestador_idprestador=provider,
        )
        client_user = User.objects.create_user(
            username='occupied-client',
            email='occupied-client@example.com',
            password='secure-test-password',
        )
        Cliente.objects.create(
            nombre='Cliente ocupado',
            correo=client_user.email,
            direccion_domicilio='Copiapó',
            telefono='912345678',
            usuario=client_user,
        )
        self.client.force_login(client_user)

        booking_data = {
            'date': '2030-01-10',
            'time': '11:30',
            'contact_name': 'Cliente ocupado',
            'contact_email': client_user.email,
            'contact_phone': '912345678',
            'address': 'Copiapó',
            'payment_status': 'success',
        }

        first_response = self.client.post(reverse('reservas'), {
            **booking_data,
            'service_id': str(first_service.pk),
        })
        second_response = self.client.post(reverse('reservas'), {
            **booking_data,
            'service_id': str(second_service.pk),
        })

        self.assertEqual(first_response.status_code, 302)
        self.assertEqual(second_response.status_code, 302)
        self.assertEqual(
            Reserva.objects.filter(
                fecha='2030-01-10',
                estado__in=['Pendiente', 'Confirmada', 'Completada'],
                servicios__prestador_idprestador=provider,
            ).count(),
            1,
        )
        self.assertEqual(Pago.objects.count(), 1)

    def test_registered_client_can_open_the_home_page_without_provider_profile(self):
        user = User.objects.create_user(
            username='normal-client',
            email='normal-client@example.com',
            password='secure-test-password',
        )
        Cliente.objects.create(
            nombre='Cliente normal',
            correo=user.email,
            direccion_domicilio='Copiapó',
            telefono='912345678',
            usuario=user,
        )
        self.client.force_login(user)

        response = self.client.get(reverse('home'))

        self.assertEqual(response.status_code, 200)

    def test_administrator_can_open_the_catalog_to_book_a_service(self):
        admin_user = User.objects.create_user(
            username='catalog-admin',
            email='catalog-admin@example.com',
            password='secure-test-password',
        )
        Administrador.objects.create(idadministrador=3, usuario=admin_user)
        provider_user = User.objects.create_user(
            username='catalog-provider',
            email='catalog-provider@example.com',
        )
        provider = Prestador.objects.create(
            especialidad='Peluquería',
            numCertificacion_sanitaria='CERT-CATALOG',
            radio_cobertura='Copiapó',
            estado_aprobacion=True,
            usuario=provider_user,
        )
        Servicio.objects.create(
            idservicio=30,
            nombre='Corte disponible',
            duracion=60,
            precio_base=20000,
            prestador_idprestador=provider,
        )
        self.client.force_login(admin_user)

        response = self.client.get(reverse('home'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'data-service-name="Corte disponible"')
        self.assertContains(response, 'Reservar')
        self.assertNotContains(response, 'Próximamente')
        self.assertContains(response, 'Panel admin')

    def test_registered_provider_can_open_booking_for_a_catalog_service(self):
        provider_user = User.objects.create_user(
            username='booking-provider',
            email='booking-provider@example.com',
        )
        Cliente.objects.create(
            nombre='Proveedor cliente',
            correo=provider_user.email,
            direccion_domicilio='Copiapó',
            telefono='912345678',
            usuario=provider_user,
        )
        Prestador.objects.create(
            especialidad='Uñas',
            numCertificacion_sanitaria='CERT-OWN',
            radio_cobertura='Copiapó',
            estado_aprobacion=True,
            usuario=provider_user,
        )
        service_provider_user = User.objects.create_user(
            username='other-booking-provider',
            email='other-booking-provider@example.com',
        )
        service_provider = Prestador.objects.create(
            especialidad='Faciales',
            numCertificacion_sanitaria='CERT-OTHER',
            radio_cobertura='Copiapó',
            estado_aprobacion=True,
            usuario=service_provider_user,
        )
        service = Servicio.objects.create(
            idservicio=31,
            nombre='Facial reservable',
            duracion=60,
            precio_base=25000,
            prestador_idprestador=service_provider,
        )
        self.client.force_login(provider_user)

        catalog = self.client.get(reverse('home'))

        self.assertEqual(catalog.status_code, 200)
        self.assertContains(catalog, 'data-service-name="Facial reservable"')
        self.assertContains(catalog, 'Reservar')
        self.assertNotContains(catalog, 'Próximamente')

        response = self.client.post(reverse('reservas'), {
            'service_id': str(service.pk),
            'date': '2030-01-10',
            'time': '10:00',
            'contact_name': 'Proveedor cliente',
            'contact_email': provider_user.email,
            'contact_phone': '912345678',
            'address': 'Copiapó',
            'payment_status': 'success',
        })

        self.assertEqual(response.status_code, 302)
        self.assertTrue(
            Reserva.objects.filter(
                cliente_idcliente__usuario=provider_user,
                servicios=service,
            ).exists()
        )

    def test_administrator_can_book_and_get_a_client_profile(self):
        admin_user = User.objects.create_user(
            username='booking-admin',
            email='booking-admin@example.com',
            password='secure-test-password',
        )
        Administrador.objects.create(idadministrador=2, usuario=admin_user)
        provider_user = User.objects.create_user(
            username='approved-provider',
            email='approved-provider@example.com',
        )
        provider = Prestador.objects.create(
            especialidad='Faciales',
            numCertificacion_sanitaria='CERT-789',
            radio_cobertura='Copiapó',
            estado_aprobacion=True,
            usuario=provider_user,
        )
        service = Servicio.objects.create(
            idservicio=1,
            nombre='Facial hidratación profunda',
            duracion=60,
            precio_base=32000,
            prestador_idprestador=provider,
        )
        self.client.force_login(admin_user)

        response = self.client.post(reverse('reservas'), {
            'service_id': str(service.pk),
            'date': '2030-01-10',
            'time': '10:00',
            'contact_name': 'Administración Beauty Go',
            'contact_email': admin_user.email,
            'contact_phone': '912345678',
            'address': 'Copiapó',
            'payment_status': 'success',
        })

        self.assertEqual(response.status_code, 302)
        client_profile = Cliente.objects.get(usuario=admin_user)
        reservation = Reserva.objects.get(cliente_idcliente=client_profile)
        self.assertEqual(reservation.servicios.get(), service)
        self.assertTrue(Pago.objects.filter(reserva_idreserva=reservation).exists())
