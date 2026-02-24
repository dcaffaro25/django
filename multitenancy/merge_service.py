"""
Generic merge service: merge N source rows into one target row, reassign relations,
delete sources, and create SubstitutionRules for future ETL substitution.
"""
from django.apps import apps
from django.db import transaction
from django.db import models as dj_models

from .tasks import MODEL_APP_MAP
from .models import SubstitutionRule


class MergeError(Exception):
    """Raised when merge validation fails."""
    pass


def merge_rows_into_target(
    model_name: str,
    target_id: int,
    source_ids: list,
    company_id: int,
    dry_run: bool = False,
) -> dict:
    """
    Merge source rows into target row: reassign FKs and M2M, delete sources,
    create SubstitutionRules. Returns stats dict.

    Args:
        model_name: Model name (e.g. "Entity", "BusinessPartner").
        target_id: PK of the row to keep.
        source_ids: List of PKs to merge into target (will be deleted).
        company_id: Tenant company ID for scoping and SubstitutionRule.
        dry_run: If True, do not persist; return what would be done.

    Returns:
        {
            "merged_count": int,
            "rules_created": int,
            "relations_updated": { "ModelName": count, ... }
        }

    Raises:
        MergeError: On validation failure.
    """
    source_ids = list(source_ids)
    if not source_ids:
        raise MergeError("source_ids cannot be empty")

    if target_id in source_ids:
        raise MergeError("target_id must not be in source_ids")

    app_label = MODEL_APP_MAP.get(model_name)
    if not app_label:
        raise MergeError(f"Unknown model '{model_name}'. Valid models: {list(MODEL_APP_MAP.keys())}")

    model = apps.get_model(app_label, model_name)
    if model is None:
        raise MergeError(f"Could not load model '{model_name}'")

    # Build base queryset with company filter if applicable
    qs = model.objects.all()
    if hasattr(model, "company_id"):
        qs = qs.filter(company_id=company_id)
    elif hasattr(model, "company"):
        qs = qs.filter(company_id=company_id)

    # Validate target and sources exist and belong to company
    try:
        target = qs.get(pk=target_id)
    except model.DoesNotExist:
        raise MergeError(f"Target row with id={target_id} not found or does not belong to company")

    sources = list(qs.filter(pk__in=source_ids))
    found_ids = {s.pk for s in sources}
    missing = set(source_ids) - found_ids
    if missing:
        raise MergeError(f"Source row(s) with id(s) {sorted(missing)} not found or do not belong to company")

    relations_updated = {}

    def do_merge():
        nonlocal relations_updated
        for rel in model._meta.related_objects:
            if getattr(rel, "field", None) and not getattr(rel.field, "editable", True):
                continue
            if rel.many_to_many:
                count = _update_m2m_relation(model, rel, source_ids, target_id)
            else:
                # ForeignKey or OneToOne reverse
                count = _update_fk_relation(rel, source_ids, target_id)
            if count > 0:
                rel_model_name = rel.related_model.__name__
                relations_updated[rel_model_name] = relations_updated.get(rel_model_name, 0) + count

        # Delete source rows
        deleted = model.objects.filter(pk__in=source_ids).delete()
        # delete() returns (total_deleted, {Model: count}); we care about our model
        merged_count = deleted[1].get(model, len(source_ids))

        # Create SubstitutionRules
        rules_created = 0
        for sid in source_ids:
            exists = SubstitutionRule.objects.filter(
                company_id=company_id,
                model_name=model.__name__,
                field_name="id",
                match_value=str(sid),
                filter_conditions__isnull=True,
            ).exists()
            if not exists:
                SubstitutionRule.objects.create(
                    company_id=company_id,
                    model_name=model.__name__,
                    field_name="id",
                    match_type="exact",
                    match_value=str(sid),
                    substitution_value=str(target_id),
                    filter_conditions=None,
                    title=f"Merge: {sid} -> {target_id}",
                )
                rules_created += 1

        return {
            "merged_count": merged_count,
            "rules_created": rules_created,
            "relations_updated": relations_updated,
        }

    if dry_run:
        # Simulate: count what would be updated
        for rel in model._meta.related_objects:
            if rel.many_to_many:
                count = _count_m2m_relation(model, rel, source_ids)
            else:
                count = _count_fk_relation(rel, source_ids)
            if count > 0:
                rel_model_name = rel.related_model.__name__
                relations_updated[rel_model_name] = relations_updated.get(rel_model_name, 0) + count
        return {
            "merged_count": len(source_ids),
            "rules_created": len(source_ids),  # Would create one per source
            "relations_updated": relations_updated,
            "dry_run": True,
        }

    with transaction.atomic():
        return do_merge()


