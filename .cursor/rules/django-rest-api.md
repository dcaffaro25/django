# Django REST API Best Practices

## Project Structure

- Follow Django's app-based architecture - one app per domain/feature
- Keep views, serializers, and models in separate files when they grow large
- Use `services/` directory for business logic, keep views thin
- Use `utils/` for reusable helper functions
- Create `permissions.py` for custom permission classes
- Use `filters.py` for filtering logic (django-filter)

## Models

- Use descriptive model names in singular form: `User`, `Product`, `Order`
- Always define `__str__` method for models
- Use `Meta` class for ordering, verbose names, and constraints
- Add `db_index=True` for frequently queried fields
- Use `related_name` for reverse relationships
- Use `on_delete` explicitly for ForeignKey and OneToOneField
- Add `null=True, blank=True` for optional fields
- Use `choices` for fields with limited options
- Add `help_text` and `verbose_name` for better admin interface
- Use `DateTimeField` with `auto_now_add` for created_at, `auto_now` for updated_at

## Serializers

- Use `ModelSerializer` for CRUD operations, `Serializer` for custom logic
- Validate data in serializer's `validate()` method
- Use `validate_<field_name>()` for field-specific validation
- Use `SerializerMethodField` for computed/read-only fields
- Use `to_representation()` to customize output format
- Use `to_internal_value()` to customize input processing
- Always specify `read_only` or `write_only` fields explicitly
- Use `source` parameter to map fields from different model attributes
- Use `required=False` with `allow_null=True` for optional fields

## Views & ViewSets

- Use `ViewSet` or `ModelViewSet` for standard CRUD operations
- Use `GenericViewSet` with mixins for custom behavior
- Use `@action` decorator for custom endpoints
- Keep views thin - delegate business logic to services
- Use `get_queryset()` to filter querysets based on permissions
- Use `get_serializer_class()` for dynamic serializer selection
- Override `perform_create()` and `perform_update()` for custom save logic
- Use `pagination_class` for list endpoints
- Use `filter_backends` and `filterset_fields` for filtering

## Permissions

- Use Django REST Framework's built-in permissions: `IsAuthenticated`, `IsAdminUser`
- Create custom permission classes inheriting from `BasePermission`
- Use `has_object_permission()` for object-level permissions
- Use `has_permission()` for view-level permissions
- Apply permissions at viewset or view level, not in serializers

## Authentication

- Use token authentication for API clients: `TokenAuthentication`
- Use session authentication for web clients
- Use JWT for stateless authentication when needed
- Never store passwords in plain text - use Django's password hashing
- Use `django.contrib.auth` for user management

## URL Routing

- Use `DefaultRouter` for ViewSets
- Use `SimpleRouter` for simpler routing needs
- Register viewsets with `router.register()`
- Use `@action` decorator for custom endpoints
- Keep URL patterns organized and descriptive
- Use namespaces for app URLs: `app_name = 'api'`

## Error Handling

- Use DRF's exception handling: `APIException`, `ValidationError`
- Create custom exception classes when needed
- Return appropriate HTTP status codes
- Use `status` module constants: `status.HTTP_400_BAD_REQUEST`
- Provide meaningful error messages
- Use `serializer.errors` for validation errors

## Query Optimization

- Use `select_related()` for ForeignKey relationships
- Use `prefetch_related()` for ManyToMany and reverse ForeignKey
- Use `only()` and `defer()` to limit fields fetched
- Avoid N+1 queries - use `prefetch_related` and `select_related`
- Use `annotate()` and `aggregate()` for database-level calculations
- Use `exists()` instead of `count()` when checking existence
- Use `iterator()` for large querysets

## Pagination

- Always paginate list endpoints
- Use `PageNumberPagination` for simple pagination
- Use `LimitOffsetPagination` for offset-based pagination
- Use `CursorPagination` for large datasets
- Set reasonable `page_size` defaults
- Allow clients to override page size when appropriate

## Filtering & Searching

- Use `django-filter` for complex filtering
- Use `SearchFilter` for text search
- Use `OrderingFilter` for sorting
- Define `filterset_fields` or custom `FilterSet` classes
- Validate filter parameters
- Document available filters in API documentation

## Testing

- Use DRF's `APITestCase` for API tests
- Test all HTTP methods: GET, POST, PUT, PATCH, DELETE
- Test authentication and permissions
- Test validation errors
- Use factories (factory_boy) for test data
- Test edge cases and error conditions
- Use `APIClient` for making requests in tests

## Security

- Always validate and sanitize input
- Use `csrf_exempt` only when necessary and with proper authentication
- Implement rate limiting for public endpoints
- Use HTTPS in production
- Validate file uploads (type, size)
- Use `django-cors-headers` properly configured for CORS
- Never expose sensitive data in error messages
- Use environment variables for secrets (django-environ)

## API Documentation

- Use `drf-yasg` or `drf-spectacular` for OpenAPI/Swagger docs
- Document all endpoints with docstrings
- Include request/response examples
- Document query parameters and filters
- Use schema decorators for custom actions

## Serialization Best Practices

- Use `depth` parameter sparingly (can cause N+1 queries)
- Use `SerializerMethodField` for computed fields
- Use `PrimaryKeyRelatedField` for simple relationships
- Use nested serializers for complex relationships
- Use `ListSerializer` for bulk operations
- Validate uniqueness in serializers when needed

## Response Format

- Use consistent response structure across the API
- Return appropriate HTTP status codes
- Include pagination metadata in list responses
- Use `Response` class instead of `JsonResponse` for DRF views
- Format dates consistently (ISO 8601)

## Database Migrations

- Always create migrations for model changes
- Review migration files before applying
- Use `makemigrations --dry-run` to preview changes
- Never edit existing migrations - create new ones
- Use data migrations for data transformations
- Test migrations on a copy of production data

## Environment Configuration

- Use `django-environ` for environment variables
- Never commit secrets to version control
- Use different settings files for different environments
- Use `.env` files for local development
- Document required environment variables

## Performance

- Use database indexes for frequently queried fields
- Implement caching where appropriate (Redis, Memcached)
- Use `select_related` and `prefetch_related` to avoid N+1 queries
- Monitor slow queries and optimize
- Use `connection.queries` in development to debug queries
- Consider using `django-debug-toolbar` for development

## Code Quality

- Follow PEP 8 style guide
- Use type hints where appropriate (Python 3.5+)
- Write docstrings for classes and functions
- Keep functions small and focused
- Use meaningful variable and function names
- Avoid deep nesting - use early returns

## Common Patterns

- Use service layer pattern for complex business logic
- Use repository pattern for data access abstraction
- Use signals sparingly - prefer explicit method calls
- Use custom managers and querysets for reusable query logic
- Use `@transaction.atomic` for database transactions

