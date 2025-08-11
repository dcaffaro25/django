# NORD/hr/urls.py
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    PositionViewSet, EmployeeViewSet, TimeTrackingViewSet, 
    KPIViewSet, BonusViewSet, PayrollViewSet, RecurringAdjustmentViewSet
)

router = DefaultRouter()
router.trailing_slash = r'/?'

router.register(r'positions', PositionViewSet)
router.register(r'employees', EmployeeViewSet)
router.register(r'timetracking', TimeTrackingViewSet)
router.register(r'kpis', KPIViewSet)
router.register(r'bonuses', BonusViewSet)
router.register(r'payrolls', PayrollViewSet, basename='payroll')
router.register(r'recurring-adjustments', RecurringAdjustmentViewSet)


urlpatterns = [
    path(r'^api/hr/?$', include(router.urls)),
]