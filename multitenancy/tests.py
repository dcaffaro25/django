from django.test import TestCase
from .models import CustomUser, Company, Entity

'''
class CustomUserModelTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        # Set up non-modified objects used by all test methods
        CustomUser.objects.create(username='testuser', password='foo')

    def test_user_creation(self):
        user = CustomUser.objects.get(id=1)
        self.assertEqual(user.username, 'testuser')

class CompanyModelTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        # Create a Company object to test with
        Company.objects.create(name='Test Company', subdomain='test-company')

    def test_company_creation(self):
        company = Company.objects.get(id=1)
        self.assertEqual(company.name, 'Test Company')

    def test_subdomain_auto_generation(self):
        # Test the auto-generation of subdomain based on the company name
        company = Company.objects.get(id=1)
        self.assertEqual(company.subdomain, 'test-company')

    def test_subdomain_uniqueness(self):
        # Test that creating a second company with the same subdomain raises an error
        with self.assertRaises(ValueError):
            Company.objects.create(name='Another Test Company', subdomain='test-company')

class EntityModelTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        company = Company.objects.create(name='Test Company', subdomain='test-company')
        Entity.objects.create(name='Test Entity', company=company)

    def test_entity_creation(self):
        entity = Entity.objects.get(id=1)
        self.assertEqual(entity.name, 'Test Entity')

    def test_get_path(self):
        # Test the get_path method functionality
        company = Company.objects.get(id=1)
        parent_entity = Entity.objects.create(name='Parent Entity', company=company)
        child_entity = Entity.objects.create(name='Child Entity', company=company, parent=parent_entity)
        self.assertEqual(child_entity.get_path(), 'Parent Entity > Child Entity')
'''
