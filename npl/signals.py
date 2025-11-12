# npl/signals.py
from django.db.models.signals import pre_save
from django.dispatch import receiver
from django.conf import settings
from .models import SpanRule
from accounting.services.embedding_client import EmbeddingClient

@receiver(pre_save, sender=SpanRule)
def compute_anchor_embeddings(sender, instance: SpanRule, **kwargs):
    """
    Gera embeddings das âncoras fortes toda vez que a SpanRule é criada ou editada.
    - Se não houver âncoras fortes, apaga as embeddings.
    - Caso a lista de âncoras fortes ou o modelo tenha mudado, recalcule.
    """
    anchors = instance.strong_anchor_list()
    if not anchors:
        instance.anchor_embeddings = None
        return

    # se já há embeddings e o número de âncoras não mudou, não recalcula
    if instance.anchor_embeddings and len(instance.anchor_embeddings) == len(anchors):
        return

    # inicializa cliente com o modelo definido na rule ou nas settings
    client = EmbeddingClient(
        model=instance.embedding_model or settings.EMBED_MODEL,
        dim=settings.EMBED_DIM,
    )
    try:
        embeddings = client.embed_texts(anchors)
        instance.anchor_embeddings = embeddings
    except Exception as e:
        # Em caso de erro, registra e mantém o campo vazio
        import logging
        logger = logging.getLogger(__name__)
        logger.warning("Falha ao calcular embeddings para SpanRule %s: %s", instance, e)
        instance.anchor_embeddings = None
