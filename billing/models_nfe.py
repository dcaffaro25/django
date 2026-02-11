# -*- coding: utf-8 -*-
"""
Modelos Django para Nota Fiscal Eletrônica (NFe).
NotaFiscal = documento consolidado; NotaFiscalItem = produtos/serviços da NF.
"""
from django.db import models
from multitenancy.models import TenantAwareBaseModel


class NotaFiscal(TenantAwareBaseModel):
    """Nota Fiscal Eletrônica -- documento fiscal consolidado."""

    # ===== CHOICES (padrão SEFAZ) =====
    TIPO_OPERACAO = [(0, 'Entrada'), (1, 'Saída')]
    FINALIDADE = [(1, 'Normal'), (2, 'Complementar'), (3, 'Ajuste'), (4, 'Devolução')]
    MODELO = [(55, 'NF-e'), (65, 'NFC-e')]
    AMBIENTE = [(1, 'Produção'), (2, 'Homologação')]
    ID_DESTINO = [(1, 'Interna'), (2, 'Interestadual'), (3, 'Exterior')]
    IND_FINAL = [(0, 'Não'), (1, 'Consumidor Final')]
    IND_PRESENCA = [
        (0, 'Não se aplica'), (1, 'Presencial'), (2, 'Internet'),
        (3, 'Teleatendimento'), (4, 'Entrega domicílio'), (9, 'Outros'),
    ]
    MOD_FRETE = [
        (0, 'Emitente/Remetente'), (1, 'Destinatário'), (2, 'Terceiros'),
        (3, 'Próprio emitente'), (4, 'Próprio destinatário'), (9, 'Sem frete'),
    ]

    # ===== IDENTIFICAÇÃO =====
    chave = models.CharField('Chave de acesso', max_length=44, unique=True, db_index=True)
    numero = models.IntegerField('Número NF')
    serie = models.SmallIntegerField('Série', default=1)
    modelo = models.SmallIntegerField('Modelo', choices=MODELO, default=55)

    # ===== TIPO / FINALIDADE =====
    tipo_operacao = models.SmallIntegerField('Tipo operação', choices=TIPO_OPERACAO)
    finalidade = models.SmallIntegerField('Finalidade', choices=FINALIDADE, default=1)
    natureza_operacao = models.CharField('Natureza da operação', max_length=200)
    ambiente = models.SmallIntegerField('Ambiente', choices=AMBIENTE, default=1)
    id_destino = models.SmallIntegerField('Destino da operação', choices=ID_DESTINO, default=1)
    ind_final = models.SmallIntegerField('Consumidor final', choices=IND_FINAL, default=0)
    ind_presenca = models.SmallIntegerField('Presença do comprador', choices=IND_PRESENCA, default=9)

    # ===== DATAS =====
    data_emissao = models.DateTimeField('Data emissão', db_index=True)
    data_saida_entrada = models.DateTimeField('Data saída/entrada', null=True, blank=True)

    # ===== EMITENTE (dados desnormalizados + FK) =====
    emit_cnpj = models.CharField('CNPJ emitente', max_length=14, db_index=True)
    emit_nome = models.CharField('Razão social emitente', max_length=300)
    emit_fantasia = models.CharField('Nome fantasia emitente', max_length=300, blank=True)
    emit_ie = models.CharField('IE emitente', max_length=20, blank=True)
    emit_crt = models.CharField('CRT emitente', max_length=1, blank=True,
        help_text='1=Simples Nacional, 2=SN excesso, 3=Regime Normal')
    emit_uf = models.CharField('UF emitente', max_length=2)
    emit_municipio = models.CharField('Município emitente', max_length=100, blank=True)
    emitente = models.ForeignKey(
        'billing.BusinessPartner', null=True, blank=True,
        on_delete=models.SET_NULL, related_name='nfe_emitidas',
        verbose_name='Parceiro emitente',
        help_text='Vínculo automático por CNPJ com BusinessPartner.identifier'
    )

    # ===== DESTINATÁRIO (dados desnormalizados + FK) =====
    dest_cnpj = models.CharField('CNPJ/CPF destinatário', max_length=14, db_index=True)
    dest_nome = models.CharField('Razão social destinatário', max_length=300)
    dest_ie = models.CharField('IE destinatário', max_length=20, blank=True)
    dest_uf = models.CharField('UF destinatário', max_length=2, blank=True)
    dest_ind_ie = models.CharField('Indicador IE dest', max_length=1, blank=True,
        help_text='1=Contribuinte, 2=Isento, 9=Não contribuinte')
    destinatario = models.ForeignKey(
        'billing.BusinessPartner', null=True, blank=True,
        on_delete=models.SET_NULL, related_name='nfe_recebidas',
        verbose_name='Parceiro destinatário',
        help_text='Vínculo automático por CNPJ com BusinessPartner.identifier'
    )

    # ===== TOTAIS (campos queryáveis) =====
    valor_nota = models.DecimalField('Valor total NF', max_digits=15, decimal_places=2)
    valor_produtos = models.DecimalField('Valor produtos', max_digits=15, decimal_places=2)
    valor_icms = models.DecimalField('ICMS', max_digits=15, decimal_places=2, default=0)
    valor_icms_st = models.DecimalField('ICMS ST', max_digits=15, decimal_places=2, default=0)
    valor_ipi = models.DecimalField('IPI', max_digits=15, decimal_places=2, default=0)
    valor_pis = models.DecimalField('PIS', max_digits=15, decimal_places=2, default=0)
    valor_cofins = models.DecimalField('COFINS', max_digits=15, decimal_places=2, default=0)
    valor_frete = models.DecimalField('Frete', max_digits=15, decimal_places=2, default=0)
    valor_seguro = models.DecimalField('Seguro', max_digits=15, decimal_places=2, default=0)
    valor_desconto = models.DecimalField('Desconto', max_digits=15, decimal_places=2, default=0)
    valor_outras = models.DecimalField('Outras despesas', max_digits=15, decimal_places=2, default=0)
    valor_icms_uf_dest = models.DecimalField('ICMS UF destino', max_digits=15, decimal_places=2, default=0)
    valor_trib_aprox = models.DecimalField('Tributos aprox', max_digits=15, decimal_places=2, default=0)

    # ===== PROTOCOLO SEFAZ =====
    protocolo = models.CharField('Protocolo', max_length=20, blank=True)
    status_sefaz = models.CharField('Status SEFAZ', max_length=5, blank=True)
    motivo_sefaz = models.CharField('Motivo SEFAZ', max_length=300, blank=True)
    data_autorizacao = models.DateTimeField('Data autorização', null=True, blank=True)

    # ===== TRANSPORTE (JSONField) =====
    mod_frete = models.SmallIntegerField('Modalidade frete', choices=MOD_FRETE, default=9)
    transporte_json = models.JSONField('Transporte (detalhes)', default=dict, blank=True,
        help_text='{"transportadora": {...}, "volumes": [...]}')

    # ===== FINANCEIRO (JSONField) =====
    financeiro_json = models.JSONField('Financeiro', default=list, blank=True,
        help_text='[{"tipo": "duplicata", "nDup": "001", "dVenc": "...", "vDup": "..."}, ...]')

    # ===== REFERÊNCIAS (JSONField) =====
    referencias_json = models.JSONField('Referências', default=list, blank=True,
        help_text='["chave_44_digitos", ...]')

    # ===== TOTAIS COMPLETOS + OBSERVAÇÕES =====
    totais_json = models.JSONField('Totais completos ICMSTot', default=dict, blank=True)
    info_complementar = models.TextField('Info complementar', blank=True)
    info_fisco = models.TextField('Info ao fisco', blank=True)

    # ===== AUDITORIA =====
    xml_original = models.TextField('XML original', blank=True,
        help_text='Conteúdo bruto do XML para auditoria e reprocessamento')
    arquivo_origem = models.CharField('Arquivo de origem', max_length=500, blank=True)

    class Meta:
        verbose_name = 'Nota Fiscal Eletrônica'
        verbose_name_plural = 'Notas Fiscais Eletrônicas'
        ordering = ['-data_emissao']
        indexes = [
            models.Index(fields=['emit_cnpj', 'data_emissao']),
            models.Index(fields=['dest_cnpj', 'data_emissao']),
            models.Index(fields=['finalidade']),
        ]

    def __str__(self):
        return f"NF {self.numero} ({self.chave[-8:]}) - {self.emit_nome[:40]}"


