from django import forms
from .models import Cliente, Prestador, Servicio
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from django.contrib.auth import get_user_model

User = get_user_model()


class CorreoAuthenticationForm(AuthenticationForm):
    username = forms.EmailField(label='Correo electrónico')

    def clean_username(self):
        email = self.cleaned_data['username']
        try:
            user = User.objects.get(email__iexact=email)
        except User.DoesNotExist:
            return email
        except User.MultipleObjectsReturned:
            raise forms.ValidationError(
                'No es posible iniciar sesión con este correo.'
            )
        return user.get_username()


# Formulario de Registro de Usuario (Base de Cuentas)
class RegistroForm(UserCreationForm):
    username = forms.CharField(label='Usuario')
    email = forms.EmailField(label='Correo electrónico')

    class Meta:
        model = User
        fields = ['username', 'email']

    def clean_email(self):
        email = self.cleaned_data['email'].lower()
        if User.objects.filter(
            email__iexact=email
        ).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError('Este correo ya está registrado')
        return email

class EditarUsuarioForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ['username', 'email']

    def clean_email(self):
        email = self.cleaned_data['email'].lower()
        if User.objects.filter(
            email__iexact=email
        ).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError('Este correo ya está registrado')
        return email


# Formulario de Registro de Cliente
class RegistroClienteForm(forms.ModelForm):
    class Meta:
        model = Cliente
        fields = ['nombre', 'direccion_domicilio', 'telefono']

# Formulario de Registro de Prestador
class RegistroPrestadorForm(forms.ModelForm):
    OTRO_SERVICIO = 'otro'

    servicios_ofrecidos = forms.MultipleChoiceField(
        choices=[
            *[
                category
                for category in Servicio.CATEGORIAS
                if category[0] != 'Otros'
            ],
            (OTRO_SERVICIO, 'Otro'),
        ],
        label='Servicios que quieres ofrecer',
        widget=forms.CheckboxSelectMultiple(
            attrs={'class': 'provider-service-options'},
        ),
    )
    especialidad_personalizada = forms.CharField(
        max_length=45,
        required=False,
        label='¿Qué otro servicio ofreces?',
        widget=forms.TextInput(attrs={
            'class': 'provider-form-control',
            'placeholder': 'Escribe el servicio que ofreces',
        }),
    )
    especialidad = forms.CharField(widget=forms.HiddenInput, required=False)

    class Meta:
        model = Prestador
        fields = [
            'servicios_ofrecidos',
            'especialidad',
            'numCertificacion_sanitaria',
            'radio_cobertura',
        ]

    def __init__(self, *args, **kwargs):
        if args and args[0] is not None:
            data = args[0]
            if (
                'servicios_ofrecidos' not in data
                and data.get('especialidad')
            ):
                data = data.copy()
                data.setlist(
                    'servicios_ofrecidos',
                    [data.get('especialidad')],
                )
                args = (data, *args[1:])
        elif kwargs.get('data') is not None:
            data = kwargs['data']
            if (
                'servicios_ofrecidos' not in data
                and data.get('especialidad')
            ):
                data = data.copy()
                data.setlist(
                    'servicios_ofrecidos',
                    [data.get('especialidad')],
                )
                kwargs['data'] = data

        super().__init__(*args, **kwargs)
        if self.instance.pk and not self.is_bound:
            self.initial['servicios_ofrecidos'] = (
                self.instance.servicios_ofrecidos
                or [self.instance.especialidad]
            )

        self.fields['numCertificacion_sanitaria'].label = (
            'Certificación sanitaria'
        )
        self.fields['numCertificacion_sanitaria'].widget.attrs.update({
            'class': 'provider-form-control',
            'placeholder': 'Número de certificación',
        })
        self.fields['radio_cobertura'].label = 'Comuna o sector'
        self.fields['radio_cobertura'].widget.attrs.update({
            'class': 'provider-form-control',
            'placeholder': 'Ej. Copiapó',
        })

    def clean(self):
        cleaned_data = super().clean()
        selected_services = cleaned_data.get('servicios_ofrecidos', [])
        offered_services = [
            service
            for service in selected_services
            if service != self.OTRO_SERVICIO
        ]

        if self.OTRO_SERVICIO in selected_services:
            especialidad_personalizada = cleaned_data.get(
                'especialidad_personalizada', ''
            ).strip()
            if not especialidad_personalizada:
                self.add_error(
                    'especialidad_personalizada',
                    'Escribe el servicio que ofreces.',
                )
            else:
                offered_services.append(especialidad_personalizada)

        if offered_services:
            cleaned_data['servicios_ofrecidos'] = offered_services
            cleaned_data['especialidad'] = offered_services[0]

        return cleaned_data


class ServicioForm(forms.ModelForm):
    DURACIONES = (
        (30, '30 min'),
        (45, '45 min'),
        (60, '60 min'),
        (90, '90 min'),
        (120, '120 min'),
    )
    categoria = forms.ChoiceField(
        choices=[('', 'Selecciona una categoría'), *Servicio.CATEGORIAS],
        label='Categoría',
        widget=forms.Select(attrs={'class': 'provider-form-control'}),
        error_messages={
            'required': 'Selecciona una categoría.',
            'invalid_choice': 'Selecciona una categoría válida.',
        },
    )
    nombre = forms.CharField(
        max_length=45,
        label='Nombre del servicio',
        widget=forms.TextInput(attrs={
            'class': 'provider-form-control',
            'placeholder': 'Ej. Manicure permanente',
        }),
        error_messages={'required': 'Ingresa el nombre del servicio.'},
    )
    descripcion = forms.CharField(
        max_length=500,
        label='Descripción del servicio',
        widget=forms.Textarea(attrs={
            'class': 'provider-form-control',
            'rows': 3,
            'placeholder': 'Describe qué incluye el servicio.',
        }),
        error_messages={'required': 'Ingresa una descripción del servicio.'},
    )
    duracion = forms.TypedChoiceField(
        choices=DURACIONES,
        coerce=int,
        label='Duración',
        widget=forms.Select(attrs={'class': 'provider-form-control'}),
        error_messages={
            'required': 'Selecciona una duración.',
            'invalid_choice': 'Selecciona una duración válida.',
        },
    )
    precio_base = forms.IntegerField(
        min_value=1000,
        max_value=2147483647,
        label='Precio (CLP)',
        widget=forms.NumberInput(attrs={
            'class': 'provider-form-control',
            'min': 1000,
            'step': 1000,
            'placeholder': '25.000',
        }),
        error_messages={
            'required': 'Ingresa el precio del servicio.',
            'min_value': 'El precio mínimo es $1.000 CLP.',
            'max_value': 'El precio supera el máximo permitido.',
            'invalid': 'Ingresa un precio válido en pesos chilenos.',
        },
    )

    class Meta:
        model = Servicio
        fields = ['categoria', 'nombre', 'descripcion', 'duracion', 'precio_base']

    def clean_nombre(self):
        nombre = self.cleaned_data['nombre'].strip()
        if not nombre:
            raise forms.ValidationError('Ingresa el nombre del servicio.')
        return nombre

    def clean_descripcion(self):
        descripcion = self.cleaned_data['descripcion'].strip()
        if not descripcion:
            raise forms.ValidationError('Ingresa una descripción del servicio.')
        return descripcion
