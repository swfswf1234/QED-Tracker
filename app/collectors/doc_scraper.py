"""DocScraper — official documentation mirror (wget --mirror via WSL)"""

from app.collectors import BaseCollector
from app.core.config import settings
from app.tools.wget_mirror import WgetMirror


DOC_SOURCES = {
    "pytorch": "https://pytorch.org/docs/stable/",
    "scikit_learn": "https://scikit-learn.org/stable/",
    "xgboost": "https://xgboost.readthedocs.io/en/stable/",
    "yolo": "https://docs.ultralytics.com/",
}


class DocScraper(BaseCollector):
    source = "official_docs"

    def __init__(self, proxy: str = ""):
        self.mirror = WgetMirror(proxy=proxy)

    def scrape(self, name: str, url: str) -> dict:
        save_dir = settings.dataset_path / "official_docs" / name
        return self.mirror.mirror(name, url, save_dir)

    def scrape_all(self) -> list[dict]:
        results = []
        for name, url in DOC_SOURCES.items():
            r = self.scrape(name, url)
            results.append(r)
        return results
