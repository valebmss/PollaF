# Lógica oficial FIFA para asignación de mejores terceros en la Ronda de 32
# Fuente: Reglamento FIFA Copa del Mundo 2026, Anexo C
#
# CONTEXTO
# --------
# En el Mundial 2026 hay 12 grupos. Los terceros de cada grupo compiten por
# 8 plazas en la Ronda de 32. Cada plaza (slot) solo puede ser ocupada por
# terceros de ciertos grupos (restricción geográfica/de balanceo FIFA).
#
# TIPOS DE DATOS
# --------------
# - grupos_clasificados : set[str]   → 8 letras, ej. {'A','C','E','G','H','I','J','K'}
# - SLOTS_ELEGIBLES     : dict[int, set[str]]  → partido → grupos válidos para ese slot
# - COMBINACIONES       : dict[frozenset, dict[int, str]]
#                         clave: frozenset de 8 letras (inmutable, hashable)
#                         valor: {número_partido: letra_grupo_del_tercero}
# - retorno             : dict[int, str]  → {74:'A', 77:'C', ...}
#
# POR QUÉ frozenset COMO CLAVE
# ----------------------------
# Un set normal es mutable → no es hashable → no puede ser clave de dict.
# frozenset es inmutable → hashable → permite búsqueda O(1) en COMBINACIONES.
# Ejemplo: frozenset('ABCDEFGH') == frozenset({'A','B','C','D','E','F','G','H'})
# sin importar el orden en que se pasen las letras.

# ── Slots y sus grupos elegibles (constraint oficial FIFA) ───────────────────
# Cada número es el partido R32 que enfrenta al ganador de un grupo con un 3ro.
# La restricción garantiza equilibrio geográfico y de bracket.
SLOTS_ELEGIBLES = {
    74: {'A', 'B', 'C', 'D', 'F'},   # Ganador Grupo E  vs Mejor 3ro de A/B/C/D/F
    77: {'C', 'D', 'F', 'G', 'H'},   # Ganador Grupo I  vs Mejor 3ro de C/D/F/G/H
    79: {'C', 'E', 'F', 'H', 'I'},   # Ganador Grupo A  vs Mejor 3ro de C/E/F/H/I
    80: {'E', 'H', 'I', 'J', 'K'},   # Ganador Grupo L  vs Mejor 3ro de E/H/I/J/K
    81: {'B', 'E', 'F', 'I', 'J'},   # Ganador Grupo D  vs Mejor 3ro de B/E/F/I/J
    82: {'A', 'E', 'H', 'I', 'J'},   # Ganador Grupo G  vs Mejor 3ro de A/E/H/I/J
    85: {'E', 'F', 'G', 'I', 'J'},   # Ganador Grupo B  vs Mejor 3ro de E/F/G/I/J
    87: {'D', 'E', 'I', 'J', 'L'},   # Ganador Grupo K  vs Mejor 3ro de D/E/I/J/L
}

# Tabla precalculada con las 495 combinaciones posibles (C(12,8) = 495).
# Generada con backtracking determinístico respetando todos los SLOTS_ELEGIBLES.
from .terceros_tabla import COMBINACIONES


# ── Función principal ────────────────────────────────────────────────────────

def asignar_terceros(grupos_clasificados: set) -> dict:
    """
    Dado el conjunto de 8 letras de grupo cuyos terceros clasificaron,
    devuelve la asignación {numero_partido: letra_grupo}.

    Parámetros:
        grupos_clasificados : set de exactamente 8 letras
                              ej. {'A','C','E','G','H','I','J','K'}

    Retorna:
        dict[int, str] con 8 entradas, claves: 74,77,79,80,81,82,85,87
        ej. {74:'A', 77:'C', 79:'I', 80:'E', 81:'J', 82:'H', 85:'G', 87:'L'}
        Vacío solo si la combinación no tiene asignación válida (no debería ocurrir).

    Algoritmo:
        1. Convierte el set a frozenset (hashable).
        2. Busca en COMBINACIONES → O(1).
        3. Si no existe (no debería pasar con las 495 precalculadas),
           corre el solver de backtracking como fallback.
    """
    clave = frozenset(grupos_clasificados)
    if clave in COMBINACIONES:
        return dict(COMBINACIONES[clave])  # devuelve copia para evitar mutaciones
    return _resolver_con_backtracking(sorted(grupos_clasificados))


# ── Solver de backtracking (fallback) ────────────────────────────────────────

def _resolver_con_backtracking(grupos: list) -> dict:
    """
    Encuentra una asignación válida usando backtracking recursivo.
    Recorre los slots en orden fijo [74,77,79,80,81,82,85,87] e intenta
    asignar cada grupo en orden alfabético → resultado determinístico.

    Complejidad: O(8!) en el peor caso, pero en la práctica muy rápido
    gracias a la poda (grupos ya usados y constraint de elegibilidad).
    """
    slots = [74, 77, 79, 80, 81, 82, 85, 87]
    asignacion = {}
    usados = set()

    def backtrack(idx):
        if idx == len(slots):
            return True
        slot = slots[idx]
        elegibles = SLOTS_ELEGIBLES[slot]
        for grupo in grupos:
            if grupo in elegibles and grupo not in usados:
                asignacion[slot] = grupo
                usados.add(grupo)
                if backtrack(idx + 1):
                    return True
                del asignacion[slot]
                usados.discard(grupo)
        return False

    backtrack(0)
    return asignacion


# ── Criterios de ranking de terceros (FIFA 2026) ─────────────────────────────
# Se aplican en este orden hasta desempatar. En PollaF se usan los 4 primeros
# (los datos de tarjetas y ranking FIFA no están en el modelo actual).

CRITERIOS_RANKING = [
    "puntos",            # puntos acumulados en fase de grupos
    "diferencia_goles",  # goles a favor - goles en contra
    "goles_favor",       # goles anotados
    "victorias",         # número de victorias
    "fair_play",         # -1 amarilla, -3 roja directa, -4 doble amarilla=roja
    "ranking_fifa",      # ranking FIFA al momento del sorteo
]
