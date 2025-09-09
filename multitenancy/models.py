# NORD/multitenancy/models.py
from django.apps import apps
from django.db import models
from django.contrib.auth.models import AbstractUser
from mptt.models import MPTTModel, TreeForeignKey
from django.utils.text import slugify
from django.utils import timezone
from django.conf import settings
from .managers import TenantAwareManager
from django.core.exceptions import ValidationError
#from accounting.models import Account, CostCenter
import datetime
from crum import get_current_user
#from jsonfield import JSONField
from django.db.models import JSONField

class CustomUser(AbstractUser):
    # Add any additional fields here
    must_change_password = models.BooleanField(default=False)
    email_last_sent_at = models.DateTimeField(null=True, blank=True)

    def mark_email_sent(self):
        """Helper to update timestamp when an email is sent to the user"""
        self.email_last_sent_at = timezone.now()
        self.save(update_fields=["email_last_sent_at"])
    #pass

def company_icon_upload_path(instance, filename):
    return f'company_icons/{instance.subdomain}/{filename}'

class BaseModel(models.Model):

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name="%(class)s_created_by"
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name="%(class)s_updated_by"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now_add=True)
    is_deleted = models.BooleanField(default=False)

    class Meta:
        abstract = True
        
    def save(self, *args, **kwargs):
        # Use django-crum to retrieve the current user.
        current_user = get_current_user()
        # If this is a new record and created_by is not set, assign the current user.
        if not self.pk and not self.created_by:
            if current_user and current_user.is_authenticated:
                self.created_by = current_user
        # Always update updated_by.
        if current_user and current_user.is_authenticated:
            self.updated_by = current_user
        super().save(*args, **kwargs)

# Company model representing each tenant
class Company(BaseModel):
    name = models.CharField(max_length=100, unique=True)
    subdomain = models.CharField(max_length=100, unique=True)
    #icon = models.FileField(upload_to=company_icon_upload_path ,null=True, blank=True)
    # Additional fields like address, contact details, etc.

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        # If the subdomain is not manually set, generate it from the company name
        if not self.subdomain:
           # Generate the initial slug from the company name
            original_slug = slugify(self.name)
            unique_slug = original_slug
            num = 1

            # Keep incrementing the number appended to the slug until it is unique
            while Company.objects.filter(subdomain=unique_slug).exclude(pk=self.pk).exists():
                unique_slug = f"{original_slug}-{num}"
                num += 1

            self.subdomain = unique_slug
        else:
            # Ensure manually set subdomain is slugified and unique
            self.subdomain = slugify(self.subdomain)
            if Company.objects.filter(subdomain=self.subdomain).exclude(pk=self.pk).exists():
                raise ValueError("The subdomain must be unique.")
        
        super().save(*args, **kwargs)

class TenantAwareBaseModel(BaseModel):
    company = models.ForeignKey(
        'multitenancy.Company',
        on_delete=models.CASCADE,
        related_name="%(class)s_company"
    )
    
    company_coherence_fields = []  # List of related fields to check for coherence
    
    objects = TenantAwareManager()  # Use TenantAwareManager by default
    
    class Meta:
        abstract = True
    
    @classmethod
    def get_company_coherence_fields(cls):
        """
        Automatically detect related fields that have a 'company' ForeignKey.
        """
        coherence_fields = []
        for field in cls._meta.fields:
            if isinstance(field, models.ForeignKey):
                related_model = field.related_model
                if related_model and hasattr(related_model, 'company'):
                    coherence_fields.append(field.name)
        return coherence_fields
    
    def clean(self):
        """
        Ensure coherence between company references in related models.
        """
        
        coherence_fields = self.get_company_coherence_fields()
        
        for field in coherence_fields:
            related_obj = getattr(self, field, None)
            if related_obj and related_obj.company != self.company:
                raise ValidationError(
                    f"The company field must match the company of the related '{field}'."
                )
        super().clean()
    
