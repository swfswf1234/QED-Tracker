"""三表 API 端点定向测试（QED-029）：selections/downloads/sources 契约 + 彻底隐藏。

契约（根仓库 downloads-three-table-model.md §3.1 + todo QED-029）：
- `GET /selections?course_id=&status=`：表1 列表，默认过滤 rejected/superseded（显式 status 查询同样隐藏）；
- `GET /selections/{id}`：详情（含表2 册明细列表）；
- `POST /selections/{id}/confirm|backup|reject|supersede`（reject/supersede 必填 reason，缺 422）；
- `GET /resources/{id}/downloads`：表2 列表（按 selection_id；默认隐藏 rejected/failed）；
- `POST /downloads/{selection_id, vol, file_hint}`：新建表2 候选册；
- `POST /downloads/{id}/register`：人工下载登记（relative_path，PDF 校验 → candidate→downloaded 直转）；
- `POST /downloads/{id}/approve|reject`：册级验收；非法迁移 409、未知 404。
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from qed_tracker.api.main import create_app
from qed_tracker.config import load_settings
from qed_tracker.db.models import Base, DownloadStatus, SelectionStatus
from qed_tracker.db.selection_repository import ThreeTableRepository


@pytest.fixture
def tt_repo(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'tt.db'}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    repo = ThreeTableRepository(lambda: factory())
    yield repo
    engine.dispose()


@pytest.fixture
def client(tmp_path, tt_repo):
    settings = load_settings(data_root=tmp_path)
    app = create_app(settings, three_table_repository=tt_repo)
    with TestClient(app) as test_client:
        yield test_client


def _seed_selection(tt_repo: ThreeTableRepository, *, title: str = "微积分学教程", status: str = "candidate"):
    selection = tt_repo.create_selection(
        course_id="01_math_analysis",
        title=title,
        authors=["菲赫金哥尔茨"],
        roles=["textbook"],
        version={"edition": "第8版", "language": "zh"},
        vols=["v1", "v2"],
    )
    if status == "confirmed":
        tt_repo.confirm_selection(selection.selection_id)
    elif status == "backup":
        tt_repo.backup_selection(selection.selection_id)
    elif status == "rejected":
        tt_repo.reject_selection(selection.selection_id, reason="版本旧", by="web")
    elif status == "superseded":
        tt_repo.confirm_selection(selection.selection_id)
        tt_repo.supersede_selection(selection.selection_id, reason="被新版替代", by="web")
    return selection


# --- GET /selections ---


def test_selections_list_with_default_hiding(client, tt_repo):
    _seed_selection(tt_repo, title="在册", status="confirmed")
    _seed_selection(tt_repo, title="否决", status="rejected")
    _seed_selection(tt_repo, title="过时", status="superseded")

    response = client.get("/api/v1/selections")
    assert response.status_code == 200
    titles = {item["title"] for item in response.json()}
    assert titles == {"在册"}

    # 显式 status=rejected 查询仍不可见（彻底隐藏语义）
    hidden = client.get("/api/v1/selections", params={"status": "rejected"}).json()
    assert hidden == []


def test_selections_filter_by_course_and_status(client, tt_repo):
    _seed_selection(tt_repo)  # 默认 candidate（微积分学教程）
    _seed_selection(tt_repo, title="数学分析", status="confirmed")
    other = tt_repo.create_selection(course_id="02_topology", title="拓扑", roles=["textbook"], version={})
    tt_repo.confirm_selection(other.selection_id)

    rows = client.get("/api/v1/selections", params={"course_id": "02_topology"}).json()
    assert [r["title"] for r in rows] == ["拓扑"]
    candidates = client.get("/api/v1/selections", params={"status": "candidate"}).json()
    assert {r["title"] for r in candidates} == {"微积分学教程"}


# --- GET /selections/{id} 详情 ---


def test_selection_detail_includes_downloads(client, tt_repo):
    selection = _seed_selection(tt_repo, status="confirmed")
    download = tt_repo.create_download(selection.selection_id, vol="v1", file_hint="第一卷")

    response = client.get(f"/api/v1/selections/{selection.selection_id}")
    assert response.status_code == 200
    data = response.json()
    assert data["title"] == "微积分学教程"
    assert data["status"] == "confirmed"
    download_ids = [d["download_id"] for d in data["downloads"]]
    assert download.download_id in download_ids


def test_selection_detail_hides_hidden_selection(client, tt_repo):
    selection = _seed_selection(tt_repo, title="否决", status="rejected")
    assert client.get(f"/api/v1/selections/{selection.selection_id}").status_code == 404


def test_selection_detail_unknown_404(client):
    assert client.get("/api/v1/selections/cand_nope").status_code == 404


# --- 三态 + supersede ---


def test_selection_three_state_actions(client, tt_repo):
    selection = _seed_selection(tt_repo)
    assert (
        client.post(f"/api/v1/selections/{selection.selection_id}/confirm", json={"note": "入书单"}).status_code == 200
    )
    assert tt_repo.get_selection(selection.selection_id).status == SelectionStatus.CONFIRMED.value

    backup = _seed_selection(tt_repo, title="备选")
    assert client.post(f"/api/v1/selections/{backup.selection_id}/backup", json={"note": "挂备选"}).status_code == 200
    assert tt_repo.get_selection(backup.selection_id).status == SelectionStatus.BACKUP.value

    rejected = _seed_selection(tt_repo, title="否决")
    response = client.post(f"/api/v1/selections/{rejected.selection_id}/reject", json={"reason": "不需要"})
    assert response.status_code == 200
    assert tt_repo.get_selection(rejected.selection_id, include_hidden=True).reject_reason == "不需要"

    superseded = _seed_selection(tt_repo, title="过时", status="confirmed")
    response = client.post(f"/api/v1/selections/{superseded.selection_id}/supersede", json={"reason": "新版替代"})
    assert response.status_code == 200
    assert (
        tt_repo.get_selection(superseded.selection_id, include_hidden=True).status == SelectionStatus.SUPERSEDED.value
    )


def test_selection_reject_requires_reason(client, tt_repo):
    selection = _seed_selection(tt_repo)
    response = client.post(f"/api/v1/selections/{selection.selection_id}/reject", json={"reason": ""})
    assert response.status_code == 422
    response = client.post(f"/api/v1/selections/{selection.selection_id}/supersede", json={})
    assert response.status_code == 422


def test_selection_unknown_action_404_and_illegal_409(client, tt_repo):
    assert client.post("/api/v1/selections/cand_nope/confirm", json={}).status_code == 404
    rejected = _seed_selection(tt_repo, title="否决", status="rejected")
    assert (
        client.post(f"/api/v1/selections/{rejected.selection_id}/confirm", json={}).status_code == 409
    )  # 终态不可迁移


# --- 表2 downloads ---


def test_create_download_posts_candidate(client, tt_repo):
    selection = _seed_selection(tt_repo, status="confirmed")
    response = client.post(
        "/api/v1/downloads", json={"selection_id": selection.selection_id, "vol": "v1", "file_hint": "第一卷"}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == DownloadStatus.CANDIDATE.value
    assert data["roles"] == ["textbook"]  # 继承表1
    assert data["selection_id"] == selection.selection_id


def test_create_download_roles_override(client, tt_repo):
    selection = _seed_selection(tt_repo, status="confirmed")
    response = client.post(
        "/api/v1/downloads", json={"selection_id": selection.selection_id, "vol": "answers", "roles": ["solutions"]}
    )
    assert response.status_code == 200
    assert response.json()["roles"] == ["solutions"]


def test_get_resources_downloads_lists_vols_and_hides(client, tt_repo):
    selection = _seed_selection(tt_repo, status="confirmed")
    tt_repo.create_download(selection.selection_id, vol="v1", file_hint="A")
    bad = tt_repo.create_download(selection.selection_id, vol="v2", file_hint="B")
    tt_repo.reject_download(bad.download_id, reason="内容不符", by="web")

    rows = client.get(f"/api/v1/resources/{selection.selection_id}/downloads").json()
    assert [r["vol"] for r in rows] == ["v1"]
    # 未知 selection_id 返回空列表（按 selection_id 过滤语义）
    assert client.get("/api/v1/resources/cand_nope/downloads").json() == []


def test_download_register_manual_file(client, tt_repo, tmp_path, pdf_bytes):
    selection = _seed_selection(tt_repo, status="confirmed")
    download = tt_repo.create_download(selection.selection_id, vol="v1", file_hint="第一卷")
    manual_dir = tmp_path / "raw" / "books" / "math-qe" / "01_math_analysis"
    manual_dir.mkdir(parents=True)
    (manual_dir / "manual_v1.pdf").write_bytes(pdf_bytes)

    response = client.post(
        f"/api/v1/downloads/{download.download_id}/register",
        json={"relative_path": "raw/books/math-qe/01_math_analysis/manual_v1.pdf"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == DownloadStatus.DOWNLOADED.value
    assert data["sha256"]
    assert data["roles"] == ["textbook"]
    assert data["relative_path"].endswith("manual_v1.pdf")


def test_download_register_rejects_non_pdf(client, tt_repo, tmp_path):
    selection = _seed_selection(tt_repo, status="confirmed")
    download = tt_repo.create_download(selection.selection_id, vol="v1")
    manual_dir = tmp_path / "raw" / "books"
    manual_dir.mkdir(parents=True)
    (manual_dir / "note.txt").write_text("not pdf", encoding="utf-8")
    response = client.post(
        f"/api/v1/downloads/{download.download_id}/register", json={"relative_path": "raw/books/note.txt"}
    )
    assert response.status_code == 400
    assert tt_repo.get_download(download.download_id).status == DownloadStatus.CANDIDATE.value  # 状态不变


def test_download_approve_and_reject(client, tt_repo, tmp_path, pdf_bytes):
    selection = _seed_selection(tt_repo, status="confirmed")
    download = tt_repo.create_download(selection.selection_id, vol="v1")
    manual_dir = tmp_path / "raw" / "books"
    manual_dir.mkdir(parents=True)
    (manual_dir / "v1.pdf").write_bytes(pdf_bytes)
    client.post(f"/api/v1/downloads/{download.download_id}/register", json={"relative_path": "raw/books/v1.pdf"})

    approved = client.post(f"/api/v1/downloads/{download.download_id}/approve")
    assert approved.status_code == 200
    assert approved.json()["status"] == DownloadStatus.APPROVED.value

    # 终态不可再 approve
    assert client.post(f"/api/v1/downloads/{download.download_id}/approve").status_code == 409

    other = tt_repo.create_download(selection.selection_id, vol="v2")
    refused = client.post(f"/api/v1/downloads/{other.download_id}/reject", json={"reason": "内容不符"})
    assert refused.status_code == 200
    assert refused.json()["status"] == DownloadStatus.REJECTED.value
    assert refused.json()["reject_reason"] == "内容不符"
    assert client.post(f"/api/v1/downloads/{other.download_id}/approve").status_code == 409


def test_download_unknown_and_missing_reason(client, tt_repo):
    assert client.post("/api/v1/downloads/download_nope/approve").status_code == 404
    selection = _seed_selection(tt_repo)
    download = tt_repo.create_download(selection.selection_id, vol="v1")
    assert client.post(f"/api/v1/downloads/{download.download_id}/reject", json={"reason": " "}).status_code == 422


# --- 表3 sources ---


def test_download_sources_endpoint(client, tt_repo):
    selection = _seed_selection(tt_repo)
    download = tt_repo.create_download(selection.selection_id, vol="v1")
    tt_repo.add_source(download.download_id, channel="manual", file_keywords="微积分学教程 第1卷", ok=True)
    tt_repo.add_source(download.download_id, channel="libgen_li", provider_id="138177644", ok=False)

    rows = client.get(f"/api/v1/downloads/{download.download_id}/sources").json()
    assert len(rows) == 2
    assert {r["channel"] for r in rows} == {"manual", "libgen_li"}  # 失败尝试留痕可查（详情弹窗统计用）
    assert client.get("/api/v1/downloads/download_nope/sources").status_code == 404
