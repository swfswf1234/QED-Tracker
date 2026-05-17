import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import argparse
from sqlalchemy import create_engine, text
from loguru import logger

from app.core.config import settings
from app.db.session import create_engine_from_config


def _base_url() -> str:
    if settings.db_engine == "mysql":
        return (
            f"mysql+pymysql://{settings.db_user}:{settings.db_password}"
            f"@{settings.db_host}:{settings.db_port}"
        )
    return (
        f"postgresql://{settings.db_user}:{settings.db_password}"
        f"@{settings.db_host}:{settings.db_port}/postgres"
    )


def create_database():
    base_url = _base_url()
    try:
        eng = create_engine(base_url, isolation_level="AUTOCOMMIT")
        with eng.connect() as conn:
            if settings.db_engine == "mysql":
                exists = conn.execute(
                    text(
                        f"SELECT SCHEMA_NAME FROM INFORMATION_SCHEMA.SCHEMATA "
                        f"WHERE SCHEMA_NAME = '{settings.db_name}'"
                    )
                ).fetchone()
            else:
                exists = conn.execute(
                    text(
                        f"SELECT 1 FROM pg_database WHERE datname = '{settings.db_name}'"
                    )
                ).scalar()
            if not exists:
                conn.execute(
                    text(f'CREATE DATABASE "{settings.db_name}" ENCODING "UTF8"')
                )
                logger.info(f"数据库 '{settings.db_name}' 已创建")
            else:
                logger.info(f"数据库 '{settings.db_name}' 已存在")
        eng.dispose()
    except Exception as e:
        logger.error(f"创建数据库失败: {e}")
        return False
    return True


def main():
    parser = argparse.ArgumentParser(description="QED-Tracker 数据库初始化")
    parser.add_argument("--create-db", action="store_true", help="创建数据库（如不存在）")
    args = parser.parse_args()

    if args.create_db:
        print("创建数据库...")
        if not create_database():
            sys.exit(1)

    print("连接数据库...")
    engine = create_engine_from_config()
    if not engine.check_connection():
        print(f"[失败] 无法连接: {settings.db_engine}://{settings.db_host}:{settings.db_port}/{settings.db_name}")
        print(f"  请确认数据库已启动, 或使用 --create-db 参数自动创建")
        sys.exit(1)

    print("创建表结构...")
    engine.connect()
    created = engine.init_tables()
    if created:
        print(f"✓ 已创建 {created} 张表")
    else:
        print("✓ 表已存在，无需创建")

    print("\n初始化完成")


if __name__ == "__main__":
    main()
