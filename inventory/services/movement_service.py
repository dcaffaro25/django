# -*- coding: utf-8 -*-
"""
Movement service: NF-e ingestion to StockMovement, manual adjustments, inventory balance updates.
"""
import uuid
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from billing.models import NotaFiscal, NotaFiscalItem, ProductService
from billing.models_cfop import CFOP

from inventory.models import (
    StockMovement,
    UnitOfMeasure,
    UoMConversion,
    Warehouse,
    InventoryBalance,
)


def _get_or_create_uom(company, code):
    """Get or create UnitOfMeasure by code. Code is normalized (uppercase, stripped)."""
    code = (code or "UN").strip().upper()[:10]
    uom, _ = UnitOfMeasure.objects.get_or_create(
        company=company,
        code=code,
        defaults={"name": code},
    )
    return uom


def _resolve_quantity_in_base_uom(product, quantity, from_uom, company):
    """
    Convert quantity to base UoM (usually UN) if conversion exists.
    Returns (converted_qty, target_uom). If no conversion, returns original.
    """
    if from_uom.code.upper() == "UN":
        return quantity, from_uom
    # Try product-specific conversion first
    conv = UoMConversion.objects.filter(
        company=company,
        product=product,
        from_uom=from_uom,
    ).first()
    if not conv:
        conv = UoMConversion.objects.filter(
            company=company,
            product__isnull=True,
            from_uom=from_uom,
        ).first()
    if conv:
        base_uom = conv.to_uom
        converted = quantity * conv.factor
        return converted, base_uom
    return quantity, from_uom


def _determine_movement_type(nota_fiscal, nfe_item, cfop_obj):
    """
    Determine StockMovement.movement_type from NF tipo_operacao and CFOP grupo_analise.
    - compra -> inbound
    - venda -> outbound
    - devolucao + Entrada (0) -> return_in (customer returning to us)
    - devolucao + Saída (1) -> return_out (we returning to vendor)
    - outros/exportacao/prestacao_servico: use tipo_operacao (0=inbound, 1=outbound)
    """
    if cfop_obj:
        grupo = cfop_obj.grupo_analise or "outros"
    else:
        grupo = CFOP.grupo_from_codigo(nfe_item.cfop or "") if nfe_item.cfop else "outros"
    tipo_op = nota_fiscal.tipo_operacao  # 0=Entrada, 1=Saída

    if grupo == "compra":
        return "inbound"
    if grupo == "venda":
        return "outbound"
    if grupo == "devolucao":
        return "return_in" if tipo_op == 0 else "return_out"
    # outros, prestacao_servico, exportacao
    return "inbound" if tipo_op == 0 else "outbound"


def _get_default_warehouse(company):
    """Get default warehouse for company, or None (single-location)."""
    return Warehouse.objects.filter(company=company, is_active=True).first()


def _update_inventory_balance(company, product, warehouse, delta, movement_date):
    """Update or create InventoryBalance by delta. Delta is signed (+ for inbound, - for outbound)."""
    balance, created = InventoryBalance.objects.get_or_create(
        company=company,
        product=product,
        warehouse=warehouse,
        defaults={
            "on_hand_qty": Decimal("0"),
            "last_movement_date": None,
            "last_rebuilt_at": None,
        },
    )
    balance.on_hand_qty += delta
    balance.last_movement_date = movement_date
    balance.save(update_fields=["on_hand_qty", "last_movement_date", "updated_at"])