# Entity model representing the hierarchical organizational structure
class Entity(TenantAwareBaseModel, MPTTModel):
    company = models.ForeignKey(Company, related_name='entities', on_delete=models.CASCADE)
    name = models.CharField(max_length=100)
    parent = TreeForeignKey('self', null=True, blank=True, related_name='children', on_delete=models.CASCADE)
    accounts = models.ManyToManyField('accounting.Account', related_name='entities', blank=True, default=None)
    cost_centers = models.ManyToManyField('accounting.CostCenter', related_name='entities', blank=True, default=None)
    
    inherit_accounts = models.BooleanField(default=True)  # Inherit accounts from parent
    inherit_cost_centers = models.BooleanField(default=True)  # Inherit cost centers from parent

    def __str__(self):
        return self.name
    
    class Meta:
        unique_together = ('company', 'name')

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
    
    def get_available_accounts(self, leaf_only=False):
        """
        Returns the set of accounts available to the entity based on inheritance chain.
        """
        Account = apps.get_model('accounting', 'Account')
    
        current = self
    
        # Subir até o primeiro que NÃO herda
        while current.parent and current.inherit_accounts:
            current = current.parent

        # Se chegamos na raiz E ela herda, usamos contas do nível da empresa
        if not current.parent:
            print(f"[DEBUG] Using company-level accounts for entity {self.id}")
            qs = Account.objects.filter(company_id=self.company_id)

        else:
            print(f"[DEBUG] Using explicitly assigned accounts of entity {current.id}")
            qs = current.parent.accounts.all()
    
        if leaf_only:
            before = qs.count()
            qs = qs.filter(is_leaf_node=True)
            after = qs.count()
            print(f"[DEBUG] Leaf-only filter: before={before}, after={after}")
    
        return qs
    
    def get_available_cost_centers(self, leaf_only=False):
        """
        Recursively fetch cost centers from the highest ancestor that does not inherit from its parent.
        If all ancestors inherit, fall back to the company's directly assigned cost centers.
        All cost centers returned should be considered selected if the entity inherits.
        """
        CostCenter = apps.get_model('accounting', 'CostCenter')
    
        #if not self.inherit_cost_centers:
        #    return self.cost_centers.all()
    
        current = self
        while current.parent and current.inherit_cost_centers:
            current = current.parent

        # Se chegamos na raiz E ela herda, usamos contas do nível da empresa
        if not current.parent:
            print(f"[DEBUG] Using company-level cost-centers for entity {self.id}")
            qs = CostCenter.objects.filter(company_id=self.company_id)

        else:
            print(f"[DEBUG] Using explicitly assigned accounts of entity {current.id}")
            qs = current.parent.cost_centers.all()
    
        if leaf_only:
            before = qs.count()
            qs = qs.filter(is_leaf_node=True)
            after = qs.count()
            print(f"[DEBUG] Leaf-only filter: before={before}, after={after}")
    
        return qs
    
    class MPTTMeta:
        order_insertion_by = ['name']   
        


class IntegrationRule(TenantAwareBaseModel):
    MODULE_CHOICES = [
        ('hr', 'Human Resources'),
        ('accounting', 'Accounting'),
    ]
    TRIGGER_CHOICES = [
        ('payroll_approved', 'Payroll Approved'),
        ('payroll_created', 'Payroll Created'),
        # Add more triggers
    ]

    name = models.CharField(max_length=100)
    description = models.TextField(blank=True, null=True)
    trigger_event = models.CharField(max_length=50, choices=TRIGGER_CHOICES)
    execution_order = models.PositiveIntegerField(default=0)
    filter_conditions = models.TextField(
        blank=True,
        null=True,
        help_text="Python expression for filtering payload records. Example: \"record['department'] == 'HR' and record['base_salary'] > 3000\""
    )
    rule = models.TextField(help_text="Formula engine code to execute.")
    use_celery = models.BooleanField(default=True)
    is_active = models.BooleanField(default=True)
    
    # Optional fields for quick stats:
    last_run_at = models.DateTimeField(blank=True, null=True)
    times_executed = models.PositiveIntegerField(default=0)

    def __str__(self):
        return f"{self.name} ({self.trigger_event} → {self.target_module})"
    
    def apply_filter(self, payload):
        """
        Apply filter_conditions using the formula engine.
        """
        if not self.filter_conditions:
            return payload

        return [record for record in payload if self.evaluate_filter(record)]
    
    def evaluate_filter(self, record):
        """
        Evaluate a Python expression for filtering.
        """
        from multitenancy.formula_engine import evaluate_expression

        context = {"record": record}
        try:
            return evaluate_expression(self.filter_conditions, context)
        except Exception as e:
            raise ValueError(f"Filter evaluation error: {e}")
    
    def run_rule(self, payload):
        """
        Execute the rule using your formula engine. 
        Logs the execution in an IntegrationRuleLog for auditing.
        """
        from multitenancy.formula_engine import execute_rule
        
        if not self.is_active:
            raise ValueError(f"Rule '{self.name}' is inactive; cannot execute.")
        
        # 1) Attempt to run
        try:
            filtered_payload = self.apply_filter(payload)
            #filtered_payload = apply_substitutions(filtered_payload, self.company_id)
            result = execute_rule(self.company.id, self.rule, filtered_payload)  # formula engine call
            self.last_run_at = timezone.now()
            self.times_executed += 1
            self.save(update_fields=['last_run_at', 'times_executed'])
            success = True
        except Exception as e:
            # 2) Possibly capture the error message
            result = str(e)
            success = False

        #print('# 3) Create a log entry')
        IntegrationRuleLog.objects.create(
            company=self.company,
            rule=self,
            payload=payload,          # or json.dumps(payload)
            result=result,
            success=success
        )
        print('IntegrationRuleLog-Multitenancy-Result',result)
        # 4) Update optional counters/stats
        if success:
            self.times_executed += 1
            self.last_run_at = timezone.now()
            self.save(update_fields=['times_executed', 'last_run_at'])

        if not success:
            # you could raise or return result. 
            # let's raise, so the caller sees the error
            raise ValueError(f"Rule run failed: {result}")

        return {"result": result, "success": True}

