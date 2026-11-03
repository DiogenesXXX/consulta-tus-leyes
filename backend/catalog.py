"""Catálogo sintético reproducible. No contiene legislación real."""
import re
import unicodedata
from collections import Counter
from datetime import date

SECTORS = ['Vivienda', 'Trabajo', 'Familia', 'Deudas', 'Salud', 'Negocio', 'Educación', 'Seguridad']
POLICIES = [
    {'id': 'democracia', 'name': 'Democracia y Estado de derecho'},
    {'id': 'equidad', 'name': 'Equidad y justicia social'},
    {'id': 'competitividad', 'name': 'Competitividad del país'},
    {'id': 'estado', 'name': 'Estado eficiente y descentralizado'},
]
ALIASES = {
    'Vivienda': 'alquiler arrendamiento casero cuarto desalojo vivienda botar casa',
    'Trabajo': 'trabajo sueldo pago salario cts despido empleo empleador',
    'Familia': 'familia pension alimentos hijo hija divorcio cuidado',
    'Deudas': 'deuda banco credito prestamo consumo reclamo compra',
    'Salud': 'salud hospital medicina medicamento atencion seguro',
    'Negocio': 'negocio tributo impuesto igv empresa emprendimiento',
    'Educación': 'educacion escuela colegio universidad beca estudiar matricula',
    'Seguridad': 'seguridad denuncia robo policia violencia proteccion',
}
SUBJECTS = [
    ('Información para personas que alquilan', 'Prórroga del arrendamiento verbal', 'Información clara sobre contratos de alquiler'),
    ('Información sobre remuneraciones', 'Transparencia en las boletas de pago', 'Orientación para el primer empleo'),
    ('Información sobre cuidados familiares', 'Servicios de orientación a familias', 'Acceso a información sobre pensiones'),
    ('Información para consumidores', 'Claridad en los contratos de crédito', 'Atención de consultas de consumo'),
    ('Información sobre atención en salud', 'Acceso a información de medicamentos', 'Orientación sobre servicios de salud'),
    ('Información para pequeños negocios', 'Simplificación de consultas tributarias', 'Formación para emprendedores'),
    ('Información sobre servicios educativos', 'Acceso a orientación sobre becas', 'Información clara sobre matrículas'),
    ('Información sobre canales de atención', 'Mejora de la orientación ciudadana', 'Accesibilidad de los canales de denuncia'),
]


def normalize(value):
    return ''.join(c for c in unicodedata.normalize('NFD', value.lower()) if unicodedata.category(c) != 'Mn')


