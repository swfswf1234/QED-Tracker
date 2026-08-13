"""三表模型（qt_selections/qt_downloads/qt_sources）状态机与隐藏过滤定向测试（SQLite 内存）。"""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from qed_tracker.db.models import Base, DownloadStatus, SelectionStatus
from qed_tracker.db.repository import InvalidTransition
from qed_tracker.db.selection_repository import ThreeTableRepository


@pytest.fixture
def repo():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    yield ThreeTableRepository(factory)
    engine.dispose()


def _selection(repo: ThreeTableRepository, title: str = "微积分学教程", roles: list[str] | None = None):
    return repo.create_selection(
        course_id="01_math_analysis",
        title=title,
        authors=["菲赫金哥尔茨"],
        roles=roles or ["textbook"],
        version={"edition": "第8版", "language": "zh"},
        vols=["v1", "v2", "v3"],
        set_no="2",
    )


# --- 表1 状态机 ---


def test_selection_default_status_candidate(repo):
    row = _selection(repo)
    assert row.status == SelectionStatus.CANDIDATE.value
    assert row.set_no == "2"


def test_selection_candidate_to_confirmed_backup(repo):
    row = _selection(repo)
    confirmed = repo.confirm_selection(row.selection_id, note="入书单")
    assert confirmed.status == SelectionStatus.CONFIRMED.value
    assert confirmed.confirmed_at is not None
    assert confirmed.note == "入书单"

    backup = _selection(repo, title="备选书")
    backed = repo.backup_selection(backup.selection_id, note="挂备选")
    assert backed.status == SelectionStatus.BACKUP.value


def test_selection_backup_to_confirmed_reversible(repo):
    row = _selection(repo, title="备选转正")
    repo.backup_selection(row.selection_id)
    promoted = repo.confirm_selection(row.selection_id)
    assert promoted.status == SelectionStatus.CONFIRMED.value
    # 转正后可再挂回备选（可逆语义）
    backed_again = repo.backup_selection(row.selection_id)
    assert backed_again.status == SelectionStatus.BACKUP.value


def test_selection_reject_requires_reason(repo):
    row = _selection(repo)
    with pytest.raises(ValueError):
        repo.reject_selection(row.selection_id, reason=" ", by="cli")


def test_selection_reject_and_supersede(repo):
    row = _selection(repo)
    rejected = repo.reject_selection(row.selection_id, reason="版本过旧", by="cli")
    assert rejected.status == SelectionStatus.REJECTED.value
    assert rejected.reject_reason == "版本过旧"

    confirmed = _selection(repo, title="新版本")
    repo.confirm_selection(confirmed.selection_id)
    superseded = repo.supersede_selection(confirmed.selection_id, reason="被新版替代", by="cli")
    assert superseded.status == SelectionStatus.SUPERSEDED.value
    assert superseded.superseded_at is not None


def test_selection_illegal_transitions(repo):
    row = _selection(repo)
    repo.confirm_selection(row.selection_id)
    # 终态不可迁移
    rejected = repo.reject_selection(_selection(repo, title="否决书").selection_id, reason="不需要", by="cli")
    with pytest.raises(InvalidTransition):
        repo.confirm_selection(rejected.selection_id)
    superseded = _selection(repo, title="过时书2")
    repo.confirm_selection(superseded.selection_id)
    repo.supersede_selection(superseded.selection_id, reason="x", by="cli")
    with pytest.raises(InvalidTransition):
        repo.reject_selection(superseded.selection_id, reason="y", by="cli")


# --- 表2 状态机 ---


def _download(repo: ThreeTableRepository, selection=None, vol: str = "v1", roles: list[str] | None = None):
    selection = selection or _selection(repo)
    return repo.create_download(selection.selection_id, vol=vol, file_hint="第一卷", roles=roles)


def test_download_default_status_candidate_and_roles_inherit(repo):
    selection = _selection(repo)
    download = repo.create_download(selection.selection_id, vol="v1", file_hint="第一卷")
    assert download.status == DownloadStatus.CANDIDATE.value
    # 默认继承表1 roles
    assert download.roles == ["textbook"]


def test_download_roles_override(repo):
    selection = _selection(repo)
    answers = repo.create_download(selection.selection_id, vol="answers", file_hint="习题答案", roles=["solutions"])
    assert answers.roles == ["solutions"]


def test_download_state_machine(repo):
    download = _download(repo)
    repo.start_download(download.download_id)
    completed = repo.complete_download(
        download.download_id, sha256="ab" * 32, relative_path="raw/x/v1.pdf", page_count=10
    )
    assert completed.status == DownloadStatus.DOWNLOADED.value
    assert completed.downloaded_at is not None
    approved = repo.approve_download(completed.download_id)
    assert approved.status == DownloadStatus.APPROVED.value
    assert approved.approved_at is not None


