"""Servidor MCP sobre o Diário Oficial do Município de Mesquita/RJ."""

from .acervo import Acervo
from .servidor import construir

__all__ = ["Acervo", "construir"]
