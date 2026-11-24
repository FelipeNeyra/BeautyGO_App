from django.db import migrations, models


def populate_offered_services(apps, schema_editor):
    Prestador = apps.get_model('website', 'Prestador')
    for prestador in Prestador.objects.all().iterator():
        specialty = prestador.especialidad.strip()
        prestador.servicios_ofrecidos = [specialty] if specialty else []
        prestador.save(update_fields=['servicios_ofrecidos'])


class Migration(migrations.Migration):

    dependencies = [
        ('website', '0015_alter_servicio_prestador_idprestador'),
    ]

    operations = [
        migrations.AddField(
            model_name='prestador',
            name='servicios_ofrecidos',
            field=models.JSONField(blank=True, default=list),
        ),
        migrations.RunPython(
            populate_offered_services,
            migrations.RunPython.noop,
        ),
    ]