class NotaFiscalItem(TenantAwareBaseModel):
    """Item (produto/serviço) de uma Nota Fiscal Eletrônica."""

    ORIGEM_MERCADORIA = [
        (0, 'Nacional'), (1, 'Estrangeira importação direta'),
        (2, 'Estrangeira mercado interno'), (3, 'Nacional 40-70% conteúdo importado'),
        (4, 'Nacional produção conforme'), (5, 'Nacional conteúdo importado < 40%'),
        (6, 'Estrangeira importação direta sem similar'), (7, 'Estrangeira mercado interno sem similar'),
        (8, 'Nacional conteúdo importado > 70%'),
    ]

    nota_fiscal = models.ForeignKey(
        NotaFiscal, related_name='itens', on_delete=models.CASCADE,
        verbose_name='Nota Fiscal'
    )
    numero_item = models.SmallIntegerField('N. item')

    # ===== PRODUTO (dados desnormalizados + FK) =====
    codigo_produto = models.CharField('Código produto (cProd)', max_length=60)
    ean = models.CharField('EAN/GTIN', max_length=14, blank=True)
    descricao = models.CharField('Descrição (xProd)', max_length=500)
    ncm = models.CharField('NCM', max_length=8, db_index=True)
    cest = models.CharField('CEST', max_length=7, blank=True)
    cfop = models.CharField('CFOP', max_length=4, db_index=True)
    unidade = models.CharField('Unidade (uCom)', max_length=6)
    quantidade = models.DecimalField('Quantidade', max_digits=15, decimal_places=4)
    valor_unitario = models.DecimalField('Valor unitário', max_digits=15, decimal_places=10)
    valor_total = models.DecimalField('Valor total item', max_digits=15, decimal_places=2)
    produto = models.ForeignKey(
        'billing.ProductService', null=True, blank=True,
        on_delete=models.SET_NULL, related_name='nfe_itens',
        verbose_name='Produto/Serviço cadastrado',
        help_text='Vínculo automático por codigo_produto vs ProductService.code ou EAN'
    )

    # ===== ICMS =====
    icms_origem = models.SmallIntegerField('Origem mercadoria', choices=ORIGEM_MERCADORIA, default=0)
    icms_cst = models.CharField('CST/CSOSN ICMS', max_length=4, blank=True,
        help_text='CST (regime normal) ou CSOSN (Simples Nacional)')
    icms_base = models.DecimalField('BC ICMS', max_digits=15, decimal_places=2, default=0)
    icms_aliquota = models.DecimalField('Alíquota ICMS %', max_digits=7, decimal_places=4, default=0)
    icms_valor = models.DecimalField('Valor ICMS', max_digits=15, decimal_places=2, default=0)
    icms_st_base = models.DecimalField('BC ICMS ST', max_digits=15, decimal_places=2, default=0)
    icms_st_valor = models.DecimalField('Valor ICMS ST', max_digits=15, decimal_places=2, default=0)

    # ===== PIS =====
    pis_cst = models.CharField('CST PIS', max_length=2, blank=True)
    pis_base = models.DecimalField('BC PIS', max_digits=15, decimal_places=2, default=0)
    pis_aliquota = models.DecimalField('Alíquota PIS %', max_digits=7, decimal_places=4, default=0)
    pis_valor = models.DecimalField('Valor PIS', max_digits=15, decimal_places=2, default=0)

    # ===== COFINS =====
    cofins_cst = models.CharField('CST COFINS', max_length=2, blank=True)
    cofins_base = models.DecimalField('BC COFINS', max_digits=15, decimal_places=2, default=0)
    cofins_aliquota = models.DecimalField('Alíquota COFINS %', max_digits=7, decimal_places=4, default=0)
    cofins_valor = models.DecimalField('Valor COFINS', max_digits=15, decimal_places=2, default=0)

    # ===== IPI =====
    ipi_cst = models.CharField('CST IPI', max_length=2, blank=True)
    ipi_valor = models.DecimalField('Valor IPI', max_digits=15, decimal_places=2, default=0)

    # ===== ICMS DIFAL =====
    icms_uf_dest_base = models.DecimalField('BC ICMS UF Dest', max_digits=15, decimal_places=2, default=0)
    icms_uf_dest_valor = models.DecimalField('Valor ICMS UF Dest', max_digits=15, decimal_places=2, default=0)
    icms_uf_remet_valor = models.DecimalField('Valor ICMS UF Remet', max_digits=15, decimal_places=2, default=0)

    # ===== IMPOSTOS COMPLETOS (JSONField) =====
    impostos_json = models.JSONField('Impostos (árvore completa)', default=dict, blank=True,
        help_text='Árvore XML completa de impostos para variantes não cobertas pelos campos flat')

    info_adicional = models.TextField('Info adicional do item', blank=True)

    class Meta:
        verbose_name = 'Item de Nota Fiscal'
        verbose_name_plural = 'Itens de Notas Fiscais'
        unique_together = ('nota_fiscal', 'numero_item')
        ordering = ['nota_fiscal', 'numero_item']
        indexes = [
            models.Index(fields=['ncm']),
            models.Index(fields=['cfop']),
        ]

    def __str__(self):
        return f"Item {self.numero_item}: {self.descricao[:50]}"


