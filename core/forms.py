from django import forms
from django.contrib.auth.models import User
from django.contrib.auth.forms import AuthenticationForm

DOMINIO = 'usa.edu.co'


class RegistroForm(forms.Form):
    nombre_completo = forms.CharField(max_length=200, label='Nombre completo')
    email = forms.EmailField(label='Correo institucional')
    password1 = forms.CharField(widget=forms.PasswordInput, label='Contraseña')
    password2 = forms.CharField(widget=forms.PasswordInput, label='Confirmar contraseña')

    def clean_email(self):
        email = self.cleaned_data['email'].lower()
        if not email.endswith(f'@{DOMINIO}'):
            raise forms.ValidationError(f'Solo se permiten correos @{DOMINIO}')
        if User.objects.filter(email=email).exists():
            raise forms.ValidationError('Ya existe una cuenta con este correo.')
        return email

    def clean(self):
        data = super().clean()
        p1 = data.get('password1')
        p2 = data.get('password2')
        if p1 and p2 and p1 != p2:
            raise forms.ValidationError('Las contraseñas no coinciden.')
        return data


class LoginForm(AuthenticationForm):
    username = forms.EmailField(label='Correo institucional')
