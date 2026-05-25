"""TextbookHunter — textbook collection orchestration layer

Responsibilities:
  1. Read curriculum (curricula/) to get target textbooks
  2. Call tools layer to search → match confidence → interactive/auto select → download
  3. Write to PostgreSQL/MySQL

Usage:
    from app.collectors.textbook_hunter import TextbookHunter
    hunter = TextbookHunter()
    hunter.interactive_all()  # iterate all courses, interactive
"""

import re
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Optional

from loguru import logger

from app.collectors import BaseCollector
from app.core.config import settings
from app.curricula.base import Confidence
from app.tools.libgen_downloader import LibGenDownloader
from app.tools.annas_downloader import AnnaDownloader
from app.tools.zlib_downloader import ZlibDownloader


class DownloadStatus(str, Enum):
    SKIP_EXISTS = "SKIP_EXISTS"
    SUCCESS = "SUCCESS"
    PASS_NO_RESULT = "PASS_NO_RESULT"
    PASS_NO_EXACT_MATCH = "PASS_NO_EXACT_MATCH"
    FAIL_DOWNLOAD = "FAIL_DOWNLOAD"
    FAIL_SOURCE_UNREACHABLE = "FAIL_SOURCE_UNREACHABLE"


@dataclass
class DownloadAttempt:
    course: str
    target_title: str
    target_author: str
    target_kind: str
    source: str
    status: DownloadStatus
    reason: str = ""
    local_path: str = ""
    result_title: str = ""
    result_author: str = ""
    download_url: str = ""
    confidence: str = ""

    def as_result(self) -> dict:
        return {
            "course": self.course,
            "title": self.result_title or self.target_title,
            "author": self.result_author or self.target_author,
            "source": self.source,
            "source_url": self.download_url,
            "download_url": self.download_url,
            "local_path": self.local_path,
            "_confidence": self.confidence,
            "_status": self.status.value,
            "_reason": self.reason,
        }


def _fuzzy_match(text: str, target: str) -> float:
    """Title similarity: exact substring first, token coverage second, Chinese single-character fallback"""
    text_lower = text.lower()
    target_lower = target.lower()

    # Exact substring match → full score
    if target_lower in text_lower or text_lower in target_lower:
        return 1.0

    # Token coverage (split by spaces/punctuation)
    tokens = re.split(r'[\s,;:()（）、，。；：\-\u2014\u2013]+', target_lower)
    tokens = [t for t in tokens if len(t) > 1]
    if tokens:
        matched = sum(1 for t in tokens if t in text_lower)
        score = matched / len(tokens)
        if score > 0:
            return min(score + 0.1, 1.0)  # small bonus

    # Chinese single-character coverage fallback
    zh_chars = [c for c in target if '\u4e00' <= c <= '\u9fff']
    if zh_chars:
        matched_zh = sum(1 for c in zh_chars if c in text)
        return matched_zh / len(zh_chars) * 0.6  # Chinese single-character lower weight

    return 0.0


def _match_confidence(result: dict, target) -> Optional[str]:
    """Returns 'A' / 'B' / 'C' / None"""
    title_sim = _fuzzy_match(result.get("title", ""), target.title)
    author_sim = _fuzzy_match(result.get("author", ""), target.author) if target.author else 0.0
    lang = (result.get("language", "") or "").lower()

    if title_sim > 0.8 and (not target.author or author_sim > 0.7):
        if target.lang == "zh" and lang in ("zh", "chinese"):
            return "A"
        if target.lang == "en" and lang in ("en", "english", ""):
            return "B"
        return "C"
    if title_sim > 0.5:
        return "C"
    return None


def _normalize_tokens(text: str) -> list[str]:
    text = (text or "").lower()
    return [t for t in re.split(r'[\s,;:()（）、，。；：\-\u2014\u2013._/]+', text) if t]


def _contains_author(text: str, author: str) -> bool:
    if not author:
        return True
    haystack = (text or "").lower()
    tokens = [t for t in _normalize_tokens(author) if len(t) > 1]
    if not tokens:
        return True
    return all(t in haystack for t in tokens)


def _language_matches(result_lang: str, target_lang: str) -> bool:
    lang = (result_lang or "").strip().lower()
    if target_lang == "en":
        return lang in ("", "en", "eng", "english")
    if target_lang == "zh":
        return lang in ("", "zh", "chi", "chinese", "cn", "中文")
    return True


def _edition_matches(result: dict, edition: str) -> bool:
    if not edition:
        return True
    needle_tokens = _normalize_tokens(edition)
    haystack = " ".join([
        result.get("title", ""),
        result.get("edition", ""),
        result.get("year", ""),
    ]).lower()
    return all(t in haystack for t in needle_tokens)


