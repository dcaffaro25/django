from django.db import models
from mptt.models import MPTTModel, TreeForeignKey
from multitenancy.models import BaseModel, TenantAwareBaseModel
from core.models import FinancialIndex, IndexQuote, FinancialIndexQuoteForecast
from django.utils import timezone

class BusinessPartnerCategory(TenantAwareBaseModel, MPTTModel):
    name = models.CharField(max_length=100)
    parent = TreeForeignKey('self', null=True, blank=True, related_name='children', on_delete=models.CASCADE)

    def __str__(self):
        return self.name
    
    def get_path(self):
        """Return the full path of this entity as a string."""
        ancestors = [self.name]
        parent = self.parent
        while parent is not None:
            ancestors.insert(0, parent.name)
            parent = parent.parent
        return ' > '.join(ancestors)
    
    def get_path_ids(self):
        """Returns the list of IDs representing the full path to this entity."""
        path = []
        current = self
        while current:
            path.insert(0, current.id)  # Prepend the current entity ID
            current = current.parent
        return path
    
    class MPTTMeta:
        order_insertion_by = ['name'] 

class BusinessPartner(TenantAwareBaseModel):
    PARTNER_TYPES = [('client', 'Client'), ('vendor', 'Vendor'), ('both', 'Both')]

    name = models.CharField(max_length=255)
    partner_type = models.CharField(max_length=10, choices=PARTNER_TYPES)
    category = TreeForeignKey(BusinessPartnerCategory, null=True, blank=True, on_delete=models.SET_NULL)
    identifier = models.CharField(max_length=50, unique=True)  # CPF/CNPJ
    address = models.CharField(max_length=255, blank=True)
    city = models.CharField(max_length=100, blank=True)
    state = models.CharField(max_length=100, blank=True)
    zipcode = models.CharField(max_length=20, blank=True)
    country = models.CharField(max_length=100, default='Brazil')
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=20, blank=True)
    currency = models.ForeignKey('accounting.Currency', on_delete=models.SET_NULL, null=True)
    payment_terms = models.CharField(max_length=50, blank=True)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.name} ({self.partner_type})"

class ProductServiceCategory(TenantAwareBaseModel, MPTTModel):
    name = models.CharField(max_length=100)
    parent = TreeForeignKey('self', null=True, blank=True, related_name='children', on_delete=models.CASCADE)

    def __str__(self):
        return self.name
    
class ProductService(TenantAwareBaseModel):
    TYPES = [('product', 'Product'), ('service', 'Service')]

    name = models.CharField(max_length=255)
    code = models.CharField(max_length=100, unique=True)
    category = TreeForeignKey(ProductServiceCategory, null=True, blank=True, on_delete=models.SET_NULL)
    description = models.TextField(blank=True)
    item_type = models.CharField(max_length=10, choices=TYPES)
    price = models.DecimalField(max_digits=12, decimal_places=2)
    cost = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    currency = models.ForeignKey('accounting.Currency', on_delete=models.SET_NULL, null=True)
    tax_code = models.CharField(max_length=50, blank=True)
    track_inventory = models.BooleanField(default=False)
    stock_quantity = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f"{self.name} ({self.item_type})"

class Contract(models.Model):
    company = models.ForeignKey('multitenancy.Company', on_delete=models.CASCADE)
    partner = models.ForeignKey('BusinessPartner', on_delete=models.CASCADE)
    contract_number = models.CharField(max_length=50, unique=True)
    start_date = models.DateField(default=timezone.now)
    end_date = models.DateField(null=True, blank=True)

    recurrence_rule = models.TextField(
        blank=True,
        help_text="RRULE string for recurrence, e.g., FREQ=MONTHLY;INTERVAL=1"
    )

    base_value = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    base_index_date = models.DateField(
        null=True, blank=True,
        help_text="Start date to reference for index adjustment"
    )
    adjustment_index = models.ForeignKey(
        FinancialIndex, on_delete=models.SET_NULL,
        null=True, blank=True, help_text="Economic index used for adjustments"
    )
    adjustment_frequency = models.TextField(
        blank=True,
        help_text="RRULE string for adjustment recurrence"
    )
    adjustment_cap = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Maximum adjustment percentage per period (e.g., 10.00 = 10%)"
    )
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return f"Contract {self.contract_number} with {self.partner.name}"
    
    
    
class Invoice(TenantAwareBaseModel):
    INVOICE_TYPES = [('sale', 'Sale'), ('purchase', 'Purchase')]
    STATUS_CHOICES = [
        ('draft', 'Draft'), ('issued', 'Issued'),
        ('partially_paid', 'Partially Paid'), ('paid', 'Paid'),
        ('canceled', 'Canceled')
    ]

    partner = models.ForeignKey(BusinessPartner, on_delete=models.CASCADE)
    invoice_type = models.CharField(max_length=10, choices=INVOICE_TYPES)
    invoice_number = models.CharField(max_length=50)
    invoice_date = models.DateField()
    due_date = models.DateField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    currency = models.ForeignKey('accounting.Currency', on_delete=models.SET_NULL, null=True)
    total_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    tax_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    discount_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    recurrence_rule = models.TextField(blank=True, help_text="RRULE string for recurrence, e.g., FREQ=MONTHLY;INTERVAL=1")
    recurrence_start_date = models.DateField(null=True, blank=True)
    recurrence_end_date = models.DateField(null=True, blank=True)
    description = models.TextField(blank=True)
    
    def __str__(self):
        return f"Invoice {self.invoice_number} - {self.partner.name}"
    
    def update_totals(self):
        self.total_amount = sum(line.total_price for line in self.lines.all())
        self.tax_amount = sum(line.tax_amount for line in self.lines.all())
        self.save(update_fields=['total_amount', 'tax_amount'])
    
class InvoiceLine(TenantAwareBaseModel):
    invoice = models.ForeignKey(Invoice, related_name='lines', on_delete=models.CASCADE)
    product_service = models.ForeignKey(ProductService, on_delete=models.CASCADE)
    description = models.CharField(max_length=255, blank=True)
    quantity = models.DecimalField(max_digits=12, decimal_places=2, default=1)
    unit_price = models.DecimalField(max_digits=12, decimal_places=2)
    total_price = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    tax_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    def save(self, *args, **kwargs):
        self.total_price = self.quantity * self.unit_price
        super().save(*args, **kwargs)
        if self.invoice:
            self.invoice.update_totals()
            
    def delete(self, *args, **kwargs):
        invoice = self.invoice
        super().delete(*args, **kwargs)
        if invoice:
            invoice.update_totals()
            
    def __str__(self):
        return f"{self.product_service.name} - {self.quantity} x {self.unit_price}"