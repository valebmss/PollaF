import random
import functools
from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.models import User
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Count

from .forms import RegistroForm, LoginForm
from .models import PerfilUsuario, Partido, Prediccion, Pais, TorneoConfig, ClasificacionManualGrupo, TerceroManual


# ── S: helper de perfil ───────────────────────────────────────────────

def _get_perfil(request):
    try:
        return request.user.perfil
    except Exception:
        return None


# ── S: decorator que centraliza el guard staff + perfil ──────────────
# Elimina el bloque repetido en 6 vistas distintas.

def _requiere_participante(view_func):
    @functools.wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if request.user.is_staff:
            return redirect('/admin/')
        perfil = _get_perfil(request)
        if perfil is None:
            messages.error(request, 'Tu cuenta no tiene perfil de participante.')
            return redirect('core:login')
        return view_func(request, *args, perfil=perfil, **kwargs)
    return wrapper


# ── S: lógica POST extraída de las vistas ────────────────────────────

def _guardar_predicciones_grupo(perfil, partidos, post_data):
    """S: only saves group stage predictions. Returns count saved."""
    guardados = 0
    for partido in partidos:
        local_key = f'local_{partido.id}'
        visit_key = f'visitante_{partido.id}'
        if local_key not in post_data or visit_key not in post_data:
            continue
        try:
            gl = int(post_data[local_key])
            gv = int(post_data[visit_key])
            if gl < 0 or gv < 0:
                continue
            Prediccion.objects.update_or_create(
                usuario=perfil,
                partido=partido,
                defaults={'goles_local': gl, 'goles_visitante': gv}
            )
            guardados += 1
        except (ValueError, TypeError):
            pass
    return guardados


def _guardar_predicciones_eliminatorias(perfil, fase, post_data):
    """S: only saves knockout predictions for a given phase."""
    for partido in Partido.objects.filter(fase=fase):
        local_key = f'local_{partido.id}'
        visit_key = f'visitante_{partido.id}'
        if local_key not in post_data or visit_key not in post_data:
            continue
        try:
            gl = int(post_data[local_key])
            gv = int(post_data[visit_key])
            if gl < 0 or gv < 0:
                continue
            clasi    = None
            clasi_id = post_data.get(f'clasi_{partido.id}')
            if clasi_id:
                try:
                    clasi = Pais.objects.get(id=int(clasi_id))
                except (Pais.DoesNotExist, ValueError):
                    pass
            Prediccion.objects.update_or_create(
                usuario=perfil,
                partido=partido,
                defaults={
                    'goles_local': gl,
                    'goles_visitante': gv,
                    'clasificado_pred': clasi,
                }
            )
        except (ValueError, TypeError):
            pass


def _construir_standings_grupo(partidos):
    """S: builds real group standings from actual results. No DB access."""
    equipos = {}
    for partido in partidos:
        for eq in [partido.equipo_local, partido.equipo_visitante]:
            if eq and eq.id not in equipos:
                equipos[eq.id] = {
                    'pais': eq, 'pj': 0, 'pg': 0, 'pe': 0, 'pp': 0,
                    'gf': 0, 'gc': 0, 'pts': 0
                }
        if not partido.jugado:
            continue
        gl, gv = partido.goles_local_real, partido.goles_visitante_real
        if gl is None or gv is None:
            continue
        lid = partido.equipo_local.id if partido.equipo_local else None
        vid = partido.equipo_visitante.id if partido.equipo_visitante else None
        if lid and vid:
            equipos[lid]['pj'] += 1; equipos[vid]['pj'] += 1
            equipos[lid]['gf'] += gl; equipos[lid]['gc'] += gv
            equipos[vid]['gf'] += gv; equipos[vid]['gc'] += gl
            if gl > gv:
                equipos[lid]['pg'] += 1; equipos[lid]['pts'] += 3; equipos[vid]['pp'] += 1
            elif gv > gl:
                equipos[vid]['pg'] += 1; equipos[vid]['pts'] += 3; equipos[lid]['pp'] += 1
            else:
                equipos[lid]['pe'] += 1; equipos[lid]['pts'] += 1
                equipos[vid]['pe'] += 1; equipos[vid]['pts'] += 1

    tabla = sorted(
        equipos.values(),
        key=lambda x: (-x['pts'], -(x['gf'] - x['gc']), -x['gf'])
    )
    for i, t in enumerate(tabla):
        t['dg'] = t['gf'] - t['gc']
        t['pos'] = i + 1
    return tabla


# ── Vistas públicas ───────────────────────────────────────────────────

def registro(request):
    if request.user.is_authenticated:
        return redirect('core:home')
    form = RegistroForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        email  = form.cleaned_data['email']
        nombre = form.cleaned_data['nombre_completo']
        user   = User.objects.create_user(username=email, email=email,
                                          password=form.cleaned_data['password1'])
        PerfilUsuario.objects.create(user=user, nombre_completo=nombre)
        messages.success(request, 'Cuenta creada. Ya puedes ingresar.')
        return redirect('core:login')
    return render(request, 'core/registro.html', {'form': form})


