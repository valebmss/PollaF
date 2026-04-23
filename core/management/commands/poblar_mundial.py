from django.core.management.base import BaseCommand
from core.models import Pais, Partido
from itertools import combinations


GRUPOS = {
    'A': ['México', 'Sudáfrica', 'Corea del Sur', 'República Checa'],
    'B': ['Canadá', 'Bosnia y Herzegovina', 'Qatar', 'Suiza'],
    'C': ['Brasil', 'Marruecos', 'Haití', 'Escocia'],
    'D': ['Estados Unidos', 'Paraguay', 'Australia', 'Turquía'],
    'E': ['Alemania', 'Curazao', 'Costa de Marfil', 'Ecuador'],
    'F': ['Países Bajos', 'Japón', 'Suecia', 'Túnez'],
    'G': ['Bélgica', 'Egipto', 'Irán', 'Nueva Zelanda'],
    'H': ['España', 'Cabo Verde', 'Arabia Saudita', 'Uruguay'],
    'I': ['Francia', 'Senegal', 'Irak', 'Noruega'],
    'J': ['Argentina', 'Argelia', 'Austria', 'Jordania'],
    'K': ['Portugal', 'RD Congo', 'Uzbekistán', 'Colombia'],
    'L': ['Inglaterra', 'Croacia', 'Ghana', 'Panamá'],
}

CODIGOS = {
    'México': 'MEX', 'Sudáfrica': 'RSA', 'Corea del Sur': 'KOR', 'República Checa': 'CZE',
    'Canadá': 'CAN', 'Bosnia y Herzegovina': 'BIH', 'Qatar': 'QAT', 'Suiza': 'SUI',
    'Brasil': 'BRA', 'Marruecos': 'MAR', 'Haití': 'HAI', 'Escocia': 'SCO',
    'Estados Unidos': 'USA', 'Paraguay': 'PAR', 'Australia': 'AUS', 'Turquía': 'TUR',
    'Alemania': 'GER', 'Curazao': 'CUW', 'Costa de Marfil': 'CIV', 'Ecuador': 'ECU',
    'Países Bajos': 'NED', 'Japón': 'JPN', 'Suecia': 'SWE', 'Túnez': 'TUN',
    'Bélgica': 'BEL', 'Egipto': 'EGY', 'Irán': 'IRN', 'Nueva Zelanda': 'NZL',
    'España': 'ESP', 'Cabo Verde': 'CPV', 'Arabia Saudita': 'KSA', 'Uruguay': 'URU',
    'Francia': 'FRA', 'Senegal': 'SEN', 'Irak': 'IRQ', 'Noruega': 'NOR',
    'Argentina': 'ARG', 'Argelia': 'ALG', 'Austria': 'AUT', 'Jordania': 'JOR',
    'Portugal': 'POR', 'RD Congo': 'COD', 'Uzbekistán': 'UZB', 'Colombia': 'COL',
    'Inglaterra': 'ENG', 'Croacia': 'CRO', 'Ghana': 'GHA', 'Panamá': 'PAN',
}

# Ronda de 32: (label_local, label_visitante)
# Fuente: reglamento FIFA 2026
RONDA_32 = [
    ('2do Grupo A', '2do Grupo B'),
    ('1ro Grupo E', 'Mejor 3ro A/B/C/D/F'),
    ('1ro Grupo F', '2do Grupo C'),
    ('1ro Grupo C', '2do Grupo F'),
    ('1ro Grupo I', 'Mejor 3ro C/D/F/G/H'),
    ('2do Grupo E', '2do Grupo I'),
    ('1ro Grupo A', 'Mejor 3ro C/E/F/H/I'),
    ('1ro Grupo L', 'Mejor 3ro E/H/I/J/K'),
    ('1ro Grupo D', 'Mejor 3ro B/E/F/I/J'),
    ('1ro Grupo G', 'Mejor 3ro A/E/H/I/J'),
    ('2do Grupo K', '2do Grupo L'),
    ('1ro Grupo H', '2do Grupo J'),
    ('1ro Grupo B', 'Mejor 3ro E/F/G/I/J'),
    ('1ro Grupo J', '2do Grupo H'),
    ('1ro Grupo K', 'Mejor 3ro D/E/I/J/L'),
    ('2do Grupo D', '2do Grupo G'),
]