def _strict_match(result: dict, target) -> Optional[str]:
    """Return target confidence only when title, author, language and edition match."""
    title_sim = _fuzzy_match(result.get("title", ""), target.title)
    if title_sim < 0.8:
        return None
    if not _contains_author(result.get("author", ""), target.author):
        return None
    if not _language_matches(result.get("language", ""), target.lang):
        return None
    if not _edition_matches(result, getattr(target, "edition", "")):
        return None
    return getattr(target.confidence, "value", str(target.confidence))


def _size_bytes(s: str) -> int:
    """Convert size string (e.g. '10MB') to bytes"""
    if not s:
        return 0
    s = s.strip().upper()
    try:
        if "MB" in s:
            return int(float(s.replace("MB", "").strip()) * 1024 * 1024)
        if "KB" in s:
            return int(float(s.replace("KB", "").strip()) * 1024)
        if "GB" in s:
            return int(float(s.replace("GB", "").strip()) * 1024 * 1024 * 1024)
        return int(s)
    except ValueError:
        return 0


class TextbookHunter(BaseCollector):
    source = "textbook"

    def __init__(self, proxy: str = "", sources: list[tuple[str, object]] | None = None):
        self.proxy = proxy
        self.libgen = LibGenDownloader(proxy=proxy)
        self.anna = AnnaDownloader(proxy=proxy)
        self.zlib = ZlibDownloader(proxy=proxy)
        self.sources = sources or [
            ("libgen", self.libgen),
            ("annas-archive", self.anna),
            ("zlib", self.zlib),
        ]

    def search_course(self, query: str) -> list[dict]:
        """Search single keyword, LibGen first → Anna's Archive → Z-Library fallback"""
        results = self.libgen.search(query, max_results=8)
        if not results:
            logger.info(f"LibGen 无结果, 尝试 Anna's Archive...")
            results = self.anna.search(query, max_results=8)
        if not results:
            logger.info(f"Anna's Archive 无结果, 尝试 Z-Library...")
            if self.zlib.check_reachable():
                results = self.zlib.search(query, max_results=8)
            else:
                logger.warning("Z-Library 不可达，跳过")
        return results

    def _show_results_with_confidence(self, results: list[dict], targets: list) -> list[dict]:
        """Tag confidence and display"""
        tagged = []
        for r in results:
            best_conf = None
            for t in targets:
                conf = _match_confidence(r, t)
                if conf == "A":
                    best_conf = "A"
                    break
                elif conf == "B" and best_conf != "A":
                    best_conf = "B"
                elif conf == "C" and best_conf is None:
                    best_conf = "C"
            r["_confidence"] = best_conf
            tagged.append(r)

        for i, r in enumerate(tagged, 1):
            conf_tag = f"[{r.get('_confidence', '?')}]" if r.get('_confidence') else "[?]"
            src_tag = " [Anna]" if r.get("_source") == "annas-archive" else ""
            print(f"  {conf_tag} [{i}]{src_tag} {r['title'][:70]}")
            print(f"      作者: {r['author']} | {r.get('year', '')} | {r.get('size', '')} | {r.get('language', '')}")
        return tagged

    def download_single(self, result: dict, course_id: str) -> Optional[dict]:
        """Download single result to course directory"""
        save_dir = settings.textbook_path / "textbooks" / course_id
        safe_title = re.sub(r'[<>:"/\\|?*]', "", result["title"]).strip()[:80]
        safe_title = re.sub(r'\s+', "_", safe_title)
        filename = f"{safe_title}.pdf"
        filepath = save_dir / filename

        if filepath.exists():
            logger.info(f"已存在: {filename}")
            rel = filepath.relative_to(settings.textbook_path)
            return {**result, "local_path": str(rel.as_posix()), "course": course_id}

        logger.info(f"下载: {filename}")
        source = result.get("_source", "")
        if source == "annas-archive":
            hunter = self.anna
        elif source == "zlib":
            hunter = self.zlib
        else:
            hunter = self.libgen
        ok = hunter.download(result["download_url"], filepath)
        if ok:
            rel = filepath.relative_to(settings.textbook_path)
            print(f"    [OK] 已保存: {rel}")
            return {**result, "local_path": str(rel.as_posix()), "course": course_id}
        else:
            print(f"    [FAIL] 下载失败")
            return None

    def interactive_select(self, results: list[dict], course_id: str) -> list[dict]:
        """Interactive select and download"""
        downloaded = []
        while True:
            try:
                choice = input(f"  选择下载 [1-{len(results)}/skip]: ").strip().lower()
            except (EOFError, KeyboardInterrupt):
                choice = "skip"
            if choice == "skip":
                break
            if choice.isdigit() and 1 <= int(choice) <= len(results):
                r = results[int(choice) - 1]
                d = self.download_single(r, course_id)
                if d:
                    downloaded.append(d)
                break
        return downloaded

    def auto_select(self, results: list[dict], course_id: str) -> list[dict]:
        """Auto mode: confidence first, same confidence sorted by size"""
        valid = [r for r in results if r.get("_source") != "annas-archive"
                 and r.get("title") and len(r["title"]) > 5]

        conf_rank = {"A": 0, "B": 1, "C": 2, None: 3}
        valid.sort(key=lambda r: (conf_rank.get(r.get("_confidence"), 3), -_size_bytes(r.get("size", ""))))
        if not valid:
            print("  无有效 PDF 结果")
            return []

        pick = valid[0]
        print(f"  自动选择: [{pick.get('_confidence', '?')}] {pick['title'][:60]} | {pick.get('size', '')}")
        d = self.download_single(pick, course_id)
        return [d] if d else []

    def _target_exists(self, course_id: str, target) -> str:
        save_dir = settings.textbook_path / "textbooks" / course_id
        if not save_dir.exists():
            return ""
        candidates = sorted(save_dir.glob("*.pdf"))
        for path in candidates:
            haystack = path.stem.replace("_", " ")
            title_sim = _fuzzy_match(haystack, target.title)
            if target.author:
                if title_sim >= 0.8:
                    return str(path.relative_to(settings.textbook_path).as_posix())
                if title_sim >= 0.5 and _contains_author(haystack, target.author):
                    return str(path.relative_to(settings.textbook_path).as_posix())
            else:
                if title_sim >= 0.8:
                    return str(path.relative_to(settings.textbook_path).as_posix())
        return ""

    def _source_reachable(self, source) -> bool:
        check = getattr(source, "check_reachable", None)
        if check is None:
            return True
        try:
            return bool(check())
        except Exception:
            return False

    def _download_result(
        self,
        source,
        source_name: str,
        result: dict,
        course_id: str,
        target,
        target_kind: str | None = None,
    ) -> DownloadAttempt:
        kind = target_kind or getattr(target, "kind", "textbook")
        save_dir = settings.textbook_path / "textbooks" / course_id
        result_author = (result.get("author") or result.get("author", "") or "").strip()
        author_tag = f"{result_author[:30]}_" if result_author else ""
        safe_title = re.sub(r'[<>:"/\\|?*]', "", result.get("title") or target.title).strip()[:80]
        safe_title = re.sub(r'\s+', "_", safe_title)
        filepath = save_dir / f"{author_tag}{safe_title}.pdf"
        if filepath.exists():
            rel = filepath.relative_to(settings.textbook_path).as_posix()
            return DownloadAttempt(
                course=course_id,
                target_title=target.title,
                target_author=target.author,
                target_kind=kind,
                source=source_name,
                status=DownloadStatus.SKIP_EXISTS,
                reason="matching filename already exists",
                local_path=rel,
                result_title=result.get("title", ""),
                result_author=result.get("author", ""),
                download_url=result.get("download_url", ""),
                confidence=_strict_match(result, target) or "",
            )
        ok = source.download(result.get("download_url", ""), filepath)
        if ok:
            rel = filepath.relative_to(settings.textbook_path).as_posix()
            return DownloadAttempt(
                course=course_id,
                target_title=target.title,
                target_author=target.author,
                target_kind=kind,
                source=source_name,
                status=DownloadStatus.SUCCESS,
                reason="downloaded",
                local_path=rel,
                result_title=result.get("title", ""),
                result_author=result.get("author", ""),
                download_url=result.get("download_url", ""),
                confidence=_strict_match(result, target) or "",
            )
        if filepath.exists():
            filepath.unlink()
        return DownloadAttempt(
            course=course_id,
            target_title=target.title,
            target_author=target.author,
            target_kind=kind,
            source=source_name,
            status=DownloadStatus.FAIL_DOWNLOAD,
            reason="exact match found but download failed",
            result_title=result.get("title", ""),
            result_author=result.get("author", ""),
            download_url=result.get("download_url", ""),
            confidence=_strict_match(result, target) or "",
        )

    def one_click_target(self, course, target, missing_only: bool = True, target_kind: str | None = None) -> DownloadAttempt:
        kind = target_kind or getattr(target, "kind", "textbook")
        existing = self._target_exists(course.id, target) if missing_only else ""
        if existing:
            return DownloadAttempt(
                course=course.id,
                target_title=target.title,
                target_author=target.author,
                target_kind=kind,
                source="local",
                status=DownloadStatus.SKIP_EXISTS,
                reason="local matching PDF exists",
                local_path=existing,
                confidence=getattr(target.confidence, "value", str(target.confidence)),
            )

        had_results = False
        unreachable = []
        last_attempt = None
        for source_name, source in self.sources:
            if not self._source_reachable(source):
                unreachable.append(source_name)
                continue
            if source_name == "libgen" and target.lang == "zh":
                continue
            query_parts = [p for p in [target.title, target.author] if p]
            query = target.query or " ".join(query_parts).strip() or target.title
            results = source.search(query, max_results=8)
            if not results:
                continue
            had_results = True
            tagged = []
            for result in results:
                conf = _strict_match(result, target)
                if conf:
                    result = {**result, "_confidence": conf, "_source": source_name}
                    tagged.append(result)
            if not tagged:
                continue
            tagged.sort(key=lambda r: -_size_bytes(r.get("size", "")))
            attempt = self._download_result(source, source_name, tagged[0], course.id, target, target_kind=kind)
            if attempt.status == DownloadStatus.SUCCESS:
                return attempt
            last_attempt = attempt

        if last_attempt:
            return last_attempt
        if unreachable and not had_results:
            return DownloadAttempt(
                course=course.id,
                target_title=target.title,
                target_author=target.author,
                target_kind=kind,
                source=",".join(unreachable),
                status=DownloadStatus.FAIL_SOURCE_UNREACHABLE,
                reason="all reachable sources returned no results; unreachable: " + ",".join(unreachable),
                confidence=getattr(target.confidence, "value", str(target.confidence)),
            )
        status = DownloadStatus.PASS_NO_EXACT_MATCH if had_results else DownloadStatus.PASS_NO_RESULT
        return DownloadAttempt(
            course=course.id,
            target_title=target.title,
            target_author=target.author,
            target_kind=kind,
            source="known-sources",
            status=status,
            reason="no strict title/author/version match" if had_results else "no results from known sources",
            confidence=getattr(target.confidence, "value", str(target.confidence)),
        )

    def one_click_course(self, course, missing_only: bool = True) -> list[DownloadAttempt]:
        attempts = []
        for target in course.textbooks:
            attempts.append(self.one_click_target(course, target, missing_only=missing_only, target_kind="textbook"))
        for target in course.exercises:
            attempts.append(self.one_click_target(course, target, missing_only=missing_only, target_kind="exercise"))
        return attempts

    def one_click_all(self, courses: list, missing_only: bool = True) -> list[DownloadAttempt]:
        attempts = []
        for course in courses:
            attempts.extend(self.one_click_course(course, missing_only=missing_only))
        return attempts

    def _search_targets(self, course, label: str, targets: list, auto: bool = False) -> list[dict]:
        """Process search for a group of target textbooks"""
        if not targets:
            return []
        all_downloaded = []
        for t in targets:
            query = t.query or t.title
            print(f"\n{'='*60}")
            print(f"{course.name} ({label}): {query}")
            print(f"{'='*60}")
            results = self.search_course(query)
            if not results:
                print("  [无结果]")
                continue
            tagged = self._show_results_with_confidence(results, [t])
            fn = self.auto_select if auto else self.interactive_select
            downloaded = fn(tagged, course.id)
            all_downloaded.extend(downloaded)
        return all_downloaded

    def hunt_course(self, course, auto: bool = False) -> list[dict]:
        """Search all targets for a single course (Chinese textbooks → English textbooks → exercise books)"""
        all_dl = []
        all_dl.extend(self._search_targets(course, "中文教材", [tb for tb in course.textbooks if tb.lang == "zh"], auto))
        all_dl.extend(self._search_targets(course, "英文教材", [tb for tb in course.textbooks if tb.lang == "en"], auto))
        all_dl.extend(self._search_targets(course, "习题集", course.exercises, auto))
        return all_dl

    def interactive_all(self, auto: bool = False, curriculum=None) -> list[dict]:
        """Iterate all courses

        Args:
            auto: Auto mode (skip interaction)
            curriculum: Curriculum object, defaults to MATH_QE
        """
        if curriculum is None:
            from app.curricula.math_qe import MATH_QE as curriculum
        all_results = []
        for course in curriculum.courses:
            results = self.hunt_course(course, auto=auto)
            all_results.extend(results)
        self.close()
        return all_results

    def close(self):
        seen = set()
        for _, source in self.sources:
            if id(source) in seen:
                continue
            seen.add(id(source))
            close = getattr(source, "close", None)
            if close:
                close()