class NotaFiscalReferencia(TenantAwareBaseModel):
    """
    Vínculo explícito: uma NF referencia outra NF (ex.: devolução referencia a nota original).
    Permite consulta bidirecional: "quem esta NF referencia?" e "quais NFs referenciam esta?".
    A referência vem do XML (refNFe no grupo NFRef); ao importar, criamos estes registros
    e preenchemos nota_referenciada quando a NF referenciada já existir no sistema.
    """
    # NF que contém a referência no XML (a "nova" NF, ex.: devolução)
    nota_fiscal = models.ForeignKey(
        NotaFiscal,
        on_delete=models.CASCADE,
        related_name="referencias_a_outras_notas",
        verbose_name="Nota Fiscal (que referencia)",
    )
    # Chave da NF referenciada (sempre do XML; 44 dígitos para refNFe)
    chave_referenciada = models.CharField(
        "Chave NF referenciada", max_length=44, db_index=True,
        help_text="Chave de 44 dígitos (refNFe) da NF ao qual esta nota faz referência.",
    )
    # Vínculo à NF referenciada quando ela existir no sistema (encadeamento)
    nota_referenciada = models.ForeignKey(
        NotaFiscal,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="notas_que_me_referenciam",
        verbose_name="Nota referenciada (quando existir)",
        help_text="Preenchido quando já existe NotaFiscal com chave = chave_referenciada.",
    )

    class Meta:
        verbose_name = "Referência entre NFs"
        verbose_name_plural = "Referências entre NFs"
        ordering = ["nota_fiscal", "chave_referenciada"]
        constraints = [
            models.UniqueConstraint(
                fields=["company", "nota_fiscal", "chave_referenciada"],
                name="billing_nfref_company_nf_chave_uniq",
            ),
        ]
        indexes = [
            models.Index(fields=["chave_referenciada"]),
            models.Index(fields=["nota_referenciada"]),
        ]

    def __str__(self):
        return f"NF {self.nota_fiscal_id} → {self.chave_referenciada[-8:]}"


