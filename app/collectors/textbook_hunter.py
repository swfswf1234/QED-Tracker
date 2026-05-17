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
from pathlib import Path
from typing import Optional

from loguru import logger

from app.collectors import BaseCollector
from app.core.config import settings
from app.curricula.base import Confidence
from app.tools.libgen_downloader import LibGenDownloader
from app.tools.annas_downloader import AnnaDownloader


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

    def __init__(self, proxy: str = ""):
        self.proxy = proxy
        self.libgen = LibGenDownloader(proxy=proxy)
        self.anna = AnnaDownloader(proxy=proxy)

    def search_course(self, query: str) -> list[dict]:
        """Search single keyword, LibGen first → Anna's Archive fallback"""
        results = self.libgen.search(query, max_results=8)
        if not results:
            logger.info(f"LibGen 无结果, 尝试 Anna's Archive...")
            results = self.anna.search(query, max_results=8)
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
        save_dir = settings.dataset_path / "textbooks" / course_id
        safe_title = re.sub(r'[<>:"/\\|?*]', "", result["title"]).strip()[:80]
        safe_title = re.sub(r'\s+', "_", safe_title)
        filename = f"{safe_title}.pdf"
        filepath = save_dir / filename

        if filepath.exists():
            logger.info(f"已存在: {filename}")
            rel = filepath.relative_to(settings.dataset_path)
            return {**result, "local_path": str(rel.as_posix()), "course": course_id}

        logger.info(f"下载: {filename}")
        hunter = self.anna if result.get("_source") == "annas-archive" else self.libgen
        ok = hunter.download(result["download_url"], filepath)
        if ok:
            rel = filepath.relative_to(settings.dataset_path)
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
        self.libgen.close()
        self.anna.close()
        return all_results

    def close(self):
        self.libgen.close()
        self.anna.close()
