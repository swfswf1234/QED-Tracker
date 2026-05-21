# QED-Tracker v0.2 测试指南

## 概览

34 个单元测试，5 个集成测试（需要 PostgreSQL），覆盖全部核心模块。

## 测试结构

```
tests/
├── __init__.py
├── conftest.py              # pytest fixtures (SQLite in-memory)
├── test_config.py           # 配置加载测试 (5 tests)
├── test_models.py           # ORM 模型测试 (11 tests)
├── test_repository.py       # CRUD 仓储测试 (5 tests, require PG)
├── test_collectors.py       # 采集器逻辑测试 (8 tests)
└── test_cli.py              # CLI 参数解析测试 (9 tests)
```

## 运行测试

```bash
# 全部测试
python -m pytest tests/ -v

# 仅运行不依赖数据库的测试
python -m pytest tests/ -v --ignore=tests/test_repository.py

# 运行指定文件
python -m pytest tests/test_collectors.py -v

# 运行指定测试类
python -m pytest tests/test_models.py::TestPaper -v

# 含覆盖率报告（需安装 pytest-cov）
python -m pytest tests/ --cov=app/
```

## 测试结果（v0.2）

```
34 passed, 5 skipped, 0 failed
```

- **5 skipped** = PostgreSQL 未运行时的 `test_repository.py`（标记为 `@pytest.mark.skipif(not check_db(), ...)`）
- 其余 **34 tests** 不依赖任何外部服务，使用 mock 和 SQLite in-memory
- 测试覆盖配置加载、ORM 模型、仓储 CRUD、采集器逻辑和 CLI 参数解析

## 测试覆盖范围

| 模块 | 测试数 | 验证内容 |
|------|--------|---------|
| `app/core/config.py` | 5 | 默认关键词、arXiv 领域、数据库名、数据集路径解析 |
| `app/models/*.py` | 11 | 4 个 ORM 模型的字段创建与默认值 |
| `app/repository/*.py` | 5 | TextbookRepo + PaperRepo 的 CRUD、按课程查询、去重检查 |
| `app/collectors/paper_collector.py` | 3 | arXiv 搜索调用、PDF 下载、无 URL 跳过 |
| `app/collectors/textbook_hunter.py` | 3 | LibGen 空结果、表格解析、非 PDF 过滤 |
| `app/collectors/doc_scraper.py` | 2 | 文档源定义、初始化 |
| `scripts/hunt_papers.py` | 3 | --domain/--max/--all-domains 参数 |
| `scripts/hunt_textbooks.py` | 3 | --course/--no-db 参数 |
| `scripts/hunt_docs.py` | 3 | --name/--all/--no-db 参数 |

## 关键测试技术

### Mock 外部 API

```python
# PaperCollector: 用 mocker 替换 arXiv API 调用
mocker.patch("app.collectors.paper_collector.arxiv_search")
mock_search.return_value = [{"arxiv_id": "2601.00001", ...}]
```

### SQLite in-memory 测试 CRUD

```python
# conftest.py: 创建独立 SQLite 内存数据库
engine = create_engine("sqlite:///:memory:", echo=False)
Base.metadata.create_all(bind=engine)
Session = sessionmaker(bind=engine)
```

### PostgreSQL 依赖跳过

```python
# 自动跳过: 当 PostgreSQL 未运行时
require_pg = pytest.mark.skipif(not check_db(), reason="PostgreSQL not available")
```

## 添加新测试

1. 在 `tests/` 下创建 `test_<module>.py`
2. 如果测试数据库操作, 在参数中使用 `db_session` fixture
3. 如果测试外部 API, 使用 `mocker` 参数 + `mocker.patch()`
4. 运行: `python -m pytest tests/test_<module>.py -v`
