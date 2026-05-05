from django.contrib import admin
from django.utils.html import format_html
from django.utils.safestring import mark_safe
from django.shortcuts import redirect
from django.urls import path
from django.utils import timezone
from django.contrib import messages as dj_messages

from .models import Pais, Partido, PerfilUsuario, Prediccion, TorneoConfig
from .scoring import calcular_puntos_partido

admin.site.site_header = 'PollaF 2026 — Administración'
admin.site.site_title  = 'PollaF Admin'
admin.site.index_title = 'Panel de administración'


# ── S: generación HTML separada de la clase admin ───────────────────

def _fila_prediccion_html(p):
    """S: generates one prediction row HTML. No DB access."""
    local = p.partido.equipo_local.nombre if p.partido.equipo_local else p.partido.label_local
    vis   = p.partido.equipo_visitante.nombre if p.partido.equipo_visitante else p.partido.label_visitante
    real  = (f"{p.partido.goles_local_real} – {p.partido.goles_visitante_real}"
             if p.partido.goles_local_real is not None else '—')
    pts   = p.puntos if p.puntos is not None else '—'
    bg    = '#d4edda' if p.puntos == 5 else '#fff3cd' if p.puntos == 2 else '#f8d7da' if p.puntos == 0 else 'transparent'
    color = '#155724' if p.puntos == 5 else '#856404' if p.puntos == 2 else '#721c24' if p.puntos == 0 else '#888'
    return (
        f'<tr style="border-bottom:1px solid #f0f0f0">'
        f'<td style="padding:5px 10px">{local} vs {vis}</td>'
        f'<td style="padding:5px 10px;text-align:center;font-weight:700">{p.goles_local} – {p.goles_visitante}</td>'
        f'<td style="padding:5px 10px;text-align:center">{real}</td>'
        f'<td style="padding:5px 10px;text-align:center;font-weight:800;'
        f'color:{color};background:{bg};border-radius:4px">{pts}</td>'
        f'</tr>'
    )


def _tabla_predicciones_html(rows):
    """S: assembles the full predictions table HTML from pre-fetched rows."""
    header = (
        '<table style="width:100%;border-collapse:collapse;font-size:.85rem">'
        '<thead><tr style="background:#f0faf4">'
        '<th style="padding:6px 10px;text-align:left">Partido</th>'
        '<th style="padding:6px 10px;text-align:center">Mi predicción</th>'
        '<th style="padding:6px 10px;text-align:center">Resultado real</th>'
        '<th style="padding:6px 10px;text-align:center">Puntos</th>'
        '</tr></thead><tbody>'
    )
    return header + ''.join(_fila_prediccion_html(p) for p in rows) + '</tbody></table>'


# ── Países: solo lectura ─────────────────────────────────────────────
@admin.register(Pais)
class PaisAdmin(admin.ModelAdmin):
    list_display  = ['nombre', 'codigo', 'grupo']
    ordering      = ['grupo', 'nombre']
    search_fields = ['nombre']

    def has_add_permission(self, request): return False
    def has_change_permission(self, request, obj=None): return False
    def has_delete_permission(self, request, obj=None): return False


# ── Torneo config: bloqueo ───────────────────────────────────────────
@admin.register(TorneoConfig)
class TorneoConfigAdmin(admin.ModelAdmin):
    change_list_template = 'admin/torneo_config_changelist.html'

    def get_urls(self):
        urls = super().get_urls()
        custom = [
            path('bloquear/', self.admin_site.admin_view(self.bloquear_view), name='bloquear_torneo'),
            path('desbloquear/', self.admin_site.admin_view(self.desbloquear_view), name='desbloquear_torneo'),
        ]
        return custom + urls

    def bloquear_view(self, request):
        cfg = TorneoConfig.get()
        cfg.bloqueado = True
        cfg.bloqueado_en = timezone.now()
        cfg.save()
        dj_messages.success(request, 'Torneo BLOQUEADO. Ya no se aceptan predicciones.')
        return redirect('/admin/core/torneoconfig/')

    def desbloquear_view(self, request):
        cfg = TorneoConfig.get()
        cfg.bloqueado = False
        cfg.save()
        dj_messages.success(request, 'Torneo DESBLOQUEADO. Las predicciones están habilitadas.')
        return redirect('/admin/core/torneoconfig/')

    def changelist_view(self, request, extra_context=None):
        extra_context = extra_context or {}
        extra_context['config'] = TorneoConfig.get()
        return super().changelist_view(request, extra_context=extra_context)

    def has_add_permission(self, request): return False
    def has_delete_permission(self, request, obj=None): return False


