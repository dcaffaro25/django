"""
Script to load a minimal taxonomy of event types (E‑codes) into the database.

Usage::

    python scripts/import_taxonomy.py

It connects to Django settings and inserts known event codes if they do not
exist already.  This script is intended to be run after migrations.
"""
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'npl_project.settings')
django.setup()

from npl_project.apps.npl.models import EventType


EVENT_TYPES = {
    'E010': 'Abertura de prazo art. 523',
    'E012': 'Multa art. 523',
    'E032': 'Bloqueio SISBAJUD',
    'E067': 'Edital de leilão',
    'E068': 'Arrematação homologada',
    'E099': 'Suspensão art. 921',
}


def main() -> None:
    for code, desc in EVENT_TYPES.items():
        EventType.objects.get_or_create(code=code, defaults={'description': desc})
    print(f"Imported {len(EVENT_TYPES)} event types.")


if __name__ == '__main__':
    main()