def seed_catalog():
    items = []
    for sector_index, sector in enumerate(SECTORS):
        for variant, title in enumerate(SUBJECTS[sector_index]):
            index = sector_index * 3 + variant + 1
            kind = 'ley' if variant == 0 else 'proyecto'
            status = 'Vigente' if kind == 'ley' else ['En comisión', 'En Senado', 'Aprobado', 'Archivado'][(sector_index + variant) % 4]
            chamber = 'Diputados' if variant != 2 else 'Senado'
            policy = ['equidad', 'equidad', 'equidad', 'competitividad', 'equidad', 'competitividad', 'equidad', 'democracia'][sector_index]
            if variant == 2 and sector_index % 2:
                policy = 'estado'
            identifier = f'DEMO-{index:03d}'
            timeline = [
                {'label': f'Presentado en {chamber}', 'date': '2026-08-12', 'done': True},
                {'label': f'Comisión de {sector}', 'date': '2026-09-03', 'done': status != 'En comisión'},
                {'label': 'Debate y votación', 'date': '2026-09-10' if status in ['Aprobado', 'Vigente'] else None, 'done': status in ['Aprobado', 'Vigente']},
                {'label': 'Publicación', 'date': '2026-09-23' if kind == 'ley' else None, 'done': kind == 'ley'},
            ]
            if status == 'Archivado':
                timeline.append({'label': 'Archivado (ejemplo)', 'date': '2026-09-23', 'done': True})
            items.append({
                'id': identifier, 'number': f'{"Ley" if kind == "ley" else "PL"} {identifier}',
                'title': title, 'kind': kind, 'sector': sector, 'status': status,
                'chamber': chamber, 'group': ['Grupo A (demo)', 'Grupo B (demo)', 'Grupo C (demo)'][index % 3],
                'author': ['Ana Torres (demo)', 'Luis Campos (demo)', 'Rosa Medina (demo)', 'José Ríos (demo)'][index % 4],
                'commission': f'Comisión de {sector}', 'policy': policy, 'date': f'2026-09-{min(28, index + 1):02d}',
                'summary': f'Ficha ficticia para explorar la información sobre {sector.lower()}. Permite probar búsquedas, filtros y seguimiento.',
                'plain_text': f'Este es un ejemplo de una {"ley" if kind == "ley" else "propuesta"} sobre {sector.lower()}. No establece derechos, obligaciones ni plazos reales. En una versión conectada, aquí aparecerá un resumen revisado y enlazado a la fuente oficial.',
                'full_text': f'{identifier} · DOCUMENTO DE DEMOSTRACIÓN\n\n{title}\n\nContenido sintético para pruebas de software. No es una norma ni un proyecto oficial.\n\nArtículo ilustrativo: presentación de información clara para la ciudadanía.\n\nNo utilice esta ficha para tomar decisiones legales.',
                'timeline': timeline, 'related_id': f'DEMO-{sector_index * 3 + (2 if kind == "ley" else 1):03d}',
                'demo': True,
            })
    return items


FILTER_KEYS = ['kind', 'sector', 'status', 'chamber', 'group', 'author', 'commission', 'policy']


def filter_catalog(items, params):
    result = list(items)
    for key in FILTER_KEYS:
        if params.get(key):
            result = [item for item in result if item[key] == params[key]]
    for key in ['from', 'to']:
        if params.get(key):
            date.fromisoformat(params[key])
    if params.get('from') and params.get('to') and params['from'] > params['to']:
        raise ValueError('La fecha inicial debe ser anterior a la final.')
    if params.get('from'):
        result = [item for item in result if item['date'] >= params['from']]
    if params.get('to'):
        result = [item for item in result if item['date'] <= params['to']]
    query = normalize(params.get('q', '').strip())[:200]
    if query:
        stop = {'me', 'mi', 'mis', 'de', 'del', 'el', 'la', 'los', 'las', 'un', 'una', 'y', 'que', 'en', 'por', 'para', 'como', 'no', 'se', 'al'}
        words = set(re.findall(r'[a-z0-9]+', query)) - stop
        sectors = {sector for sector, aliases in ALIASES.items() if words & set(aliases.split())}
        result = [item for item in result if query in normalize(item['number'] + ' ' + item['title']) or
                  (words and words <= set(re.findall(r'[a-z0-9]+', normalize(item['title'] + ' ' + item['summary'] + ' ' + item['author'])))) or item['sector'] in sectors]
    return sorted(result, key=lambda item: item['date'], reverse=True)


def summarize(items):
    def groups(key):
        counts = Counter(item[key] for item in items)
        return [{'name': name, 'count': count} for name, count in sorted(counts.items(), key=lambda pair: (-pair[1], pair[0]))]
    return {'total': len(items), 'laws': sum(i['kind'] == 'ley' for i in items),
            'projects': sum(i['kind'] == 'proyecto' for i in items),
            'by_chamber': groups('chamber'), 'by_group': groups('group'), 'by_sector': groups('sector'),
            'by_author': groups('author'), 'by_status': groups('status'), 'by_policy': groups('policy'),
            'demo': True, 'methodology': 'Un registro por ficha. Cámara y grupo de origen. Los filtros se aplican a todos los conteos. Leyes y proyectos se contabilizan por separado; no es una tasa de aprobación.'}
