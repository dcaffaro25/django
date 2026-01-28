"""
Build ERP API request payloads.

Produces JSON in the form:
  {"call": "ListarContasPagar", "param": [{...}], "app_key": "...", "app_secret": "..."}
"""

import copy
from typing import Any, Dict, List, Optional

from erp_integrations.models import ERPAPIDefinition, ERPConnection


def build_payload(
    connection: ERPConnection,
    api_definition: ERPAPIDefinition,
    param_overrides: Optional[Dict[str, Any]] = None,
    param_list: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """
    Build the request payload for an ERP API call.

    Args:
        connection: ERP connection (app_key, app_secret).
        api_definition: API call + default_param.
        param_overrides: Override keys in the default param object. If the API
            uses a single param object (e.g. ListarContasPagar), we merge this
            into default_param and emit param: [merged].
        param_list: If provided, use this as param directly (list of objects).
            Otherwise we use default_param merged with param_overrides as
            param: [merged].

    Returns:
        Dict with "call", "param", "app_key", "app_secret".
    """
    if param_list is not None:
        param = param_list
    else:
        base = copy.deepcopy(api_definition.default_param) or {}
        overrides = param_overrides or {}
        merged = {**base, **overrides}
        param = [merged]

    return {
        "call": api_definition.call,
        "param": param,
        "app_key": connection.app_key,
        "app_secret": connection.app_secret,
    }


def build_payload_by_ids(
    connection_id: int,
    api_definition_id: int,
    param_overrides: Optional[Dict[str, Any]] = None,
    param_list: Optional[List[Dict[str, Any]]] = None,
    company_id: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Build payload by connection and API definition IDs.

    Optionally restrict connection to a specific company.
    """
    qs = ERPConnection.objects.filter(pk=connection_id, is_active=True)
    if company_id is not None:
        qs = qs.filter(company_id=company_id)
    connection = qs.select_related("provider").get()

    api_def = ERPAPIDefinition.objects.filter(
        pk=api_definition_id,
        provider=connection.provider,
        is_active=True,
    ).get()

    return build_payload(
        connection=connection,
        api_definition=api_def,
        param_overrides=param_overrides,
        param_list=param_list,
    )
