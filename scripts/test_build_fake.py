"""Test de build avec données factices — vérifie le pipeline complet."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from datetime import datetime, timedelta
import random
random.seed(42)

from modules.builder import build_html, build_profile

# Génération de 200 séances factices sur 18 mois
TYPES = ['endurance', 'footing', 'tempo', 'frac_court', 'frac_long', 'sortie_longue', 'marathon', 'semi']
TYPE_WEIGHTS = [40, 15, 8, 12, 8, 12, 1, 4]

sessions = []
base_date = datetime(2026, 5, 14)
for i in range(200):
    d = base_date - timedelta(days=i * 2 + random.randint(0, 1))
    tp = random.choices(TYPES, weights=TYPE_WEIGHTS)[0]

    if tp == 'marathon':
        km = round(42.195, 2)
        pace_s = random.randint(240, 260)
    elif tp == 'semi':
        km = round(random.uniform(21, 22), 2)
        pace_s = random.randint(225, 245)
    elif tp == 'sortie_longue':
        km = round(random.uniform(25, 35), 2)
        pace_s = random.randint(265, 295)
    elif tp == 'frac_court':
        km = round(random.uniform(8, 13), 2)
        pace_s = random.randint(220, 260)
    elif tp == 'frac_long':
        km = round(random.uniform(12, 18), 2)
        pace_s = random.randint(230, 260)
    elif tp == 'tempo':
        km = round(random.uniform(10, 16), 2)
        pace_s = random.randint(235, 255)
    elif tp == 'footing':
        km = round(random.uniform(6, 10), 2)
        pace_s = random.randint(310, 340)
    else:  # endurance
        km = round(random.uniform(10, 18), 2)
        pace_s = random.randint(270, 300)

    dur_s = int(km * pace_s)
    sessions.append({
        'd': d.strftime('%d/%m/%Y'),
        'h': f"{random.randint(6, 19):02d}:{random.choice(['00', '15', '30', '45'])}",
        't': f"Séance {tp}",
        'km': km,
        'dur': f"{dur_s // 3600}h {(dur_s % 3600) // 60:02d}m {dur_s % 60:02d}s" if dur_s >= 3600 else f"{dur_s // 60}m {dur_s % 60:02d}s",
        'dur_s': dur_s,
        'v': round(3600 / pace_s, 2),
        'a': f"{pace_s // 60}'{pace_s % 60:02d}\"/km",
        'ps': pace_s,
        'fc': random.randint(135, 175),
        'tp': tp,
        'cv': round(random.uniform(2, 15), 1),
        'track': False,
        'b': [],
        'source': f'fake_{i}.fit',
    })

# Tri date desc
sessions.sort(key=lambda s: datetime.strptime(s['d'] + ' ' + s['h'], '%d/%m/%Y %H:%M'), reverse=True)

print(f"Sessions générées : {len(sessions)}")
print(f"Plus récente : {sessions[0]['d']} — {sessions[0]['km']} km {sessions[0]['tp']}")
print(f"Plus ancienne : {sessions[-1]['d']}")
print(f"Total : {sum(s['km'] for s in sessions):.0f} km")

# Build
profile = build_profile()
output_path = Path(__file__).parent.parent / 'output' / 'index.html'
output_path.parent.mkdir(exist_ok=True)

build_html(
    sessions=sessions,
    profile=profile,
    templates_dir=str(Path(__file__).parent.parent / 'templates'),
    output_path=str(output_path),
)

print(f"\n✓ HTML généré : {output_path}")
print(f"  Taille : {output_path.stat().st_size / 1024:.1f} Ko")