def test_download_register_direct_candidate_to_downloaded(repo):
    """D7 语义：人工 register 从 candidate 直转 downloaded（QED-021 延续）。"""
    download = _download(repo)
    registered = repo.complete_download(
        download.download_id, sha256="cd" * 32, relative_path="raw/x/manual.pdf", page_count=5
    )
    assert registered.status == DownloadStatus.DOWNLOADED.value


def test_download_failed_retry(repo):
    download = _download(repo)
    repo.start_download(download.download_id)
    failed = repo.fail_download(download.download_id)
    assert failed.status == DownloadStatus.FAILED.value
    retried = repo.retry_download(failed.download_id)
    assert retried.status == DownloadStatus.DOWNLOADING.value


def test_download_illegal_transitions(repo):
    download = _download(repo)
    # downloading → downloaded 需要 sha256+path（跳级校验）
    repo.start_download(download.download_id)
    with pytest.raises(InvalidTransition):
        repo.approve_download(download.download_id)
    # 终态不可迁移
    approved = repo.approve_download(
        repo.complete_download(
            _download(repo, vol="v2").download_id, sha256="ef" * 32, relative_path="raw/x/v2.pdf", page_count=2
        ).download_id
    )
    with pytest.raises(InvalidTransition):
        repo.start_download(approved.download_id)
    # candidate → failed 不允许
    fresh = _download(repo, vol="v3")
    with pytest.raises(InvalidTransition):
        repo.fail_download(fresh.download_id)


# --- 彻底隐藏默认过滤 ---


def test_selection_list_filters_rejected_superseded(repo):
    visible = _selection(repo, title="在册")
    repo.confirm_selection(visible.selection_id)
    hidden_reject = _selection(repo, title="否决")
    repo.reject_selection(hidden_reject.selection_id, reason="x", by="cli")
    superseded = _selection(repo, title="过时")
    repo.confirm_selection(superseded.selection_id)
    repo.supersede_selection(superseded.selection_id, reason="y", by="cli")

    rows = repo.list_selections()
    titles = {r.title for r in rows}
    assert titles == {"在册"}

    all_rows = repo.list_selections(include_hidden=True)
    assert {r.title for r in all_rows} == {"在册", "否决", "过时"}

    # 指定 status 过滤仍遵守隐藏语义（直接查 rejected 也默认返回空）
    assert repo.list_selections(status="rejected") == []


def test_download_list_filters_rejected_failed(repo):
    selection = _selection(repo)
    ok = repo.create_download(selection.selection_id, vol="v1", file_hint="A")
    repo.complete_download(ok.download_id, sha256="aa" * 32, relative_path="raw/x/a.pdf", page_count=1)
    bad = repo.create_download(selection.selection_id, vol="v2", file_hint="B")
    repo.start_download(bad.download_id)
    repo.fail_download(bad.download_id)
    refused = repo.create_download(selection.selection_id, vol="v3", file_hint="C")
    repo.reject_download(refused.download_id, reason="x", by="cli")

    rows = repo.list_downloads(selection.selection_id)
    assert {r.vol for r in rows} == {"v1"}
    assert {r.vol for r in repo.list_downloads(selection.selection_id, include_hidden=True)} == {"v1", "v2", "v3"}


# --- 表3 来源 ---


def test_source_records(repo):
    download = _download(repo)
    repo.add_source(
        download.download_id,
        channel="libgen_li",
        provider_id="138177644",
        page_url="https://libgen.li/edition.php?id=138177644",
        ok=0,
        note="djvu 需转 PDF",
    )
    repo.add_source(download.download_id, channel="manual", file_keywords="微积分学教程 第1卷", ok=1)
    ok_sources = repo.list_sources(download.download_id, ok_only=True)
    assert len(ok_sources) == 1
    assert ok_sources[0].channel == "manual"
    all_sources = repo.list_sources(download.download_id)
    assert len(all_sources) == 2


def test_create_download_idempotent(repo):
    selection = _selection(repo)
    first = repo.create_download(selection.selection_id, vol="v1", file_hint="第一卷")
    second = repo.create_download(selection.selection_id, vol="v1", file_hint="第一卷")
    assert first.download_id == second.download_id
    assert len(repo.list_downloads(selection.selection_id)) == 1


def test_selection_creation_idempotent(repo):
    first = _selection(repo)
    second = _selection(repo)
    assert first.selection_id == second.selection_id
