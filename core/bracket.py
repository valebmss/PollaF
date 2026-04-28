"""
Cascade bracket computation for PollaF 2026.
Derives predicted teams for each elimination match from user's group predictions.
"""
from .models import Partido, Prediccion, ClasificacionManualGrupo, TerceroManual


GRUPOS_LETRAS = list('ABCDEFGHIJKL')


def _clasificados_grupo_auto(perfil, letra):
    """Returns list of Pais sorted by predicted standing [1st, 2nd, 3rd, 4th]."""
    partidos = list(
        Partido.objects.filter(fase='GR', grupo=letra)
        .select_related('equipo_local', 'equipo_visitante')
    )
    preds = {
        p.partido_id: p
        for p in Prediccion.objects.filter(usuario=perfil, partido__in=partidos)
    }

    equipos = {}
    for partido in partidos:
        for eq in [partido.equipo_local, partido.equipo_visitante]:
            if eq and eq.id not in equipos:
                equipos[eq.id] = {'pais': eq, 'pts': 0, 'gd': 0, 'gf': 0, 'wins': 0}

    for partido in partidos:
        pred = preds.get(partido.id)
        if not pred or not partido.equipo_local or not partido.equipo_visitante:
            continue
        gl, gv = pred.goles_local, pred.goles_visitante
        lid, vid = partido.equipo_local.id, partido.equipo_visitante.id
        equipos[lid]['gf'] += gl
        equipos[lid]['gd'] += gl - gv
        equipos[vid]['gf'] += gv
        equipos[vid]['gd'] += gv - gl
        if gl > gv:
            equipos[lid]['pts'] += 3
            equipos[lid]['wins'] += 1
        elif gv > gl:
            equipos[vid]['pts'] += 3
            equipos[vid]['wins'] += 1
        else:
            equipos[lid]['pts'] += 1
            equipos[vid]['pts'] += 1

    sorted_teams = sorted(
        equipos.values(),
        key=lambda x: (-x['pts'], -x['gd'], -x['gf'], -x['wins'])
    )
    return [s['pais'] for s in sorted_teams]


def _clasificados_grupo(perfil, letra):
    manual = (
        ClasificacionManualGrupo.objects
        .filter(usuario=perfil, grupo=letra)
        .select_related('primero', 'segundo', 'tercero', 'cuarto')
        .first()
    )

    if manual:
        return [manual.primero, manual.segundo, manual.tercero, manual.cuarto]

    return _clasificados_grupo_auto(perfil, letra)


def _tercero_stats(perfil, equipo, letra):
    """Returns stats dict for a third-place team in their group."""
    partidos = list(Partido.objects.filter(fase='GR', grupo=letra))
    preds = {p.partido_id: p for p in Prediccion.objects.filter(usuario=perfil, partido__in=partidos)}
    pts, gd, gf, wins = 0, 0, 0, 0
    for partido in partidos:
        pred = preds.get(partido.id)
        if not pred or not partido.equipo_local or not partido.equipo_visitante:
            continue
        gl, gv = pred.goles_local, pred.goles_visitante
        if partido.equipo_local == equipo:
            gf += gl; gd += gl - gv
            if gl > gv: pts += 3; wins += 1
            elif gl == gv: pts += 1
        elif partido.equipo_visitante == equipo:
            gf += gv; gd += gv - gl
            if gv > gl: pts += 3; wins += 1
            elif gv == gl: pts += 1
    return {'pts': pts, 'gd': gd, 'gf': gf, 'wins': wins}


def _label_to_team(label, clasificados, terceros_map, partido_numero):
    if label.startswith('1ro Grupo '):
        letra = label[-1]
        equipos = clasificados.get(letra, [])
        return equipos[0] if equipos else None
    if label.startswith('2do Grupo '):
        letra = label[-1]
        equipos = clasificados.get(letra, [])
        return equipos[1] if len(equipos) >= 2 else None
    if label.startswith('Mejor 3ro'):
        return terceros_map.get(partido_numero)
    return None


def _predict_outcome(local, visitante, pred):
    """Returns (winner, loser). None if prediction missing or draw with no clasificado."""
    if not pred or local is None or visitante is None:
        return None, None
    gl, gv = pred.goles_local, pred.goles_visitante
    if gl > gv:
        return local, visitante
    if gv > gl:
        return visitante, local
    # Draw in elimination: winner is quien clasificó
    winner = pred.clasificado_pred
    if winner is None:
        return None, None
    loser = visitante if winner.id == local.id else local
    return winner, loser


