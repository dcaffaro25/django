# NORD/hr/urls.py
from django.urls import re_path, include
from rest_framework.routers import DefaultRouter
from .views import (
    PositionViewSet, EmployeeViewSet, TimeTrackingViewSet, 
    KPIViewSet, BonusViewSet, PayrollViewSet, RecurringAdjustmentViewSet
)

class LooseSlashRouter(DefaultRouter):
    trailing_slash = r'/?'

router = LooseSlashRouter()
router.register('positions', PositionViewSet)
router.register('employees', EmployeeViewSet)
router.register('timetracking', TimeTrackingViewSet)
router.register('kpis', KPIViewSet)
router.register('bonuses', BonusViewSet)
router.register('payrolls', PayrollViewSet, basename='payroll')
router.register('recurring-adjustments', RecurringAdjustmentViewSet)

urlpatterns = [
    # IMPORTANT: no extra 'api/hr' here
    re_path(r'', include(router.urls)),
]
