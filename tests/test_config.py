"""测试：配置加载"""

import sys, os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.core.config import Settings


def test_default_keywords():
    s = Settings()
    assert "数学分析" in s.search_keywords


def test_default_arxiv_domains():
    s = Settings()
    assert "math.CA" in s.arxiv_math_domains


def test_default_db_name():
    s = Settings()
    assert s.db_name == "qed_tracker"


def test_dataset_path_resolution():
    s = Settings(dataset_dir="dataset")
    root = s.project_root
    expected = root / "dataset"
    assert s.dataset_path == expected


def test_dataset_path_absolute():
    s = Settings(dataset_dir="/abs/path")
    # 在 Windows 上变为 D:\abs\path；在 Unix 上为 /abs/path
    assert s.dataset_path.is_absolute()


def test_db_url_format():
    s = Settings(db_engine="postgresql", db_host="localhost", db_port=5432, db_name="test_db", db_user="u", db_password="p")
    assert "test_db" in s.db_url
    assert s.db_url.startswith("postgresql://")

def test_db_url_mysql():
    s = Settings(db_engine="mysql", db_host="localhost", db_port=3306, db_name="test_db", db_user="u", db_password="p")
    assert s.db_url.startswith("mysql+pymysql://")