def login_view(request):
    if request.user.is_authenticated:
        return redirect('/admin/' if request.user.is_staff else 'core:home')
    form = LoginForm(request, data=request.POST or None)
    if request.method == 'POST' and form.is_valid():
        user = form.get_user()
        login(request, user)
        return redirect('/admin/' if user.is_staff else 'core:home')
    return render(request, 'core/login.html', {'form': form})


def logout_view(request):
    logout(request)
    return redirect('core:login')


# ── Vistas de participante ────────────────────────────────────────────

@login_required
@_requiere_participante
def home(request, perfil):
    partidos_grupos = (
        Partido.objects
        .filter(fase='GR')
        .select_related('equipo_local', 'equipo_visitante')
        .order_by('grupo', 'numero')
    )

    if request.method == 'POST' and request.POST.get('accion') == 'guardar_grupo':
        if TorneoConfig.esta_bloqueado():
            messages.error(request, 'El torneo está bloqueado.')
            return redirect('core:home')
        guardados = _guardar_predicciones_grupo(perfil, partidos_grupos, request.POST)
        if guardados:
            messages.success(request, f'Grupo {request.POST.get("grupo")} guardado.')
        return redirect('core:home')

    predicciones_map = {
        p.partido_id: p
        for p in Prediccion.objects.filter(usuario=perfil, partido__fase='GR')
        .select_related('clasificado_pred')
    }
    context = {
        'perfil':         perfil,
        'partidos_grupos': partidos_grupos,
        'predicciones_map': predicciones_map,
        'total_pred':     len(predicciones_map),
        'total_jugados':  Partido.objects.filter(jugado=True).count(),
        'bloqueado':      TorneoConfig.esta_bloqueado(),
    }
    return render(request, 'core/home.html', context)


@login_required
@_requiere_participante
def eliminatorias(request, perfil):
    if request.method == 'POST':
        if TorneoConfig.esta_bloqueado():
            messages.error(request, 'El torneo está bloqueado. No se pueden modificar predicciones.')
            return redirect('core:eliminatorias')
        fase = request.POST.get('fase')
        if fase:
            _guardar_predicciones_eliminatorias(perfil, fase, request.POST)
            messages.success(request, 'Predicciones eliminatorias guardadas.')
        return redirect('core:eliminatorias')

    from .bracket import get_predicted_bracket
    teams, pred_map, fases = get_predicted_bracket(perfil)

    NOMBRES_FASE = dict(Partido.FASES)
    fases_display = []
    for clave, partidos_list in [
        ('R32', fases['r32']), ('R16', fases['r16']),
        ('QF',  fases['qf']),  ('SF',  fases['sf']),
        ('TP',  fases['tp']),  ('FI',  fases['fi']),
    ]:
        matches = []
        for partido in partidos_list:
            local, visitante = teams.get(partido.id, (None, None))
            matches.append({
                'partido':   partido,
                'local':     local,
                'visitante': visitante,
                'pred':      pred_map.get(partido.id),
            })
        fases_display.append({
            'clave':   clave,
            'nombre':  NOMBRES_FASE.get(clave, clave),
            'matches': matches,
        })

    context = {
        'fases_display':  fases_display,
        'total_pred_gr':  Prediccion.objects.filter(usuario=perfil, partido__fase='GR').count(),
        'perfil':         perfil,
    }
    return render(request, 'core/eliminatorias.html', context)


@login_required
def mundial(request):
    if request.user.is_staff:
        return redirect('/admin/')

    grupos_data = []
    for letra in list('ABCDEFGHIJKL'):
        partidos = list(
            Partido.objects.filter(fase='GR', grupo=letra)
            .select_related('equipo_local', 'equipo_visitante', 'clasificado_real')
            .order_by('numero')
        )
        tabla = _construir_standings_grupo(partidos)
        grupos_data.append({
            'letra':      letra,
            'tabla':      tabla,
            'jugados':    [p for p in partidos if p.jugado],
            'pendientes': [p for p in partidos if not p.jugado],
        })

    NOMBRES   = dict(Partido.FASES)
    elim_data = []
    for fase in ['R32', 'R16', 'QF', 'SF', 'TP', 'FI']:
        partidos = list(
            Partido.objects.filter(fase=fase)
            .select_related('equipo_local', 'equipo_visitante', 'clasificado_real')
            .order_by('numero')
        )
        if any(p.jugado for p in partidos) or fase == 'R32':
            elim_data.append({'fase': fase, 'nombre': NOMBRES[fase], 'partidos': partidos})

    context = {
        'grupos_data': grupos_data,
        'elim_data':   elim_data,
        'perfil':      _get_perfil(request),
    }
    return render(request, 'core/mundial.html', context)


