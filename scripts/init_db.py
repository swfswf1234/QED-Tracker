"""数据库初始化入口 — 委托 app/db/init_db.py

用法:
    python scripts/init_db.py               # 创建表 (数据库需已存在)
    python scripts/init_db.py --create-db   # 尝试创建数据库
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.db.init_db import main

if __name__ == "__main__":
    main()
