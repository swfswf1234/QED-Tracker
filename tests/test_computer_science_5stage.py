"""computer-science 领域5阶段探索模拟测试（QED-014 联调前置）。

验证领域探索的完整状态机转换：
  未开始 → 已生成 → 探索中 → 待确认 → 已完成

使用 mock LLM 模拟响应，不访问公网。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from qed_tracker.api.main import create_app
from qed_tracker.config import load_settings

# ------------------------------ Mock 数据 ------------------------------

COMPUTER_SCIENCE_JSON = {
    "domain": "cs-test-5stage",
    "name": "计算机科学（5阶段测试）",
    "description": "计算机科学研究计算本身：信息如何表示、问题如何被机械地解决。",
    "level": "本科",
    "scope": "以计算机系本科课程体系为基准",
    "entry_requirements": "高中数学与基本信息技术素养",
    "stages": ["基础", "主干", "分支", "前沿"],
    "classic_tracks": [
        {"name": "程序设计与算法", "summary": "以编程语言为载体研究如何把问题转化为可执行的计算过程。", "kind": "main"},
        {"name": "计算机系统", "summary": "研究程序在真实硬件上的运行机制。", "kind": "main"},
        {"name": "人工智能与机器学习", "summary": "以统计建模与优化为核心研究如何让计算机从数据中学习。", "kind": "main"},
    ],
    "anchor_courses": ["程序设计基础", "数据结构与算法", "计算机组成与体系结构"],
    "courses": [
        {
            "course_id": "c_programming",
            "name": "程序设计基础",
            "track": "程序设计与算法",
            "stage": "基础",
            "aliases": ["C 程序设计", "C 语言"],
            "summary": "计算机专业的第一门课。以 C 语言为载体，训练结构化程序设计思想。",
            "prerequisites": [],
        },
        {
            "course_id": "data_structures_and_algorithms",
            "name": "数据结构与算法",
            "track": "程序设计与算法",
            "stage": "基础",
            "aliases": ["数据结构"],
            "summary": "把高效解决问题变成可分析的学问。",
            "prerequisites": ["c_programming"],
        },
        {
            "course_id": "computer_architecture",
            "name": "计算机组成与体系结构",
            "track": "计算机系统",
            "stage": "基础",
            "aliases": ["计算机组成原理"],
            "summary": "从程序员视角回答程序如何在机器上跑。",
            "prerequisites": ["c_programming"],
        },
        {
            "course_id": "operating_systems",
            "name": "操作系统",
            "track": "计算机系统",
            "stage": "主干",
            "aliases": ["OS"],
            "summary": "管理硬件、抽象资源、支撑并发的核心系统课。",
            "prerequisites": ["computer_architecture"],
        },
        {
            "course_id": "machine_learning_basics",
            "name": "机器学习基础",
            "track": "人工智能与机器学习",
            "stage": "主干",
            "aliases": ["机器学习"],
            "summary": "入门主干课：让机器从数据中学习模型。",
            "prerequisites": ["data_structures_and_algorithms"],
        },
    ],
}


# ------------------------------ Mock LLM ------------------------------

class FakeExploreAdvisor:
    """模拟探索 LLM advisor，返回固定响应。"""

    last_instance: FakeExploreAdvisor | None = None

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.calls = 0
        FakeExploreAdvisor.last_instance = self

    def explore_domain(self, domain_name: str, **kwargs) -> dict[str, Any]:
        """模拟 domain@v4 响应。"""
        self.calls += 1
        return {
            "domain": {
                "final_name": domain_name,
                "description": COMPUTER_SCIENCE_JSON["description"],
                "level": COMPUTER_SCIENCE_JSON["level"],
                "stages": COMPUTER_SCIENCE_JSON["stages"],
                "classic_tracks": COMPUTER_SCIENCE_JSON["classic_tracks"],
                "entry_requirements": COMPUTER_SCIENCE_JSON["entry_requirements"],
                "prior_knowledge": "",
            },
            "courses": None,  # domain@v4 不返回课程
            "path": {"notes": "", "edges": [], "graph_td": "graph TD\n"},
        }

    def explore_courses(self, domain_name: str, domain_info: dict, **kwargs) -> dict[str, Any]:
        """模拟 courses@v8 响应。"""
        self.calls += 1
        return {
            "domain": None,
            "courses": COMPUTER_SCIENCE_JSON["courses"],
            "path": {
                "notes": "课程先修关系",
                "edges": [
                    {"from": "data_structures_and_algorithms", "to": "c_programming"},
                    {"from": "computer_architecture", "to": "c_programming"},
                    {"from": "operating_systems", "to": "computer_architecture"},
                    {"from": "machine_learning_basics", "to": "data_structures_and_algorithms"},
                ],
                "graph_td": "graph TD\nA[c_programming] --> B[data_structures_and_algorithms]\nA --> C[computer_architecture]\nC --> D[operating_systems]\nB --> E[machine_learning_basics]",
            },
        }

    def close(self):
        pass


# ------------------------------ Fixtures ------------------------------

@pytest.fixture
def client(tmp_path, monkeypatch):
    """创建带 mock LLM 的测试客户端。"""
    # Mock LLM API key
    monkeypatch.setattr("qed_tracker.api.main.llm_api_key", lambda: "test-key")
    
    # Mock DomainPipeline
    class MockPipeline:
        def __init__(self, **kwargs):
            self.kwargs = kwargs
            self.advisor = FakeExploreAdvisor(**kwargs)
        
        def explore_domain(self, domain_name, **kwargs):
            return self.advisor.explore_domain(domain_name, **kwargs)
        
        def explore_courses(self, domain_name, domain_info, **kwargs):
            return self.advisor.explore_courses(domain_name, domain_info, **kwargs)
        
        def close(self):
            self.advisor.close()
    
    monkeypatch.setattr("qed_tracker.api.main.DomainPipeline", MockPipeline)
    
    settings = load_settings(data_root=tmp_path)
    app = create_app(settings)
    
    with TestClient(app) as test_client:
        yield test_client


# ------------------------------ 测试用例 ------------------------------

def test_5stage_domain_import_and_confirm(client, tmp_path):
    """测试领域导入和确认的基本流程（阶段2和阶段3）。"""
    
    # 使用唯一的时间戳避免冲突
    import time
    unique_suffix = str(int(time.time() * 1000))[-6:]
    domain_id = f"cs-test-5stage-{unique_suffix}"
    domain_name = f"计算机科学（5阶段测试{unique_suffix}）"
    
    # 先创建领域（阶段1：未开始）
    response = client.post("/api/v1/domains", json={
        "name": domain_name,
        "domain_id": domain_id,
        "description": "计算机科学研究计算本身",
        "stages": ["基础", "主干", "分支", "前沿"],
    })
    assert response.status_code == 201
    body = response.json()
    assert body["domain_id"] == domain_id
    assert body["exploration_stage"] == "未开始"
    
    # 修改测试数据使用唯一的 domain_id
    test_data = COMPUTER_SCIENCE_JSON.copy()
    test_data["domain"] = domain_id
    test_data["name"] = domain_name
    
    # 阶段2：已生成（导入领域 JSON）
    response = client.post("/api/v1/domains/import", json={
        "domain": test_data,
    })
    assert response.status_code == 200
    body = response.json()
    assert body["domain_id"] == domain_id
    assert body["exploration_stage"] == "已生成"
    file_path = body["file_path"]
    
    # 验证文件已写入
    assert Path(file_path).exists()
    with open(file_path, encoding="utf-8") as f:
        saved_data = json.load(f)
    assert saved_data["domain"] == domain_id
    
    # 阶段3：待确认（确认领域，手动导入路径直接同步课程）
    response = client.post(f"/api/v1/domains/{domain_id}/confirm")
    assert response.status_code == 200
    body = response.json()
    assert body["domain_id"] == domain_id
    assert body["exploration_stage"] == "待确认"
    assert body["task_id"] is None  # 手动导入路径不触发 LLM


def test_domain_import_validation(client):
    """测试领域导入校验。"""
    
    # 测试缺少必要字段
    response = client.post("/api/v1/domains/import", json={
        "domain": {"domain": "test", "name": "测试领域"},
    })
    assert response.status_code == 400
    
    # 测试无效的 stages
    invalid_data = COMPUTER_SCIENCE_JSON.copy()
    invalid_data["stages"] = ["invalid_stage"]
    response = client.post("/api/v1/domains/import", json={
        "domain": invalid_data,
    })
    assert response.status_code == 400


def test_confirm_requires_file(client):
    """测试确认领域需要文件存在。"""
    response = client.post("/api/v1/domains/nonexistent/confirm")
    assert response.status_code == 404


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