# Códigos de tipo de evento NFe (SEFAZ) para uso em choices e filtros
TP_EVENTO_CHOICES = [
    (110110, "Carta de Correção (CCe)"),
    (110111, "Cancelamento"),
    (110112, "Cancelamento por substituição"),
    (110140, "EPEC - Emissão em contingência"),
    (210200, "Manifestação: Confirmação da operação"),
    (210210, "Manifestação: Ciência da operação"),
    (210220, "Manifestação: Desconhecimento da operação"),
    (210240, "Manifestação: Operação não realizada"),
]


class NFeEvento(TenantAwareBaseModel):
    """
    Evento vinculado a uma NFe (cancelamento, CCe, manifestação do destinatário, etc.).
    Um mesmo documento pode ter vários eventos (ex.: autorização + CCe + manifestação).
    A chave da NFe identifica o documento; nota_fiscal é FK opcional quando a NF estiver importada.
    """
    # Vínculo à NF quando existir no sistema; chave sempre preenchida para busca
    nota_fiscal = models.ForeignKey(
        NotaFiscal, null=True, blank=True, on_delete=models.CASCADE,
        related_name="eventos", verbose_name="Nota Fiscal",
        help_text="Preenchido quando a NF foi importada; senão use chave_nfe.",
    )
    chave_nfe = models.CharField(
        "Chave NFe (44 dígitos)", max_length=44, db_index=True,
        help_text="Chave do documento fiscal ao qual o evento se refere.",
    )

    tipo_evento = models.PositiveIntegerField(
        "Tipo do evento", choices=TP_EVENTO_CHOICES, db_index=True,
        help_text="110110=CCe, 110111=Cancelamento, 210200=Confirmação, etc.",
    )
    n_seq_evento = models.PositiveSmallIntegerField(
        "Sequência do evento", default=1,
        help_text="Número sequencial do evento para a mesma NF (nSeqEvento).",
    )

    data_evento = models.DateTimeField("Data/hora do evento", null=True, blank=True, db_index=True)
    descricao = models.TextField(
        "Descrição / correção", blank=True,
        help_text="Para CCe: texto da correção (xCorrecao); para outros: xMotivo ou similar.",
    )

    # Retorno SEFAZ (quando disponível no XML de resposta)
    protocolo = models.CharField("Protocolo", max_length=20, blank=True)
    status_sefaz = models.CharField("Status SEFAZ", max_length=5, blank=True, db_index=True)
    motivo_sefaz = models.CharField("Motivo SEFAZ", max_length=500, blank=True)
    data_registro = models.DateTimeField("Data registro SEFAZ", null=True, blank=True)

    xml_original = models.TextField("XML original", blank=True)
    arquivo_origem = models.CharField("Arquivo de origem", max_length=500, blank=True)

    class Meta:
        verbose_name = "Evento NFe"
        verbose_name_plural = "Eventos NFe"
        ordering = ["chave_nfe", "data_evento", "n_seq_evento"]
        constraints = [
            models.UniqueConstraint(
                fields=["company", "chave_nfe", "tipo_evento", "n_seq_evento"],
                name="billing_nfeevento_company_chave_tipo_seq_uniq",
            ),
        ]
        indexes = [
            models.Index(fields=["tipo_evento", "chave_nfe"]),
            models.Index(fields=["status_sefaz"]),
        ]

    def __str__(self):
        return f"Evento {self.tipo_evento} NF {self.chave_nfe[-8:]} seq {self.n_seq_evento}"