# ── Partidos: solo ingresar marcador ────────────────────────────────
@admin.register(Partido)
class PartidoAdmin(admin.ModelAdmin):
    list_display  = ['fase_badge', 'equipos_display', 'resultado_display', 'jugado']
    list_filter   = ['fase', 'jugado']
    search_fields = ['numero']
    list_per_page = 25
    ordering      = ['numero']

    readonly_fields = [
        'numero', 'fase', 'grupo',
        'equipo_local', 'equipo_visitante',
        'label_local', 'label_visitante',
        'info_partido',
    ]

    def get_fields(self, request, obj=None):
        fields = ['info_partido', 'goles_local_real', 'goles_visitante_real']
        if obj and obj.fase != 'GR':
            fields.append('clasificado_real')
        fields.append('jugado')
        return fields

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == 'clasificado_real' and request.resolver_match.kwargs.get('object_id'):
            obj_id = request.resolver_match.kwargs['object_id']
            try:
                partido = Partido.objects.get(pk=obj_id)
                opts = [p.pk for p in [partido.equipo_local, partido.equipo_visitante] if p]
                if opts:
                    kwargs['queryset'] = Pais.objects.filter(pk__in=opts)
            except Partido.DoesNotExist:
                pass
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    def info_partido(self, obj):
        local = obj.equipo_local.nombre if obj.equipo_local else obj.label_local
        vis   = obj.equipo_visitante.nombre if obj.equipo_visitante else obj.label_visitante
        return format_html(
            '<div style="font-size:1.2rem;font-weight:800;padding:8px 0;color:#1a7f4b">'
            '{} <span style="color:#aaa;font-weight:400">vs</span> {}'
            ' &nbsp;<span style="background:#eee;color:#555;font-size:.75rem;'
            'font-weight:600;padding:3px 10px;border-radius:8px">{}</span></div>',
            local, vis, obj.get_fase_display()
        )
    info_partido.short_description = 'Partido'

    def fase_badge(self, obj):
        colores = {
            'GR':'#6c757d','R32':'#0d6efd','R16':'#6610f2',
            'QF':'#fd7e14','SF':'#dc3545','TP':'#198754','FI':'#b8860b',
        }
        c = colores.get(obj.fase, '#999')
        return format_html(
            '<span style="background:{};color:#fff;padding:2px 10px;'
            'border-radius:10px;font-size:.75rem;font-weight:700">{}</span>',
            c, obj.get_fase_display()
        )
    fase_badge.short_description = 'Fase'

    def equipos_display(self, obj):
        local = obj.equipo_local.nombre if obj.equipo_local else obj.label_local
        vis   = obj.equipo_visitante.nombre if obj.equipo_visitante else obj.label_visitante
        return format_html('<b>{}</b> <span style="color:#ccc"> vs </span> <b>{}</b>', local, vis)
    equipos_display.short_description = 'Partido'

    def resultado_display(self, obj):
        if obj.goles_local_real is not None and obj.goles_visitante_real is not None:
            extra = ''
            if obj.fase != 'GR' and obj.goles_local_real == obj.goles_visitante_real and obj.clasificado_real:
                extra = format_html(' <span style="font-size:.75rem;color:#666">(pen. {})</span>',
                                    obj.clasificado_real.nombre)
            return format_html(
                '<span style="background:#d4edda;color:#155724;padding:3px 12px;'
                'border-radius:6px;font-weight:700;font-size:.95rem">{} – {}</span>{}',
                obj.goles_local_real, obj.goles_visitante_real, extra
            )
        return mark_safe('<span style="color:#ddd">—</span>')
    resultado_display.short_description = 'Resultado'

    def has_add_permission(self, request): return False
    def has_delete_permission(self, request, obj=None): return False

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        if obj.jugado:
            n = calcular_puntos_partido(obj)
            self.message_user(request,
                f'✓ Puntos calculados para {n} participantes — Partido #{obj.numero}.')


# ── Participantes ────────────────────────────────────────────────────
@admin.register(PerfilUsuario)
class PerfilAdmin(admin.ModelAdmin):
    list_display    = ['nombre_completo', 'email_display', 'puntos_badge', 'pred_grupos']
    ordering        = ['-puntos_totales']
    search_fields   = ['nombre_completo', 'user__email']
    readonly_fields = ['nombre_completo', 'user', 'puntos_totales', 'tabla_predicciones']
    fields          = ['nombre_completo', 'puntos_totales', 'tabla_predicciones']

    def email_display(self, obj): return obj.user.email
    email_display.short_description = 'Correo'

    def puntos_badge(self, obj):
        return format_html('<b style="font-size:1.1rem;color:#1a7f4b">{}</b>', obj.puntos_totales)
    puntos_badge.short_description = 'Puntos'
    puntos_badge.admin_order_field = 'puntos_totales'

    def pred_grupos(self, obj):
        n = obj.predicciones.filter(partido__fase='GR').count()
        c = '#155724' if n == 72 else '#856404' if n > 0 else '#bbb'
        return format_html('<span style="color:{};font-weight:700">{}/72</span>', c, n)
    pred_grupos.short_description = 'Predicciones grupos'

    def tabla_predicciones(self, obj):
        rows = (obj.predicciones
                .select_related('partido', 'partido__equipo_local', 'partido__equipo_visitante')
                .order_by('partido__numero'))
        return mark_safe(_tabla_predicciones_html(rows))
    tabla_predicciones.short_description = 'Historial de predicciones'

    def has_add_permission(self, request): return False
    def has_delete_permission(self, request, obj=None): return False
    def has_change_permission(self, request, obj=None): return False