# Etiquetas para Octavos en adelante (basadas en el bracket)
OCTAVOS = [
    ('Ganador R32 M1', 'Ganador R32 M2'),
    ('Ganador R32 M3', 'Ganador R32 M4'),
    ('Ganador R32 M5', 'Ganador R32 M6'),
    ('Ganador R32 M7', 'Ganador R32 M8'),
    ('Ganador R32 M9', 'Ganador R32 M10'),
    ('Ganador R32 M11', 'Ganador R32 M12'),
    ('Ganador R32 M13', 'Ganador R32 M14'),
    ('Ganador R32 M15', 'Ganador R32 M16'),
]

CUARTOS = [
    ('Ganador Octavos M1', 'Ganador Octavos M2'),
    ('Ganador Octavos M3', 'Ganador Octavos M4'),
    ('Ganador Octavos M5', 'Ganador Octavos M6'),
    ('Ganador Octavos M7', 'Ganador Octavos M8'),
]

SEMIS = [
    ('Ganador Cuartos M1', 'Ganador Cuartos M2'),
    ('Ganador Cuartos M3', 'Ganador Cuartos M4'),
]


class Command(BaseCommand):
    help = 'Pobla la base de datos con países y partidos del Mundial 2026'

    def handle(self, *args, **kwargs):
        self.stdout.write('Eliminando datos previos...')
        Partido.objects.all().delete()
        Pais.objects.all().delete()

        # ── Países ──────────────────────────────────────────────────
        self.stdout.write('Creando países...')
        paises = {}
        for grupo, equipos in GRUPOS.items():
            for nombre in equipos:
                p = Pais.objects.create(
                    nombre=nombre,
                    codigo=CODIGOS[nombre],
                    grupo=grupo,
                )
                paises[nombre] = p
        self.stdout.write(self.style.SUCCESS(f'  {Pais.objects.count()} países creados'))

        # ── Fase de grupos (72 partidos) ────────────────────────────
        self.stdout.write('Creando partidos de grupos...')
        num = 1
        for grupo, equipos in GRUPOS.items():
            for local, visitante in combinations(equipos, 2):
                Partido.objects.create(
                    numero=num,
                    fase='GR',
                    grupo=grupo,
                    equipo_local=paises[local],
                    equipo_visitante=paises[visitante],
                    label_local=local,
                    label_visitante=visitante,
                )
                num += 1
        self.stdout.write(self.style.SUCCESS(f'  {num - 1} partidos de grupos creados'))

        # ── Ronda de 32 (16 partidos) ───────────────────────────────
        self.stdout.write('Creando Ronda de 32...')
        for i, (ll, lv) in enumerate(RONDA_32, start=1):
            Partido.objects.create(
                numero=num,
                fase='R32',
                label_local=ll,
                label_visitante=lv,
            )
            num += 1

        # ── Octavos (8 partidos) ────────────────────────────────────
        self.stdout.write('Creando Octavos de Final...')
        for ll, lv in OCTAVOS:
            Partido.objects.create(
                numero=num, fase='R16',
                label_local=ll, label_visitante=lv,
            )
            num += 1

        # ── Cuartos (4 partidos) ────────────────────────────────────
        self.stdout.write('Creando Cuartos de Final...')
        for ll, lv in CUARTOS:
            Partido.objects.create(
                numero=num, fase='QF',
                label_local=ll, label_visitante=lv,
            )
            num += 1

        # ── Semifinales (2 partidos) ────────────────────────────────
        self.stdout.write('Creando Semifinales...')
        for ll, lv in SEMIS:
            Partido.objects.create(
                numero=num, fase='SF',
                label_local=ll, label_visitante=lv,
            )
            num += 1

        # ── Tercer puesto ───────────────────────────────────────────
        Partido.objects.create(
            numero=num, fase='TP',
            label_local='Perdedor Semi M1', label_visitante='Perdedor Semi M2',
        )
        num += 1

        # ── Final ───────────────────────────────────────────────────
        Partido.objects.create(
            numero=num, fase='FI',
            label_local='Ganador Semi M1', label_visitante='Ganador Semi M2',
        )

        total = Partido.objects.count()
        self.stdout.write(self.style.SUCCESS(
            f'\nOK Total: {Pais.objects.count()} paises y {total} partidos creados.'
        ))
        self.stdout.write(self.style.WARNING(
            'AVISO: Verifica los equipos TBD-G4, TBD-H4, TBD-I4, TBD-J4 en grupos G, H, I, J.'
        ))
