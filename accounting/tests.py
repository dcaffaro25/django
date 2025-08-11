# tests.py
from django.urls import reverse, NoReverseMatch
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APITestCase, APIClient
from django.contrib.auth import get_user_model
from multitenancy.models import Company, CustomUser, Entity

class GenericViewSetTestCase(APITestCase):
    """
    A generic test case for testing CRUD operations in DRF viewsets.
    """

    def setUp(self):
        # Set up a test client and a user for authentication (if needed)
        CustomUser = get_user_model()
        self.user = CustomUser.objects.create_user(username='testuser', password='12345')
        #make user a suepruser
        #self.user.is_superuser = True
        self.company = Company.objects.create(name='Test Company', subdomain='test-company')

        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

        # Set these in subclass
        self.model = None
        self.serializer_class = None
        self.viewset_basename = None
        self.valid_payload = None
        self.invalid_payload = None
        self.bulk_payload = None
        self.list_url_name = None
        self.detail_url_name = None
        self.bulk_create_url_name = None
        self.bulk_delete_url_name = None

    def check_create(self):
        url = reverse(self.list_url_name, kwargs={'tenant_id':self.company.subdomain})
        response = self.client.post(url, self.valid_payload)
        print(url)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def check_create_invalid(self):
        url = reverse(self.list_url_name, kwargs={'tenant_id':self.company.subdomain})
        response = self.client.post(url, self.invalid_payload)
        print(url)
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def check_list(self):
        url = reverse(self.list_url_name, kwargs={'tenant_id':self.company.subdomain})
        response = self.client.get(url)
        print(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def check_update(self):
        instance = self.model.objects.create(**self.valid_payload)
        updated_payload = self.valid_payload.copy()
        updated_payload.update({'name': 'Updated Name'})
        url = reverse(self.detail_url_name, kwargs={'tenant_id':self.company.subdomain,'pk': instance.id})
        response = self.client.put(url, updated_payload)
        print(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def check_delete(self):
        instance = self.model.objects.create(**self.valid_payload)
        url = reverse(self.detail_url_name, kwargs={'tenant_id':self.company.subdomain,'pk': instance.id})
        response = self.client.delete(url)
        print(url)
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)

    def check_bulk_create(self):
        url = reverse(self.bulk_create_url_name, kwargs={'tenant_id':self.company.subdomain})
        response = self.client.post(url, self.bulk_payload, format='json')
        print(url)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def check_bulk_delete(self):
        # Create instances for deletion
        for payload in self.bulk_payload:
            self.model.objects.create(**payload)
        delete_ids = [instance.id for instance in self.model.objects.all()]
        url = reverse(self.bulk_delete_url_name, kwargs={'tenant_id':self.company.subdomain})
        response = self.client.delete(url, delete_ids, format='json')
        print(url)
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)




# Example of subclassing for specific model/viewset
class CurrencyViewSetTestCase(GenericViewSetTestCase):
    def setUp(self):
        super().setUp()
        from .models import Currency
        from .serializers import CurrencySerializer

        self.model = Currency
        self.serializer_class = CurrencySerializer
        self.viewset_basename = 'currency'
        self.valid_payload = {'code': 'USD', 'name': 'US Dollar', 'symbol': '$'}
        self.invalid_payload = {'code': 'US', 'name': 'US Dollar', 'symbol': '$'}
        self.bulk_payload = [{'code': 'EUR', 'name': 'Euro', 'symbol': '€'}, {'code': 'GBP', 'name': 'British Pound', 'symbol': '£'}]

        self.list_url_name = 'currency-list'
        self.detail_url_name = 'currency-detail'
        self.bulk_create_url_name = 'currency-bulk-create'
        self.bulk_delete_url_name = 'currency-bulk-delete'

    def test_create(self):
        self.check_create()

    def test_create_invalid(self):
        self.check_create_invalid()

    def test_list(self):
        self.check_list()

    def test_update(self):
        self.check_update()

    def test_delete(self):
        self.check_delete()

    def test_bulk_create(self):
        self.check_bulk_create()

    def test_bulk_delete(self):
        self.check_bulk_delete()