def ingest_nf_to_movements(company, nota_fiscal_id=None, nota_fiscal_ids=None):
    """
    Ingest NF-e items into StockMovement. Idempotent per nfe_item.
    Only processes items with produto (ProductService) where track_inventory=True and item_type='product'.

    Args:
        company: Company instance
        nota_fiscal_id: single NF id (optional)
        nota_fiscal_ids: list of NF ids (optional)

    Returns:
        dict: {created: int, skipped: int, errors: list}
    """
    ids = []
    if nota_fiscal_id:
        ids.append(nota_fiscal_id)
    if nota_fiscal_ids:
        ids.extend(nota_fiscal_ids)
    ids = list(set(ids))

    if not ids:
        nfs = NotaFiscal.objects.filter(company=company).order_by("data_emissao")
    else:
        nfs = NotaFiscal.objects.filter(company=company, id__in=ids).order_by("data_emissao")

    created = 0
    skipped = 0
    errors = []

    with transaction.atomic():
        for nf in nfs:
            mov_date = nf.data_saida_entrada or nf.data_emissao
            default_warehouse = _get_default_warehouse(company)

            for item in nf.itens.select_related("produto", "cfop_ref").all():
                product = item.produto
                if not product:
                    product = ProductService.objects.filter(
                        company=company,
                        code__in=[c for c in (item.codigo_produto, item.ean) if c],
                    ).first()
                if not product:
                    skipped += 1
                    continue
                if product.item_type != "product":
                    skipped += 1
                    continue
                if not product.track_inventory:
                    skipped += 1
                    continue

                idempotency_key = f"nfe_item:{item.id}"
                if StockMovement.objects.filter(company=company, idempotency_key=idempotency_key).exists():
                    skipped += 1
                    continue

                movement_type = _determine_movement_type(nf, item, item.cfop_ref)
                uom = _get_or_create_uom(company, item.unidade)

                qty = item.quantidade
                qty, target_uom = _resolve_quantity_in_base_uom(product, qty, uom, company)

                # Inbound-like: we receive, unit_cost = valor_unitario
                # Outbound-like: we send, unit_cost filled later by costing
                is_inbound_like = movement_type in ("inbound", "return_in")
                unit_cost = item.valor_unitario if is_inbound_like else None

                try:
                    movement = StockMovement.objects.create(
                        company=company,
                        movement_type=movement_type,
                        product=product,
                        warehouse=default_warehouse,
                        quantity=qty,
                        unit_cost=unit_cost,
                        uom=target_uom,
                        movement_date=mov_date,
                        source_type="nfe_item",
                        source_id=item.id,
                        nfe_item=item,
                        nota_fiscal=nf,
                        reference=f"NF {nf.numero}/{nf.serie}",
                        idempotency_key=idempotency_key,
                        metadata={
                            "nfe_chave": nf.chave,
                            "item_numero": item.numero_item,
                            "cfop": item.cfop,
                            "original_uom": item.unidade,
                        },
                    )
                    created += 1

                    # Update inventory balance
                    delta = qty if is_inbound_like else -qty
                    _update_inventory_balance(
                        company, product, default_warehouse, delta, mov_date
                    )
                except Exception as e:
                    errors.append(f"Item {item.id}: {e}")

    return {"created": created, "skipped": skipped, "errors": errors}


def create_manual_adjustment(company, product_id, quantity, unit_cost=None, warehouse_id=None, reference=""):
    """
    Create a manual stock adjustment. Quantity > 0 = inbound, < 0 = outbound (use absolute for movement).
    Returns (movement, error). Movement has positive quantity; type is adjustment.
    """
    from billing.models import ProductService

    product = ProductService.objects.filter(company=company, id=product_id).first()
    if not product:
        return None, "Product not found"
    if not product.track_inventory:
        return None, "Product does not track inventory"
    if quantity == 0:
        return None, "Quantity cannot be zero"

    warehouse = None
    if warehouse_id:
        warehouse = Warehouse.objects.filter(company=company, id=warehouse_id).first()

    uom = _get_or_create_uom(company, "UN")
    movement_type = "adjustment"
    qty_abs = abs(quantity)
    is_inbound = quantity > 0

    idempotency_key = f"manual:{uuid.uuid4().hex}"

    with transaction.atomic():
        movement = StockMovement.objects.create(
            company=company,
            movement_type=movement_type,
            product=product,
            warehouse=warehouse,
            quantity=qty_abs,
            unit_cost=unit_cost,
            uom=uom,
            movement_date=timezone.now(),
            source_type="manual_adjustment",
            reference=reference or "Manual adjustment",
            idempotency_key=idempotency_key,
            metadata={"direction": "in" if is_inbound else "out"},
        )
        delta = qty_abs if is_inbound else -qty_abs
        _update_inventory_balance(company, product, warehouse, delta, movement.movement_date)

    return movement, None
