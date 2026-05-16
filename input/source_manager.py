import json
import os
from input.video_source import VideoSource


class SourceManager:
    def __init__(self, config_file: str = "config/sources.json"):
        self.config_file = config_file
        self.sources = {}
        self.active_source_id = None
        self.load_config()

    def load_config(self):
        if not os.path.exists(self.config_file):
            self._create_default_config()
            return

        try:
            with open(self.config_file, "r", encoding="utf-8") as f:
                data = json.load(f)

            for src_data in data.get("sources", []):
                if src_data.get("enabled", True):
                    source = VideoSource(
                        source_id=src_data.get("id"),
                        name=src_data.get("name"),
                        source_path=src_data.get("path"),
                    )
                    self.sources[src_data.get("id")] = source

            print(f"Загружено {len(self.sources)} источников видео")

        except Exception as e:
            print(f"Ошибка загрузки: {e}")

    def _create_default_config(self):
        os.makedirs('config', exist_ok=True)
        default_config = {
            "sources": [
                {
                    "id": 1,
                    "name": "USB камера 0",
                    "path": 0,
                    "enabled": True,
                    "type": "usb"
                }
            ]
        }
        with open(self.config_file, "w", encoding="utf-8") as f:
            json.dump(default_config, f, ensure_ascii=False, indent=2)

    def connect_all(self):
        for source in self.sources.values():
            if source.connect():
                source.start_capture()
        print(f"Запущено источников: {len(self.sources)}")

    def connect_source(self, source_id):
        if source_id in self.sources:
            if self.sources[source_id].connect():
                self.sources[source_id].start_capture()
                return True
        return False

    def get_source(self, source_id):
        return self.sources.get(source_id)

    def get_active_source(self):
        if self.active_source_id is not None:
            return self.sources.get(self.active_source_id)
        return None

    def set_active_source(self, source_id):
        if source_id in self.sources:
            self.active_source_id = source_id
            print(f"Активный источник: {self.sources[source_id].name}")

    def get_all_sources(self):
        return list(self.sources.values())

    def get_sources_list(self):
        result = []
        for src in self.sources.values():
            result.append({
                'id': src.source_id,
                'name': src.name,
                'connected': src.is_connected,
                'path': src.source_path
            })
        return result

    def stop_all(self):
        for source in self.sources.values():
            source.stop()

    def add_ip_source(self, name, path):
        if self.sources:
            new_id = max(self.sources.keys()) + 1
        else:
            new_id = 1
        source = VideoSource(new_id, name, path)
        self.sources[new_id] = source
        self._save_config()
        return new_id

    def remove_source(self, source_id):
        if source_id in self.sources:
            self.sources[source_id].stop()
            del self.sources[source_id]
            if self.active_source_id == source_id:
                self.active_source_id = None
            self._save_config()

    def _save_config(self):
        data = {"sources": []}
        for src in self.sources.values():
            data["sources"].append({
                "id": src.source_id,
                "name": src.name,
                "path": src.source_path,
                "enabled": True,
                "type": "usb" if isinstance(src.source_path, int) else "ip"
            })
        with open(self.config_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def get_zones_file(self, source_id):
        source = self.sources.get(source_id)
        if source:
            return source.zones_file
        return None