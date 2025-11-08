"""
Script to import fictitious PDFs into the system for demonstration.

This script assumes that you have placed your PDF files in the ``fixtures``
directory under the project root.  It will create a dummy process and upload
each PDF via the Django ORM so that Celery can process them.
"""
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'npl_project.settings')
django.setup()

from npl_project.apps.npl.models import Process, Document


def main() -> None:
    process, _ = Process.objects.get_or_create(case_number='0000000-00.0000.0.00.0000')
    fixtures_dir = os.path.join(os.path.dirname(__file__), '..', 'fixtures')
    if not os.path.isdir(fixtures_dir):
        print(f"Fixtures directory {fixtures_dir} does not exist. Please add sample PDFs there.")
        return
    for fname in os.listdir(fixtures_dir):
        if fname.lower().endswith('.pdf'):
            path = os.path.join(fixtures_dir, fname)
            with open(path, 'rb') as f:
                doc = Document.objects.create(process=process, file=f)
                print(f"Created document {doc.id} for {fname}")


if __name__ == '__main__':
    main()