def _update_fk_relation(rel, source_ids, target_id):
    """Update reverse FK/OneToOne: set FK to target_id where FK in source_ids."""
    related_model = rel.related_model
    field = rel.field
    if not hasattr(field, "attname"):
        return 0
    attname = field.attname
    updated = related_model.objects.filter(**{f"{attname}__in": source_ids}).update(**{attname: target_id})
    return updated


def _count_fk_relation(rel, source_ids):
    """Count rows that would be updated for dry run."""
    related_model = rel.related_model
    field = rel.field
    if not hasattr(field, "attname"):
        return 0
    attname = field.attname
    return related_model.objects.filter(**{f"{attname}__in": source_ids}).count()


def _get_through_column_for_model(through_model, our_model):
    """Find the FK field in through_model that points to our_model."""
    for f in through_model._meta.fields:
        if isinstance(f, dj_models.ForeignKey):
            try:
                related = f.related_model
                if related == our_model:
                    return f.attname
            except Exception:
                continue
    return None


def _update_m2m_relation(our_model, rel, source_ids, target_id):
    """
    Update M2M through table: change rows where our model's FK is in source_ids
    to target_id. Handle duplicates by deleting rows that would create
    duplicate (other_side, target_id) after update.
    """
    field = getattr(rel, "field", None)
    if not field:
        return 0
    through_model = getattr(field, "through", None)
    if through_model is None:
        return 0
    our_col = _get_through_column_for_model(through_model, our_model)
    if not our_col:
        return 0

    # Find the other FK column (points to the "other" model)
    other_col = None
    for f in through_model._meta.fields:
        if isinstance(f, dj_models.ForeignKey) and f.attname != our_col:
            try:
                if f.related_model != our_model:
                    other_col = f.attname
                    break
            except Exception:
                continue

    # Strategy: update our_col from source_ids to target_id. This may create
    # duplicates if (other_id, target_id) already exists. So we:
    # 1) Update all through rows where our_col in source_ids to target_id
    # 2) Find duplicates: (other_col, our_col) pairs that appear more than once
    # 3) Keep one row per (other_col, our_col), delete the rest

    rows_to_update = through_model.objects.filter(**{f"{our_col}__in": source_ids})
    count_before = rows_to_update.count()
    if count_before == 0:
        return 0

    # Update to target_id
    rows_to_update.update(**{our_col: target_id})

    # Remove duplicates: if we have multiple rows with same (other_col, target_id),
    # keep one and delete the rest
    if other_col:
        from django.db.models import Count, Min

        # Find (other_col, our_col) groups with count > 1
        dupes = (
            through_model.objects.filter(**{our_col: target_id})
            .values(other_col)
            .annotate(cnt=Count("pk"), min_pk=Min("pk"))
            .filter(cnt__gt=1)
        )
        for d in dupes:
            # Delete all but the one with min pk
            through_model.objects.filter(**{other_col: d[other_col], our_col: target_id}).exclude(
                pk=d["min_pk"]
            ).delete()

    return count_before


def _count_m2m_relation(our_model, rel, source_ids):
    """Count through rows that would be updated for dry run."""
    field = getattr(rel, "field", None)
    if not field:
        return 0
    through_model = getattr(field, "through", None)
    if through_model is None:
        return 0
    our_col = _get_through_column_for_model(through_model, our_model)
    if not our_col:
        return 0
    return through_model.objects.filter(**{f"{our_col}__in": source_ids}).count()
