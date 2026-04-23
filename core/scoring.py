from django.db.models import Sum
from .models import Prediccion, PerfilUsuario


def calcular_puntos_partido(partido):
    """
    Calculates points for every prediction of a played match.
    Group matches: 5 exact score, 2 correct result.
    Knockout draws: advancing team counts as "the result".
    """
    if (not partido.jugado
            or partido.goles_local_real is None
            or partido.goles_visitante_real is None):
        return 0

    gl_r = partido.goles_local_real
    gv_r = partido.goles_visitante_real
    es_grupo = partido.fase == 'GR'

    # For knockouts with a draw, the real winner is clasificado_real
    if not es_grupo and gl_r == gv_r:
        ganador_real = partido.clasificado_real  # Pais or None
    elif gl_r > gv_r:
        ganador_real = partido.equipo_local
    else:
        ganador_real = partido.equipo_visitante

    preds = list(Prediccion.objects.filter(partido=partido).select_related(
        'usuario', 'clasificado_pred'))
    usuarios_afectados = set()

    for pred in preds:
        gl_p = pred.goles_local
        gv_p = pred.goles_visitante

        if es_grupo:
            # Group match scoring
            if gl_p == gl_r and gv_p == gv_r:
                pts = 5
            else:
                if gl_p > gv_p:
                    res_p = 'L'
                elif gv_p > gl_p:
                    res_p = 'V'
                else:
                    res_p = 'E'
                if gl_r > gv_r:
                    res_r = 'L'
                elif gv_r > gl_r:
                    res_r = 'V'
                else:
                    res_r = 'E'
                pts = 2 if res_p == res_r else 0
        else:
            # Knockout match scoring
            # Determine predicted winner
            if gl_p > gv_p:
                ganador_pred = partido.equipo_local
            elif gv_p > gl_p:
                ganador_pred = partido.equipo_visitante
            else:
                ganador_pred = pred.clasificado_pred  # user's choice for draw

            exact_score = (gl_p == gl_r and gv_p == gv_r)
            correct_winner = (
                ganador_pred is not None
                and ganador_real is not None
                and ganador_pred.id == ganador_real.id
            )

            if exact_score and correct_winner:
                pts = 5
            elif correct_winner:
                pts = 2
            else:
                pts = 0

        pred.puntos = pts
        pred.save(update_fields=['puntos'])
        usuarios_afectados.add(pred.usuario_id)

    # Recalculate totals
    for uid in usuarios_afectados:
        total = (
            Prediccion.objects
            .filter(usuario_id=uid, puntos__isnull=False)
            .aggregate(t=Sum('puntos'))['t'] or 0
        )
        PerfilUsuario.objects.filter(id=uid).update(puntos_totales=total)

    return len(preds)
