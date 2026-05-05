from django.db.models import Sum
from .models import Prediccion, PerfilUsuario


# ── S: helper puro ───────────────────────────────────────────────────

def _resultado(gl, gv):
    """Returns 'L', 'E', or 'V' for a given score."""
    if gl > gv:
        return 'L'
    if gv > gl:
        return 'V'
    return 'E'


# ── O: estrategias de puntuación ─────────────────────────────────────

class EstrategiaGrupo:
    """Scoring for group stage: 5 exact, 2 correct result, 0 wrong."""

    def calcular(self, gl_p, gv_p, gl_r, gv_r, ganador_pred=None, ganador_real=None):
        if gl_p == gl_r and gv_p == gv_r:
            return 5
        return 2 if _resultado(gl_p, gv_p) == _resultado(gl_r, gv_r) else 0


class EstrategiaEliminatoria:
    """Scoring for knockout: 5 exact+winner, 2 correct winner, 0 wrong."""

    def calcular(self, gl_p, gv_p, gl_r, gv_r, ganador_pred=None, ganador_real=None):
        exact = (gl_p == gl_r and gv_p == gv_r)
        correct = (
            ganador_pred is not None
            and ganador_real is not None
            and ganador_pred.id == ganador_real.id
        )
        if exact and correct:
            return 5
        return 2 if correct else 0


def _get_estrategia(fase):
    """O: factory — returns the right scoring strategy for a given phase."""
    return EstrategiaGrupo() if fase == 'GR' else EstrategiaEliminatoria()


# ── S: cálculo puro, sin acceso a BD ────────────────────────────────

def _ganador_real(partido):
    """S: determines real winner from match data. No DB access."""
    gl_r, gv_r = partido.goles_local_real, partido.goles_visitante_real
    if partido.fase != 'GR' and gl_r == gv_r:
        return partido.clasificado_real
    return partido.equipo_local if gl_r > gv_r else partido.equipo_visitante


def _ganador_pred(pred, partido):
    """S: determines predicted winner from a prediction. No DB access."""
    gl_p, gv_p = pred.goles_local, pred.goles_visitante
    if gl_p > gv_p:
        return partido.equipo_local
    if gv_p > gl_p:
        return partido.equipo_visitante
    return pred.clasificado_pred


def _calcular_puntos_pred(pred, partido, estrategia, ganador_real):
    """S: pure calculation — returns int points for one prediction."""
    return estrategia.calcular(
        pred.goles_local, pred.goles_visitante,
        partido.goles_local_real, partido.goles_visitante_real,
        ganador_pred=_ganador_pred(pred, partido),
        ganador_real=ganador_real,
    )


# ── S: persistencia separada del cálculo ────────────────────────────

def _guardar_puntos_predicciones(preds_pts):
    """S: only writes calculated points to DB. Returns affected user IDs."""
    usuario_ids = set()
    for pred, pts in preds_pts:
        pred.puntos = pts
        pred.save(update_fields=['puntos'])
        usuario_ids.add(pred.usuario_id)
    return usuario_ids


def _recalcular_totales(usuario_ids):
    """S: only recalculates total points per affected user."""
    for uid in usuario_ids:
        total = (
            Prediccion.objects
            .filter(usuario_id=uid, puntos__isnull=False)
            .aggregate(t=Sum('puntos'))['t'] or 0
        )
        PerfilUsuario.objects.filter(id=uid).update(puntos_totales=total)


# ── Orquestador público ───────────────────────────────────────────────

def calcular_puntos_partido(partido):
    """
    Calculates and saves points for every prediction of a played match.
    Returns the number of predictions processed.
    """
    if (not partido.jugado
            or partido.goles_local_real is None
            or partido.goles_visitante_real is None):
        return 0

    estrategia = _get_estrategia(partido.fase)
    gan_real   = _ganador_real(partido)

    preds = list(Prediccion.objects.filter(partido=partido).select_related(
        'usuario', 'clasificado_pred'))

    preds_pts = [
        (pred, _calcular_puntos_pred(pred, partido, estrategia, gan_real))
        for pred in preds
    ]

    usuario_ids = _guardar_puntos_predicciones(preds_pts)
    _recalcular_totales(usuario_ids)

    return len(preds)
