"""数据根布局访问器与 staging 清扫（ARCH-019 统一数据根）。

data_root 即 <QED_DATA_ROOT> 共享树——raw/ 为原始成品区（唯一被外部读取），
tmp/qed-tracker/downloads/ 为下载临时区（终态不保留）。

QED-071 B 轮（2026-09-26）：`Inventory` 类与 `<data_root>/qed-tracker/meta/resources/`
单资源 JSON 岛**已退役**——内容身份只存 `qt_books` 三列（sha256/size_bytes/page_count，
ix_qt_books_sha256 普通索引，D17），读路径（去重/verify/书目视图）全部经 DB；Axiom 传输
留痕（transfers 区）已判废删除（2026-09-24，D3，无读取方）。反岛守护见
`tests/test_data_layout.py`（下载/清扫全链路不得生成 `qed-tracker/` 顶层目录）。
"""

from __future__ import annotations

import logging
import time
from pathlib import Path

logger = logging.getLogger("qed_tracker.inventory")

# 领域缺省：catalog 流程当前只服务 math-qe 目录；体系扩展后由调用方传 domain_id。
DEFAULT_DOMAIN_ID = "math"

# QED-071 R2/D7：staging 清扫阈值 = timeout × retries × 4，绝对下限 6 小时。
_STAGING_AGE_MULTIPLIER = 4
_STAGING_AGE_FLOOR_SECONDS = 6 * 3600


def staging_max_age_seconds(timeout_seconds: float, retries: int) -> int:
    """孤儿 staging 清扫阈值：严格大于单次下载最长寿命（timeout × retries）。

    4 倍安全系数 + 6 小时下限（裁决 D7）；卡死长连接由 httpx timeout 兜底，
    因此无需进程内 in-flight 注册表即可安全清扫。
    """
    return max(int(timeout_seconds * retries * _STAGING_AGE_MULTIPLIER), _STAGING_AGE_FLOOR_SECONDS)


def sweep_downloads(directory: Path, *, max_age_seconds: int) -> list[Path]:
    """按 mtime 年龄清扫本仓孤儿 staging 文件（QED-071 R2）。

    只匹配 `*.download` 与 `*.download.part` 两种本仓命名模式；非递归、不删目录、
    不碰其他项目前缀。失败（权限/占用）只告警不抛出，不得阻断取书任务。
    """
    removed: list[Path] = []
    if not directory.is_dir():
        return removed
    deadline = time.time() - max_age_seconds
    try:
        entries = sorted(directory.iterdir())
    except OSError as exc:
        logger.warning("staging 清扫目录不可读（跳过）：%s：%s", directory, exc)
        return removed
    for path in entries:
        if not path.is_file() or not path.name.endswith((".download", ".download.part")):
            continue
        try:
            if path.stat().st_mtime <= deadline:
                path.unlink()
                removed.append(path)
        except OSError as exc:
            logger.warning("staging 清扫失败（跳过）：%s：%s", path, exc)
    if removed:
        logger.info("staging 年龄清扫：移除 %d 个超龄中间态（>%ss）", len(removed), max_age_seconds)
    return removed


def raw_course_dir(data_root: Path, course_id: str, *, domain_id: str = DEFAULT_DOMAIN_ID) -> Path:
    """课程桶：raw/<domain_id>/<course_id>/（教材/习题成品落盘位）。"""
    return data_root / "raw" / domain_id / course_id


def raw_general_dir(data_root: Path, *, domain_id: str = DEFAULT_DOMAIN_ID) -> Path:
    """领域通用桶：raw/<domain_id>/_general/（inbox/论文等无法归属课程的文件）。"""
    return data_root / "raw" / domain_id / "_general"


def downloads_tmp_dir(data_root: Path) -> Path:
    """下载临时区：tmp/qed-tracker/downloads/（.part/.download 中间态，终态原子替换进 raw）。"""
    return data_root / "tmp" / "qed-tracker" / "downloads"
