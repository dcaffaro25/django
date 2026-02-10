from django.test import TestCase
from rest_framework.test import APITestCase, APIClient
from rest_framework import status
from django.contrib.auth import get_user_model
from multitenancy.models import Company

from .services.nfe_import_service import import_many


class NFeImportServiceTestCase(TestCase):
    """Testes do engine de importação de NFe."""

    def setUp(self):
        self.company = Company.objects.create(name="Test NFe Company", subdomain="test-nfe")

    def test_import_many_empty_returns_correct_structure(self):
        result = import_many([], self.company)
        self.assertIn("importadas", result)
        self.assertIn("duplicadas", result)
        self.assertIn("erros", result)
        self.assertEqual(result["importadas"], [])
        self.assertEqual(result["duplicadas"], [])
        self.assertEqual(result["erros"], [])


class NFeImportViewTestCase(APITestCase):
    """Testes do endpoint POST /api/nfe/import/."""

    def setUp(self):
        self.company = Company.objects.create(name="Test NFe Company", subdomain="test-nfe-import")
        self.user = get_user_model().objects.create_user(username="nfeuser", password="testpass")
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    def test_import_without_files_returns_400(self):
        from billing.views_nfe import NFeImportView
        from django.test import RequestFactory
        factory = RequestFactory()
        req = factory.post("/api/nfe/import/")
        req.tenant = self.company
        req.FILES = {}
        view = NFeImportView.as_view()
        response = view(req, tenant_id=self.company.subdomain)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("files", str(response.data).lower() or "detail" in response.data)