def get_predicted_bracket(perfil):
    """
    Computes the full predicted bracket from user predictions.

    Returns:
        teams: dict {partido_id: (local_pais|None, visitante_pais|None)}
        pred_map: dict {partido_id: Prediccion}
        fases: dict of phase keys → list of Partido
    """
    from .terceros import asignar_terceros

    # ── Group standings ──────────────────────────────────────────────
    clasificados = {}
    for letra in GRUPOS_LETRAS:
        clasificados[letra] = _clasificados_grupo(perfil, letra)

    # ── Best 8 third-place teams ─────────────────────────────────────
    terceros_info = []
    for letra in GRUPOS_LETRAS:
        equipos = clasificados.get(letra, [])
        if len(equipos) >= 3:
            equipo = equipos[2]
            stats = _tercero_stats(perfil, equipo, letra)
            terceros_info.append({'pais': equipo, 'grupo': letra, **stats})

    terceros_manuales = list(
    TerceroManual.objects
        .filter(usuario=perfil)
        .select_related('pais')
        .order_by('posicion')
    )

    if terceros_manuales:
        mejores_8 = [
            {'pais': t.pais, 'grupo': t.grupo}
            for t in terceros_manuales[:8]
        ]
    else:
        terceros_info.sort(key=lambda x: (-x['pts'], -x['gd'], -x['gf'], -x['wins']))
        mejores_8 = terceros_info[:8]

    grupos_8 = {t['grupo'] for t in mejores_8}
    terceros_pais = {t['grupo']: t['pais'] for t in mejores_8}

    # Assign to R32 slots
    asignacion = asignar_terceros(grupos_8)  # {partido_num: letra_grupo}
    terceros_map = {num: terceros_pais[letra] for num, letra in asignacion.items() if letra in terceros_pais}

    # ── Load all elimination matches ─────────────────────────────────
    r32 = list(Partido.objects.filter(fase='R32').order_by('numero'))
    r16 = list(Partido.objects.filter(fase='R16').order_by('numero'))
    qf  = list(Partido.objects.filter(fase='QF').order_by('numero'))
    sf  = list(Partido.objects.filter(fase='SF').order_by('numero'))
    tp  = list(Partido.objects.filter(fase='TP').order_by('numero'))
    fi  = list(Partido.objects.filter(fase='FI').order_by('numero'))

    all_elim = r32 + r16 + qf + sf + tp + fi
    pred_map = {
        p.partido_id: p
        for p in Prediccion.objects.filter(usuario=perfil, partido__in=all_elim)
        .select_related('clasificado_pred')
    }

    teams   = {}  # partido_id -> (local, visitante)
    winners = {}  # partido_id -> winner pais
    losers  = {}  # partido_id -> loser pais

    # R32
    for partido in r32:
        local = _label_to_team(partido.label_local, clasificados, terceros_map, partido.numero)
        vis   = _label_to_team(partido.label_visitante, clasificados, terceros_map, partido.numero)
        teams[partido.id] = (local, vis)
        w, l = _predict_outcome(local, vis, pred_map.get(partido.id))
        winners[partido.id] = w
        losers[partido.id]  = l

    # R16: winner of R32[0] vs winner of R32[1], etc.
    for i, partido in enumerate(r16):
        local = winners.get(r32[i * 2].id)     if i * 2     < len(r32) else None
        vis   = winners.get(r32[i * 2 + 1].id) if i * 2 + 1 < len(r32) else None
        teams[partido.id] = (local, vis)
        w, l = _predict_outcome(local, vis, pred_map.get(partido.id))
        winners[partido.id] = w
        losers[partido.id]  = l

    # QF: winner of R16 pairs
    for i, partido in enumerate(qf):
        local = winners.get(r16[i * 2].id)     if i * 2     < len(r16) else None
        vis   = winners.get(r16[i * 2 + 1].id) if i * 2 + 1 < len(r16) else None
        teams[partido.id] = (local, vis)
        w, l = _predict_outcome(local, vis, pred_map.get(partido.id))
        winners[partido.id] = w
        losers[partido.id]  = l

    # SF: winner of QF pairs
    for i, partido in enumerate(sf):
        local = winners.get(qf[i * 2].id)     if i * 2     < len(qf) else None
        vis   = winners.get(qf[i * 2 + 1].id) if i * 2 + 1 < len(qf) else None
        teams[partido.id] = (local, vis)
        w, l = _predict_outcome(local, vis, pred_map.get(partido.id))
        winners[partido.id] = w
        losers[partido.id]  = l

    # Tercer puesto: SF losers
    if tp and len(sf) >= 2:
        local = losers.get(sf[0].id)
        vis   = losers.get(sf[1].id)
        teams[tp[0].id] = (local, vis)

    # Final: SF winners
    if fi and len(sf) >= 2:
        local = winners.get(sf[0].id)
        vis   = winners.get(sf[1].id)
        teams[fi[0].id] = (local, vis)

    fases = {'r32': r32, 'r16': r16, 'qf': qf, 'sf': sf, 'tp': tp, 'fi': fi}
    return teams, pred_map, fases