class IntegrationRuleLog(TenantAwareBaseModel):
    """
    Audit log for each time an IntegrationRule is executed.
    """
    rule = models.ForeignKey(
        IntegrationRule,
        on_delete=models.CASCADE,
        related_name="executions"
    )

    payload = models.JSONField(blank=True, null=True)
    result = models.TextField(blank=True, null=True)
    success = models.BooleanField(default=False)

    def __str__(self):
        return f"[{self.executed_at}] {self.rule.name} => {'OK' if self.success else 'FAIL'}"
    
class SubstitutionRule(TenantAwareBaseModel):
    """
    Define regras de substituição (de‑para) para limpar e padronizar dados.

    - `model_name` e `field_name`: aplicam a regra a instâncias de um modelo específico.
    - `column_name`: aplica a regra quando o payload é um dicionário (ex.: linha de CSV), usando a chave/coluna informada.
    - `column_index`: aplica a regra quando o payload é uma lista/tupla, usando o índice indicado (zero‑based).
    Pelo menos um desses alvos deve ser definido.

    O campo `match_type` controla o tipo de comparação:
    - `exact` (padrão) – igualdade direta.
    - `regex` – usa expressões regulares para substituir (`re.sub`).
    - `caseless` – comparação sem diferenciar maiúsculas/minúsculas nem acentuação.
    """
    # NOVO: título/descrição legível da regra, usado em relatórios
    title = models.CharField(max_length=255, null=True, blank=True)
    model_name = models.CharField(max_length=255, null=True, blank=True)
    field_name = models.CharField(max_length=255, null=True, blank=True)
    column_name = models.CharField(max_length=255, null=True, blank=True)
    column_index = models.PositiveIntegerField(null=True, blank=True)

    match_type = models.CharField(
        max_length=50,
        choices=[('exact', 'Exact'),
                 ('regex', 'Regex'),
                 ('caseless', 'Case/Accent Insensitive')],
        default='exact',
        help_text=(
            "Tipo de comparação:\n"
            "- 'exact': igualdade direta.\n"
            "- 'regex': usa re.sub.\n"
            "- 'caseless': ignora maiúsculas/minúsculas e acentuação."
        ),
    )
    match_value = models.TextField()
    substitution_value = models.TextField()
    filter_conditions = JSONField(null=True, blank=True)

    
    
    class Meta:
        unique_together = (
            'company',
            'model_name',
            'field_name',
            'column_name',
            'column_index',
            'match_value',
        )

    def clean(self):
        super().clean()
        if not (self.field_name or self.column_name or self.column_index is not None):
            raise ValidationError(
                "Defina ao menos um alvo (field_name, column_name ou column_index)."
            )

    def __str__(self):
        if self.model_name and self.field_name:
            target = f"{self.model_name}.{self.field_name}"
        elif self.column_name:
            target = f"[col:{self.column_name}]"
        elif self.column_index is not None:
            target = f"[idx:{self.column_index}]"
        else:
            target = "<unspecified>"
        return f"Regra {self.id} – {self.title}_{target}: {self.match_value} -> {self.substitution_value}"

