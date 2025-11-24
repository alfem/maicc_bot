"""
Gestor de memorias usando mem0 para el bot de Telegram.
Proporciona almacenamiento semántico de conversaciones y recuperación basada en relevancia.
"""
import os
from typing import List, Dict, Optional
from logger_config import get_logger


class MemoryManager:
    """Gestiona las memorias usando mem0 para almacenamiento semántico."""

    def __init__(self, config: Dict, enabled: bool = True):
        """
        Inicializa el gestor de memorias con mem0.

        Args:
            config: Configuración de mem0 (vector_store, llm, embedder)
            enabled: Si está habilitado el sistema de memorias
        """
        self.enabled = enabled
        self.memory = None
        self.logger = get_logger('telegram')

        if not self.enabled:
            self.logger.info("MemoryManager deshabilitado en configuración")
            return

        try:
            # Importar mem0 solo si está habilitado
            from mem0 import Memory

            # Verificar que GOOGLE_API_KEY esté configurada
            # mem0 la busca automáticamente en las variables de entorno
            if not os.getenv('GOOGLE_API_KEY'):
                self.logger.error("GOOGLE_API_KEY no está configurada. mem0 no funcionará correctamente.")
                self.enabled = False
                return

            # Inicializar mem0 con la configuración
            self.memory = Memory.from_config(config)
            self.logger.info("MemoryManager inicializado correctamente con mem0")

        except ImportError:
            self.logger.error("mem0ai no está instalado. Ejecuta: pip install mem0ai")
            self.enabled = False
        except Exception as e:
            self.logger.error(f"Error al inicializar MemoryManager: {e}", exc_info=True)
            self.enabled = False

    def add_conversation(self, user_id: int, messages: List[Dict[str, str]]) -> bool:
        """
        Añade mensajes de conversación a mem0 para extracción de memorias.

        Args:
            user_id: ID del usuario de Telegram
            messages: Lista de mensajes en formato [{"role": "user/assistant", "content": "..."}]

        Returns:
            True si se añadió correctamente, False en caso contrario
        """
        if not self.enabled or not self.memory:
            self.logger.debug(f"mem0 deshabilitado, no se añade conversación para usuario {user_id}")
            return False

        try:
            # mem0 espera el user_id como string
            user_id_str = str(user_id)

            self.logger.info(f"Añadiendo {len(messages)} mensajes a mem0 para usuario {user_id}")

            # Añadir los mensajes a mem0
            # mem0 extraerá automáticamente los hechos importantes usando el LLM configurado
            result = self.memory.add(messages, user_id=user_id_str)

            self.logger.info(f"Conversación añadida a mem0 para usuario {user_id}. Resultado: {result}")
            return True

        except Exception as e:
            self.logger.error(f"Error al añadir conversación a mem0: {e}", exc_info=True)
            return False

    def get_relevant_memories(self, user_id: int, query: str, limit: int = 5) -> List[Dict]:
        """
        Recupera memorias relevantes para una consulta específica.

        Args:
            user_id: ID del usuario de Telegram
            query: Consulta o texto para buscar memorias relevantes
            limit: Número máximo de memorias a recuperar

        Returns:
            Lista de memorias relevantes con formato:
            [{"id": "...", "memory": "...", "score": 0.9, ...}, ...]
        """
        if not self.enabled or not self.memory:
            return []

        try:
            user_id_str = str(user_id)

            # Buscar memorias relevantes usando filtros por user_id
            results = self.memory.search(
                query=query,
                user_id=user_id_str,
                limit=limit
            )

            # mem0 devuelve un dict con "results" que contiene la lista de memorias
            memories = results.get("results", []) if isinstance(results, dict) else results

            self.logger.debug(f"Recuperadas {len(memories)} memorias para usuario {user_id}")
            return memories

        except Exception as e:
            self.logger.error(f"Error al recuperar memorias de mem0: {e}", exc_info=True)
            return []

    def get_all_memories(self, user_id: int) -> List[Dict]:
        """
        Recupera todas las memorias almacenadas para un usuario.

        Args:
            user_id: ID del usuario de Telegram

        Returns:
            Lista de todas las memorias del usuario
        """
        if not self.enabled or not self.memory:
            return []

        try:
            user_id_str = str(user_id)

            # Obtener todas las memorias del usuario
            memories = self.memory.get_all(user_id=user_id_str)

            # mem0 devuelve un dict con "results"
            results = memories.get("results", []) if isinstance(memories, dict) else memories

            self.logger.debug(f"Recuperadas todas las memorias ({len(results)}) para usuario {user_id}")
            return results

        except Exception as e:
            self.logger.error(f"Error al recuperar todas las memorias: {e}", exc_info=True)
            return []

    def delete_memory(self, memory_id: str) -> bool:
        """
        Elimina una memoria específica por su ID.

        Args:
            memory_id: ID de la memoria a eliminar

        Returns:
            True si se eliminó correctamente, False en caso contrario
        """
        if not self.enabled or not self.memory:
            return False

        try:
            self.memory.delete(memory_id=memory_id)
            self.logger.info(f"Memoria {memory_id} eliminada")
            return True

        except Exception as e:
            self.logger.error(f"Error al eliminar memoria: {e}", exc_info=True)
            return False

    def delete_all_memories(self, user_id: int) -> bool:
        """
        Elimina todas las memorias de un usuario.

        Args:
            user_id: ID del usuario de Telegram

        Returns:
            True si se eliminaron correctamente, False en caso contrario
        """
        if not self.enabled or not self.memory:
            return False

        try:
            user_id_str = str(user_id)
            self.memory.delete_all(user_id=user_id_str)
            self.logger.info(f"Todas las memorias eliminadas para usuario {user_id}")
            return True

        except Exception as e:
            self.logger.error(f"Error al eliminar memorias: {e}", exc_info=True)
            return False

    def format_memories_for_context(self, memories: List[Dict]) -> str:
        """
        Formatea las memorias recuperadas para incluir en el contexto del LLM.

        Args:
            memories: Lista de memorias de mem0

        Returns:
            String formateado con las memorias para inyectar en el prompt
        """
        if not memories:
            return ""

        formatted = "### Memorias relevantes del usuario:\n"
        for mem in memories:
            memory_text = mem.get("memory", "")
            score = mem.get("score", 0)
            formatted += f"- {memory_text} (relevancia: {score:.2f})\n"

        return formatted
