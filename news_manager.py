"""
Gestor de noticias RSS para el bot.
Consulta feeds RSS, almacena noticias y proporciona noticias aleatorias.
"""
import json
import random
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Optional
import feedparser

logger = logging.getLogger(__name__)


class NewsManager:
    """Gestiona la consulta y almacenamiento de noticias RSS."""

    def __init__(self, rss_feeds: List[str], storage_file: str = "./news_cache.json"):
        """
        Inicializa el gestor de noticias.

        Args:
            rss_feeds: Lista de URLs de feeds RSS
            storage_file: Archivo donde se almacenan las noticias en caché
        """
        self.rss_feeds = rss_feeds
        self.storage_file = Path(storage_file)
        self.news_cache = self._load_cache()

    def _load_cache(self) -> Dict:
        """Carga el caché de noticias desde el archivo."""
        if self.storage_file.exists():
            try:
                with open(self.storage_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"Error al cargar caché de noticias: {e}")
                return {"last_update": None, "news": []}
        return {"last_update": None, "news": []}

    def _save_cache(self):
        """Guarda el caché de noticias en el archivo."""
        try:
            with open(self.storage_file, 'w', encoding='utf-8') as f:
                json.dump(self.news_cache, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Error al guardar caché de noticias: {e}")

    def _should_update(self) -> bool:
        """
        Verifica si se debe actualizar el caché de noticias.
        Se actualiza una vez al día.

        Returns:
            True si debe actualizarse, False en caso contrario
        """
        last_update = self.news_cache.get("last_update")

        if not last_update:
            return True

        try:
            last_update_date = datetime.fromisoformat(last_update)
            now = datetime.now()

            # Actualizar si pasó más de un día
            return (now - last_update_date) >= timedelta(days=1)
        except Exception as e:
            logger.error(f"Error al verificar fecha de actualización: {e}")
            return True

    def _parse_feed(self, feed_url: str) -> List[Dict]:
        """
        Parsea un feed RSS y extrae las noticias.

        Args:
            feed_url: URL del feed RSS

        Returns:
            Lista de noticias con título, descripción, link y fecha
        """
        news_items = []

        try:
            logger.info(f"Consultando feed RSS: {feed_url}")
            feed = feedparser.parse(feed_url)

            if feed.bozo:
                logger.warning(f"Error al parsear feed {feed_url}: {feed.bozo_exception}")

            for entry in feed.entries[:10]:  # Tomar las 10 noticias más recientes
                news_item = {
                    "title": entry.get("title", "Sin título"),
                    "description": entry.get("summary", entry.get("description", "")),
                    "link": entry.get("link", ""),
                    "published": entry.get("published", entry.get("updated", "")),
                    "source": feed.feed.get("title", feed_url)
                }

                # Limpiar HTML de la descripción si existe
                if news_item["description"]:
                    # Remover etiquetas HTML básicas
                    import re
                    news_item["description"] = re.sub(r'<[^>]+>', '', news_item["description"])
                    # Limitar longitud de descripción
                    if len(news_item["description"]) > 500:
                        news_item["description"] = news_item["description"][:497] + "..."

                news_items.append(news_item)

            logger.info(f"Se obtuvieron {len(news_items)} noticias de {feed_url}")

        except Exception as e:
            logger.error(f"Error al consultar feed {feed_url}: {e}")

        return news_items

    def update_news(self) -> bool:
        """
        Actualiza el caché de noticias consultando todos los feeds RSS.

        Returns:
            True si se actualizó correctamente, False en caso contrario
        """
        if not self._should_update():
            logger.info("El caché de noticias está actualizado, no es necesario consultar")
            return True

        logger.info("Actualizando caché de noticias...")
        all_news = []

        for feed_url in self.rss_feeds:
            news_items = self._parse_feed(feed_url)
            all_news.extend(news_items)

        if all_news:
            self.news_cache["news"] = all_news
            self.news_cache["last_update"] = datetime.now().isoformat()
            self._save_cache()
            logger.info(f"Caché actualizado con {len(all_news)} noticias")
            return True
        else:
            logger.warning("No se pudieron obtener noticias de ningún feed")
            return False

    def get_random_news(self) -> Optional[Dict]:
        """
        Obtiene una noticia al azar del caché.

        Returns:
            Diccionario con la noticia o None si no hay noticias disponibles
        """
        # Intentar actualizar si es necesario
        self.update_news()

        news_list = self.news_cache.get("news", [])

        if not news_list:
            logger.warning("No hay noticias disponibles en el caché")
            return None

        return random.choice(news_list)

    def format_news_for_conversation(self, news: Dict) -> str:
        """
        Formatea una noticia para ser usada en una conversación.

        Args:
            news: Diccionario con la información de la noticia

        Returns:
            Texto formateado de la noticia
        """
        if not news:
            return ""

        formatted = f"📰 {news['title']}\n\n"

        if news.get('description'):
            formatted += f"{news['description']}\n\n"

        if news.get('source'):
            formatted += f"Fuente: {news['source']}\n"

        if news.get('link'):
            formatted += f"Más información: {news['link']}"

        return formatted

    def get_news_count(self) -> int:
        """Retorna el número de noticias en caché."""
        return len(self.news_cache.get("news", []))

    def get_last_update(self) -> Optional[str]:
        """Retorna la fecha de la última actualización."""
        return self.news_cache.get("last_update")
