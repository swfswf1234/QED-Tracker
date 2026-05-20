"""FrontierCollector — frontier article/blog collection orchestration

Flow:
  1. Fetch RSS/API articles via RssTracker
  2. Deduplicate by URL against resources table
  3. Insert new articles into resources table
  4. Optionally seed精选 articles on first run
"""

from loguru import logger

from app.collectors import BaseCollector
from app.core.database import get_conn, init_tables
from app.models.resource import Resource
from app.repository.resource_repo import ResourceRepo
from app.tools.rss_tracker import RssTracker, SEED_ARTICLES


class FrontierCollector(BaseCollector):
    source = "frontier"

    def __init__(self, proxy: str = ""):
        self.proxy = proxy
        self.tracker = RssTracker(proxy=proxy)

    def fetch_new(self, dry_run: bool = False, no_db: bool = False) -> list[dict]:
        """Fetch all articles, filter new ones by URL against DB"""
        articles = self.tracker.fetch_all()
        if not articles:
            logger.info("没有新文章")
            return []

        if dry_run or no_db:
            tag = "[DRY RUN] " if dry_run else "[NO DB] "
            logger.info(f"{tag}新文章 {len(articles)} 篇")
            for a in articles:
                print(f"  [{a['resource_type']}] {a['title'][:60]}")
                print(f"         {a['url']}")
            return articles if no_db else []

        db = get_conn()
        try:
            init_tables()
            repo = ResourceRepo(db)
            new_items = []
            for a in articles:
                exists = repo.exists(url=a["url"])
                if not exists:
                    new_items.append(a)
            logger.info(f"去重后新文章 {len(new_items)} 篇 (共 {len(articles)} 篇)")
            return new_items
        except Exception as e:
            db.rollback()
            logger.error(f"数据库查询失败: {e}")
            return articles
        finally:
            db.close()

    def save_to_db(self, articles: list[dict], no_db: bool = False) -> int:
        """Insert articles into resources table"""
        if not articles:
            return 0

        if no_db:
            logger.info("跳过入库 (--no-db)")
            return 0

        db = get_conn()
        try:
            init_tables()
            repo = ResourceRepo(db)
            imported = 0
            for a in articles:
                try:
                    repo.create(Resource(
                        id=None,
                        resource_type=a.get("resource_type", "article"),
                        title=a["title"],
                        url=a["url"],
                        description=a.get("description", ""),
                        course_tags=a.get("course_tags", []),
                        author=a.get("author", ""),
                        platform=a.get("platform", ""),
                    ))
                    imported += 1
                except Exception as e:
                    logger.warning(f"入库失败 [{a.get('title','')[:40]}]: {e}")
            db.commit()
            logger.info(f"入库完成: {imported}/{len(articles)}")
            return imported
        except Exception as e:
            db.rollback()
            logger.error(f"数据库写入失败: {e}")
            return 0
        finally:
            db.close()

    def seed_articles(self, dry_run: bool = False, no_db: bool = False) -> int:
        """Seed精选 articles on first run"""
        if dry_run:
            print(f"种子数据 {len(SEED_ARTICLES)} 篇:")
            for a in SEED_ARTICLES:
                print(f"  [{a['resource_type']}] {a['title'][:60]}")
            return len(SEED_ARTICLES)

        if no_db:
            logger.info("跳过入库 (--no-db)")
            return 0

        db = get_conn()
        try:
            init_tables()
            repo = ResourceRepo(db)
            seeded = 0
            for a in SEED_ARTICLES:
                exists = repo.exists(url=a["url"])
                if not exists:
                    repo.create(Resource(
                        id=None,
                        resource_type=a["resource_type"],
                        title=a["title"],
                        url=a["url"],
                        description=a.get("description", ""),
                        course_tags=a.get("course_tags", []),
                        author=a["author"],
                        platform=a["platform"],
                    ))
                    seeded += 1
            db.commit()
            logger.info(f"种子数据: 新增 {seeded}/{len(SEED_ARTICLES)}")
            return seeded
        except Exception as e:
            db.rollback()
            logger.error(f"种子数据入库失败: {e}")
            return 0
        finally:
            db.close()

    def run(self, dry_run: bool = False, seed: bool = False, no_db: bool = False) -> int:
        """Main entry: seed OR fetch+save, not both"""
        total = 0

        if seed:
            n = self.seed_articles(dry_run=dry_run, no_db=no_db)
            total += n
        else:
            new = self.fetch_new(dry_run=dry_run, no_db=no_db)
            if new:
                if not dry_run and not no_db:
                    self.save_to_db(new, no_db=no_db)
                total += len(new)

        self.tracker.close()
        return total

    def close(self):
        self.tracker.close()
