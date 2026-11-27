from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('website', '0016_prestador_servicios_ofrecidos'),
    ]

    operations = [
        migrations.AddField(
            model_name='servicio',
            name='categoria_personalizada',
            field=models.CharField(blank=True, default='', max_length=30),
        ),
    ]
