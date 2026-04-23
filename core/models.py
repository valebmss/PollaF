from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone


class Pais(models.Model):
    nombre = models.CharField(max_length=100)
    codigo = models.CharField(max_length=3, unique=True)
    grupo = models.CharField(max_length=1)  # A-L

    class Meta:
        verbose_name_plural = "Paises"
        ordering = ['grupo', 'nombre']

    def __str__(self):
        return f"{self.nombre} (Grupo {self.grupo})"


class Partido(models.Model):
    FASES = [
        ('GR', 'Fase de Grupos'),
        ('R32', 'Ronda de 32'),
        ('R16', 'Octavos de Final'),
        ('QF', 'Cuartos de Final'),
        ('SF', 'Semifinal'),
        ('TP', 'Tercer Puesto'),
        ('FI', 'Final'),
    ]

    numero = models.PositiveSmallIntegerField(unique=True)
    fase = models.CharField(max_length=3, choices=FASES)
    grupo = models.CharField(max_length=1, blank=True)  # solo para fase de grupos

    # Equipos reales (conocidos en grupos, se llenan al avanzar en eliminatorias)
    equipo_local = models.ForeignKey(
        Pais, null=True, blank=True,
        on_delete=models.SET_NULL, related_name='partidos_local'
    )
    equipo_visitante = models.ForeignKey(
        Pais, null=True, blank=True,
        on_delete=models.SET_NULL, related_name='partidos_visitante'
    )

    # Etiqueta descriptiva del slot (ej: "Ganador Grupo A", "Mejor 3ro C/D/E")
    label_local = models.CharField(max_length=60, blank=True)
    label_visitante = models.CharField(max_length=60, blank=True)

    # Resultado real (lo llena el admin cuando se juega)
    goles_local_real = models.SmallIntegerField(null=True, blank=True)
    goles_visitante_real = models.SmallIntegerField(null=True, blank=True)
    # Solo para fases eliminatorias cuando el marcador real es empate:
    clasificado_real = models.ForeignKey(
        'Pais', null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='clasificaciones_reales'
    )
    jugado = models.BooleanField(default=False)

    class Meta:
        ordering = ['numero']

    def __str__(self):
        local = self.equipo_local.nombre if self.equipo_local else self.label_local
        visitante = self.equipo_visitante.nombre if self.equipo_visitante else self.label_visitante
        return f"#{self.numero} [{self.get_fase_display()}] {local} vs {visitante}"


class TorneoConfig(models.Model):
    """Singleton que controla si el torneo está bloqueado (no más predicciones)."""
    bloqueado = models.BooleanField(default=False)
    bloqueado_en = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = 'Configuración del torneo'

    @classmethod
    def get(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj

    @classmethod
    def esta_bloqueado(cls):
        return cls.get().bloqueado

    def __str__(self):
        return 'BLOQUEADO — no se aceptan predicciones' if self.bloqueado else 'ABIERTO — predicciones habilitadas'


class PerfilUsuario(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='perfil')
    nombre_completo = models.CharField(max_length=200)
    puntos_totales = models.IntegerField(default=0)

    def __str__(self):
        return self.nombre_completo


class Prediccion(models.Model):
    usuario = models.ForeignKey(
        PerfilUsuario, on_delete=models.CASCADE, related_name='predicciones'
    )
    partido = models.ForeignKey(
        Partido, on_delete=models.CASCADE, related_name='predicciones'
    )
    goles_local = models.SmallIntegerField()
    goles_visitante = models.SmallIntegerField()
    # Solo para fases eliminatorias cuando el marcador predicho es empate:
    # el usuario elige quién clasifica en penales
    clasificado_pred = models.ForeignKey(
        Pais, null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='clasificaciones_pred'
    )
    # Se llena automáticamente cuando el partido se juega
    puntos = models.SmallIntegerField(null=True, blank=True)

    class Meta:
        unique_together = ('usuario', 'partido')

    def __str__(self):
        return f"{self.usuario} | {self.partido} → {self.goles_local}-{self.goles_visitante}"
