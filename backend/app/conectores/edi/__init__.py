"""Motor de EDI de largura fixa + layouts OCOREN (docs/edi/ocoren-integracao.md).

Não existe um adapter por versão do layout: um motor só (`motor.py`) lê a especificação de cada registro
como dado (`layouts/`); o que muda por parceiro é o perfil (`infra.models.ParceiroEdi`), nunca o código.
"""