class NFeInutilizacao(TenantAwareBaseModel):
    """
    Inutilização de numeração de NFe (ProcInutNFe).
    Não é evento sobre uma NF específica; invalida um intervalo de números (nNFIni a nNFFin)
    para uma série/ano/CNPJ.
    """
    cuf = models.CharField("UF", max_length=2, blank=True)
    ano = models.CharField("Ano (2 dígitos)", max_length=2, db_index=True)
    cnpj = models.CharField("CNPJ", max_length=14, db_index=True)
    modelo = models.SmallIntegerField("Modelo (55=NF-e)", default=55)
    serie = models.SmallIntegerField("Série", default=1)
    n_nf_ini = models.IntegerField("Número NF inicial")
    n_nf_fin = models.IntegerField("Número NF final")
    x_just = models.CharField("Justificativa", max_length=255)
    protocolo = models.CharField("Protocolo", max_length=20, blank=True)
    status_sefaz = models.CharField("Status SEFAZ", max_length=5, blank=True, db_index=True)
    motivo_sefaz = models.CharField("Motivo SEFAZ", max_length=500, blank=True)
    data_registro = models.DateTimeField("Data registro SEFAZ", null=True, blank=True)
    xml_original = models.TextField("XML original", blank=True)
    arquivo_origem = models.CharField("Arquivo de origem", max_length=500, blank=True)

    class Meta:
        verbose_name = "Inutilização NFe"
        verbose_name_plural = "Inutilizações NFe"
        ordering = ["-data_registro", "ano", "serie", "n_nf_ini"]
        constraints = [
            models.UniqueConstraint(
                fields=["company", "ano", "serie", "n_nf_ini", "n_nf_fin"],
                name="billing_nfeinut_company_ano_serie_ini_fin_uniq",
            ),
        ]

    def __str__(self):
        return f"Inut {self.ano}/S{self.serie} nNF {self.n_nf_ini}-{self.n_nf_fin}"
