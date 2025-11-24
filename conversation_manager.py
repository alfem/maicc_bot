"""
Gestor de conversaciones para el bot de Telegram.
Maneja el almacenamiento y recuperación de mensajes por usuario.
"""
import json
import os
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional
from memory_manager import MemoryManager
from logger_config import get_logger


class ConversationManager:
    """Gestiona las conversaciones de usuarios individuales."""

    def __init__(self, conversations_dir: str, max_context_messages: int = 20,
                 memory_manager: Optional[MemoryManager] = None):
        """
        Inicializa el gestor de conversaciones.

        Args:
            conversations_dir: Directorio donde se guardan las conversaciones
            max_context_messages: Número máximo de mensajes a mantener en contexto
            memory_manager: Gestor de memorias mem0 (opcional)
        """
        self.conversations_dir = Path(conversations_dir)
        self.conversations_dir.mkdir(parents=True, exist_ok=True)
        self.max_context_messages = max_context_messages
        self.memory_manager = memory_manager
        self.logger = get_logger('telegram')

    def _get_user_file(self, user_id: int) -> Path:
        """Obtiene la ruta del archivo de conversación de un usuario."""
        return self.conversations_dir / f"user_{user_id}.json"

    def _load_user_data(self, user_id: int) -> Dict:
        """Carga los datos de conversación de un usuario."""
        user_file = self._get_user_file(user_id)

        if user_file.exists():
            with open(user_file, 'r', encoding='utf-8') as f:
                return json.load(f)

        return {
            "user_id": user_id,
            "username": "",
            "first_name": "",
            "created_at": datetime.now().isoformat(),
            "messages": []
        }

    def _save_user_data(self, user_id: int, data: Dict):
        """Guarda los datos de conversación de un usuario."""
        user_file = self._get_user_file(user_id)

        with open(user_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def add_message(self, user_id: int, role: str, content: str,
                   username: str = "", first_name: str = "", mood_info: Optional[Dict] = None):
        """
        Añade un mensaje a la conversación de un usuario.

        Args:
            user_id: ID del usuario de Telegram
            role: 'user' o 'assistant'
            content: Contenido del mensaje
            username: Nombre de usuario de Telegram (opcional)
            first_name: Nombre del usuario (opcional)
            mood_info: Información del estado de ánimo del bot (opcional, solo para role='assistant')
        """
        data = self._load_user_data(user_id)

        # Actualizar información del usuario si está disponible
        if username:
            data["username"] = username
        if first_name:
            data["first_name"] = first_name

        # Añadir mensaje con timestamp
        message = {
            "role": role,
            "content": content,
            "timestamp": datetime.now().isoformat()
        }

        # Agregar información de mood si es un mensaje del asistente y hay mood disponible
        if role == "assistant" and mood_info:
            message["mood"] = mood_info

        data["messages"].append(message)

        self._save_user_data(user_id, data)

        # Guardar también en mem0 si está habilitado
        if self.memory_manager and self.memory_manager.enabled:
            # Enviar los últimos mensajes a mem0 para extracción de memorias
            # Tomamos un contexto más amplio para mejor extracción (últimos 10 mensajes)
            recent_messages = data["messages"][-10:]
            formatted_messages = [
                {"role": msg["role"], "content": msg["content"]}
                for msg in recent_messages
            ]
            self.memory_manager.add_conversation(user_id, formatted_messages)

    def get_context(self, user_id: int) -> List[Dict[str, str]]:
        """
        Obtiene el contexto reciente de conversación para enviar al LLM.

        Args:
            user_id: ID del usuario

        Returns:
            Lista de mensajes en formato {"role": "user/assistant", "content": "..."}
        """
        data = self._load_user_data(user_id)
        messages = data["messages"]

        # Tomar solo los últimos N mensajes para el contexto
        recent_messages = messages[-self.max_context_messages:]

        # Formatear para el LLM (sin timestamp)
        return [
            {"role": msg["role"], "content": msg["content"]}
            for msg in recent_messages
        ]

    def get_full_history(self, user_id: int) -> Dict:
        """Obtiene todo el historial de conversación de un usuario."""
        return self._load_user_data(user_id)

    def get_all_users(self) -> List[Dict]:
        """Obtiene información básica de todos los usuarios."""
        users = []

        for user_file in self.conversations_dir.glob("user_*.json"):
            try:
                with open(user_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)

                messages = data.get("messages", [])
                users.append({
                    "user_id": data["user_id"],
                    "username": data.get("username", ""),
                    "first_name": data.get("first_name", "Usuario"),
                    "created_at": data.get("created_at", ""),
                    "message_count": len(messages),
                    "last_message": messages[-1]["timestamp"] if messages else ""
                })
            except Exception as e:
                print(f"Error al leer {user_file}: {e}")

        # Ordenar por último mensaje (más reciente primero)
        users.sort(key=lambda x: x.get("last_message", ""), reverse=True)

        return users

    def get_messages_by_date(self, user_id: int, start_date: str, end_date: str) -> List[Dict]:
        """
        Obtiene mensajes de un usuario en un rango de fechas.

        Args:
            user_id: ID del usuario
            start_date: Fecha inicial en formato ISO (YYYY-MM-DD)
            end_date: Fecha final en formato ISO (YYYY-MM-DD)

        Returns:
            Lista de mensajes en el rango de fechas
        """
        data = self._load_user_data(user_id)
        messages = data["messages"]

        filtered_messages = []
        for msg in messages:
            msg_date = msg["timestamp"].split("T")[0]
            if start_date <= msg_date <= end_date:
                filtered_messages.append(msg)

        return filtered_messages

    def clear_user_history(self, user_id: int):
        """Elimina el historial de conversación de un usuario."""
        user_file = self._get_user_file(user_id)
        if user_file.exists():
            user_file.unlink()