@login_required
@_requiere_participante
def llenar_prueba(request, perfil):
    if request.method != 'POST':
        return redirect('core:home')
    SCORES = [(1,0),(0,1),(1,1),(2,1),(1,2),(2,0),(0,2),(2,2),
              (3,1),(1,3),(3,0),(0,3),(0,0),(3,2),(2,3)]
    for partido in Partido.objects.filter(fase='GR'):
        gl, gv = random.choice(SCORES)
        Prediccion.objects.update_or_create(
            usuario=perfil, partido=partido,
            defaults={'goles_local': gl, 'goles_visitante': gv}
        )
    messages.success(request, 'Datos de prueba cargados: 72 predicciones de grupos listas.')
    return redirect('core:home')


@login_required
@_requiere_participante
def clasificacion_manual(request, perfil):
    if TorneoConfig.esta_bloqueado():
        messages.error(request, 'El torneo está bloqueado. No se pueden modificar clasificaciones.')
        return redirect('core:eliminatorias')

    grupos = list('ABCDEFGHIJKL')

    if request.method == 'POST':
        accion = request.POST.get('accion')

        if accion in ['guardar_grupos', 'guardar_todo']:
            for letra in grupos:
                ids = [
                    request.POST.get(f'{letra}_primero'),
                    request.POST.get(f'{letra}_segundo'),
                    request.POST.get(f'{letra}_tercero'),
                    request.POST.get(f'{letra}_cuarto'),
                ]
                if not all(ids):
                    continue
                if len(set(ids)) != 4:
                    messages.error(request, f'Grupo {letra}: no puedes repetir equipos.')
                    return redirect('core:clasificacion_manual')
                try:
                    primero, segundo, tercero, cuarto = [Pais.objects.get(id=int(x)) for x in ids]
                except (Pais.DoesNotExist, ValueError):
                    continue
                ClasificacionManualGrupo.objects.update_or_create(
                    usuario=perfil, grupo=letra,
                    defaults={
                        'primero': primero, 'segundo': segundo,
                        'tercero': tercero, 'cuarto': cuarto,
                    }
                )
            TerceroManual.objects.filter(usuario=perfil).delete()
            messages.success(request, 'Clasificación manual de grupos guardada.')
            return redirect('core:clasificacion_manual')

        if accion == 'guardar_terceros':
            TerceroManual.objects.filter(usuario=perfil).delete()
            usados = set()
            for pos in range(1, 13):
                pais_id = request.POST.get(f'tercero_{pos}')
                if not pais_id:
                    continue
                if pais_id in usados:
                    messages.error(request, 'No puedes repetir equipos en la tabla de terceros.')
                    return redirect('core:clasificacion_manual')
                try:
                    pais = Pais.objects.get(id=int(pais_id))
                except (Pais.DoesNotExist, ValueError):
                    continue
                usados.add(pais_id)
                TerceroManual.objects.create(
                    usuario=perfil, posicion=pos, pais=pais, grupo=pais.grupo)
            messages.success(request, 'Orden manual de terceros guardado.')
            return redirect('core:eliminatorias')

        if accion == 'restaurar_auto':
            ClasificacionManualGrupo.objects.filter(usuario=perfil).delete()
            TerceroManual.objects.filter(usuario=perfil).delete()
            messages.success(request, 'Clasificación restaurada al cálculo automático.')
            return redirect('core:clasificacion_manual')

    from .bracket import _clasificados_grupo

    grupos_data          = []
    terceros_candidatos  = []
    for letra in grupos:
        equipos_grupo = list(Pais.objects.filter(grupo=letra).order_by('nombre'))
        orden_actual  = _clasificados_grupo(perfil, letra)
        manual        = ClasificacionManualGrupo.objects.filter(usuario=perfil, grupo=letra).first()
        if len(orden_actual) >= 3:
            terceros_candidatos.append(orden_actual[2])
        grupos_data.append({
            'letra':        letra,
            'equipos':      equipos_grupo,
            'orden_actual': orden_actual,
            'manual':       manual,
        })

    terceros_manual = {
        t.posicion: t.pais
        for t in TerceroManual.objects.filter(usuario=perfil).select_related('pais')
    }

    context = {
        'perfil':               perfil,
        'grupos_data':          grupos_data,
        'terceros_candidatos':  terceros_candidatos,
        'terceros_manual':      terceros_manual,
        'posiciones_terceros':  range(1, 13),
    }
    return render(request, 'core/clasificacion_manual.html', context)


@login_required
@_requiere_participante
def ranking(request, perfil):
    perfiles = (
        PerfilUsuario.objects
        .select_related('user')
        .order_by('-puntos_totales', 'nombre_completo')
    )
    pred_counts = {
        p['usuario_id']: p['count']
        for p in Prediccion.objects.values('usuario_id').annotate(count=Count('id'))
    }
    tabla = [
        {
            'pos':          i,
            'nombre':       p.nombre_completo,
            'email':        p.user.email,
            'puntos':       p.puntos_totales,
            'predicciones': pred_counts.get(p.id, 0),
            'es_yo':        p.user == request.user,
        }
        for i, p in enumerate(perfiles, 1)
    ]
    context = {
        'tabla':         tabla,
        'perfil':        perfil,
        'total_jugados': Partido.objects.filter(jugado=True).count(),
    }
    return render(request, 'core/ranking.html', context)
