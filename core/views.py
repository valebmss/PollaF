import random
from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.models import User
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db.models import Count

from .forms import RegistroForm, LoginForm
from .models import PerfilUsuario, Partido, Prediccion, Pais, TorneoConfig


def _get_perfil(request):
    """Returns perfil or None. Staff users are redirected to /admin/."""
    try:
        return request.user.perfil
    except Exception:
        return None


def registro(request):
    if request.user.is_authenticated:
        return redirect('core:home')
    form = RegistroForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        email = form.cleaned_data['email']
        nombre = form.cleaned_data['nombre_completo']
        password = form.cleaned_data['password1']
        user = User.objects.create_user(username=email, email=email, password=password)
        PerfilUsuario.objects.create(user=user, nombre_completo=nombre)
        messages.success(request, 'Cuenta creada. Ya puedes ingresar.')
        return redirect('core:login')
    return render(request, 'core/registro.html', {'form': form})


def login_view(request):
    if request.user.is_authenticated:
        if request.user.is_staff:
            return redirect('/admin/')
        return redirect('core:home')
    form = LoginForm(request, data=request.POST or None)
    if request.method == 'POST' and form.is_valid():
        user = form.get_user()
        login(request, user)
        if user.is_staff:
            return redirect('/admin/')
        return redirect('core:home')
    return render(request, 'core/login.html', {'form': form})


def logout_view(request):
    logout(request)
    return redirect('core:login')


@login_required
def home(request):
    if request.user.is_staff:
        return redirect('/admin/')
    perfil = _get_perfil(request)
    if perfil is None:
        messages.error(request, 'Tu cuenta no tiene perfil de participante.')
        return redirect('core:login')

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
        guardados = 0
        for partido in partidos_grupos:
            local_key = f'local_{partido.id}'
            visit_key = f'visitante_{partido.id}'
            if local_key in request.POST and visit_key in request.POST:
                try:
                    gl = int(request.POST[local_key])
                    gv = int(request.POST[visit_key])
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
        if guardados:
            messages.success(request, f'Grupo {request.POST.get("grupo")} guardado.')
        return redirect('core:home')

    predicciones_map = {
        p.partido_id: p
        for p in Prediccion.objects.filter(usuario=perfil, partido__fase='GR')
        .select_related('clasificado_pred')
    }

    context = {
        'perfil': perfil,
        'partidos_grupos': partidos_grupos,
        'predicciones_map': predicciones_map,
        'total_pred': len(predicciones_map),
        'total_jugados': Partido.objects.filter(jugado=True).count(),
        'bloqueado': TorneoConfig.esta_bloqueado(),
    }
    return render(request, 'core/home.html', context)


@login_required
def eliminatorias(request):
    if request.user.is_staff:
        return redirect('/admin/')
    perfil = _get_perfil(request)
    if perfil is None:
        return redirect('core:login')

    if request.method == 'POST':
        if TorneoConfig.esta_bloqueado():
            messages.error(request, 'El torneo está bloqueado. No se pueden modificar predicciones.')
            return redirect('core:eliminatorias')
        fase = request.POST.get('fase')
        if fase:
            partidos_fase = Partido.objects.filter(fase=fase)
            for partido in partidos_fase:
                local_key = f'local_{partido.id}'
                visit_key = f'visitante_{partido.id}'
                clasi_key = f'clasi_{partido.id}'
                if local_key in request.POST and visit_key in request.POST:
                    try:
                        gl = int(request.POST[local_key])
                        gv = int(request.POST[visit_key])
                        if gl < 0 or gv < 0:
                            continue
                        clasi = None
                        clasi_id = request.POST.get(clasi_key)
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
            pred = pred_map.get(partido.id)
            matches.append({
                'partido': partido,
                'local': local,
                'visitante': visitante,
                'pred': pred,
            })
        fases_display.append({
            'clave': clave,
            'nombre': NOMBRES_FASE.get(clave, clave),
            'matches': matches,
        })

    total_pred_gr = Prediccion.objects.filter(usuario=perfil, partido__fase='GR').count()

    context = {
        'fases_display': fases_display,
        'total_pred_gr': total_pred_gr,
        'perfil': perfil,
    }
    return render(request, 'core/eliminatorias.html', context)


@login_required
def mundial(request):
    """Real tournament status page — standings, results, bracket."""
    if request.user.is_staff:
        return redirect('/admin/')

    GRUPOS_LETRAS = list('ABCDEFGHIJKL')

    # Build real group standings
    grupos_data = []
    for letra in GRUPOS_LETRAS:
        partidos = list(
            Partido.objects.filter(fase='GR', grupo=letra)
            .select_related('equipo_local', 'equipo_visitante', 'clasificado_real')
            .order_by('numero')
        )
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

        jugados = [p for p in partidos if p.jugado]
        pendientes = [p for p in partidos if not p.jugado]
        grupos_data.append({
            'letra': letra,
            'tabla': tabla,
            'jugados': jugados,
            'pendientes': pendientes,
        })

    # Elimination results
    fases_elim = ['R32', 'R16', 'QF', 'SF', 'TP', 'FI']
    NOMBRES = dict(Partido.FASES)
    elim_data = []
    for fase in fases_elim:
        partidos = list(
            Partido.objects.filter(fase=fase)
            .select_related('equipo_local', 'equipo_visitante', 'clasificado_real')
            .order_by('numero')
        )
        if any(p.jugado for p in partidos) or fase == 'R32':
            elim_data.append({'fase': fase, 'nombre': NOMBRES[fase], 'partidos': partidos})

    context = {
        'grupos_data': grupos_data,
        'elim_data': elim_data,
        'perfil': _get_perfil(request),
    }
    return render(request, 'core/mundial.html', context)


@login_required
def llenar_prueba(request):
    if request.user.is_staff:
        return redirect('/admin/')
    perfil = _get_perfil(request)
    if perfil is None or request.method != 'POST':
        return redirect('core:home')

    partidos = Partido.objects.filter(fase='GR')
    SCORES = [(1,0),(0,1),(1,1),(2,1),(1,2),(2,0),(0,2),(2,2),(3,1),(1,3),(3,0),(0,3),(0,0),(3,2),(2,3)]
    for partido in partidos:
        gl, gv = random.choice(SCORES)
        Prediccion.objects.update_or_create(
            usuario=perfil, partido=partido,
            defaults={'goles_local': gl, 'goles_visitante': gv}
        )
    messages.success(request, 'Datos de prueba cargados: 72 predicciones de grupos listas.')
    return redirect('core:home')


@login_required
def ranking(request):
    if request.user.is_staff:
        return redirect('/admin/')
    perfil = _get_perfil(request)
    if perfil is None:
        return redirect('core:login')

    perfiles = (
        PerfilUsuario.objects
        .select_related('user')
        .order_by('-puntos_totales', 'nombre_completo')
    )
    pred_counts = {
        p['usuario_id']: p['count']
        for p in Prediccion.objects.values('usuario_id').annotate(count=Count('id'))
    }

    tabla = []
    for i, p in enumerate(perfiles, 1):
        tabla.append({
            'pos': i,
            'nombre': p.nombre_completo,
            'email': p.user.email,
            'puntos': p.puntos_totales,
            'predicciones': pred_counts.get(p.id, 0),
            'es_yo': p.user == request.user,
        })

    context = {
        'tabla': tabla,
        'perfil': perfil,
        'total_jugados': Partido.objects.filter(jugado=True).count(),
    }
    return render(request, 'core/ranking.html', context)
