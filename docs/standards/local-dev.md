# 本地开发环境

状态：Current
确认状态：已确认
最后更新：2026-09-30
治理对象：本地机器标识、环境依赖、构建命令与开发约定（机器绑定事实）及开发产物落位（仓库通用规则，[ADR 0011](../adr/0011-artifact-placement-hygiene.md)）
依据：QED-Engine 根仓库 `docs/standards/local-dev.md` 治理模式，适配单仓库规模
关联测试：无

## 目的与边界

本文档标注 QED-Tracker 本地开发环境的机器绑定事实，供开发者快速确认环境一致性、减少重复
探索与误判。本文档仅在 UUID 为 `2C6ECD2C-BBEE-11ED-8A95-F0D4154ABBA8` 的机器上生效；
其他环境需复制并修改。

**本地 vs 可移植边界**：本文登记机器绑定事实（机器标识、绝对路径、conda 环境名）与「开发产物落位」仓库通用规则（决定与理由见 [ADR 0011](../adr/0011-artifact-placement-hygiene.md)，本文只承接规则）；
可移植配置以仓库内文件为唯一事实源——Python 版本与依赖看 `pyproject.toml`，数据库
schema 自愈看 `src/qed_tracker/db/schema.py`（ADR 0006：Alembic 已退役，无 `alembic.ini`），
服务配置看根 `.env` 的 `QED_*` 变量（`src/qed_tracker/config.py` 直读）。
可移植事实与本文冲突时，以仓库内文件为准并回修本文。

## 机器标识

| 项目 | 值 |
|------|-----|
| UUID | `2C6ECD2C-BBEE-11ED-8A95-F0D4154ABBA8` |
| 主机名 | `wenfu` |

## Git 配置

| 项目 | 值 |
|------|-----|
| 版本 | `git version 2.41.0.windows.1` |
| 用户名 | `swfswf1234` |
| 邮箱 | `812146364@qq.com` |

## Python 环境

| 项目 | 值 |
|------|-----|
| Conda 环境 | `qed_env` |
| 环境路径 | `D:\software\anaconda3\envs\qed_env` |
| Python 版本 | 3.12（以 `pyproject.toml` `requires-python` 为准） |

激活与执行约定（与[开发指南](../guides/development.md)一致）：

```bash
conda run -n qed_env <命令>
```

命令统一经 `conda run -n qed_env` 执行，避免 shell 落到 anaconda base 缺少项目依赖。
历史上文档曾写作 `QED_env`；Windows 文件系统大小写不敏感，两者指向同一环境，
文档统一写 `qed_env`。

## 服务端口速查

| 服务 | 端口 | 说明 |
| --- | --- | --- |
| QED-Tracker | 8901 | 本仓库 FastAPI 服务 |
| QED-Engine 后端 | 8900 | 根仓库（本仓库只链接不复制其细节） |
| Axiom-Flow | 8902 | 子仓库（8000 旧端口兼容保留） |
| QED-Engine 前端 | 8903 | 根仓库 |

## 开发产物落位

三类产物唯一落位（决定与理由见 [ADR 0011](../adr/0011-artifact-placement-hygiene.md)，此处只列可执行规则）：

| 产物类别 | 唯一落位 | 约束 |
| --- | --- | --- |
| 服务运行产物（pid / mode / stderr / 应用日志） | 仓库 `logs/` | 仅此一类；开发临时与取证文件禁止入内 |
| 开发临时文件（探针脚本、捕获输出、一次性编辑脚本） | 仓库 `tmp/`（已 gitignore） | 证据结论与索引落 `docs/plans/`；`tmp/` 不充当长期证据库 |
| 重要过程数据（用户输入件、真实模型试运行产物、回填举证） | `QED_DATA_ROOT` 的 `tmp/qed-tracker/` 分桶 | 按根仓库 dataset 契约：tmp→raw 原子落盘、`raw/` 不可变；根契约正文只链接不复制 |

本机 `QED_DATA_ROOT` 现指向 `D:\coding\QED-Engine\dataset`（见[运维指南](../guides/operations.md)）；其他机器以本机 `.env` 为准。

## 常见误判注记

- **配置来源**：`src/qed_tracker/config.py` 读取优先级为 真实环境变量 > 自身 `.env`
  （本仓库根）> 根 `.env`（自当前目录向上逐级查找，通常落在 QED-Engine 根仓库）> 内置最小
  默认值；只认 `QED_*` 变量 + 密钥变量 `API_KEY`，`QED_TRACKER_*` 前缀与 TOML 已退役；
  排障时先确认各层实际生效值。
- **未配置 MySQL 不是故障**：8901 未配置数据库时相关端点按契约 409 降级，服务本身正常。
- **API key 兜底**：模型调用密钥先取自身 `.env`，再兜底根仓库根 `.env`；`API_KEY` 未配置时
  相关 dry-run 端点返回 409 而非崩溃。
- **Windows 路径**：仓库位于 `D:\coding\QED-Engine\QED-Tracker`，shell 为 Git Bash（POSIX
  语法）；命令中使用正斜杠。
- **`.env` 值内联注释**：值中 ` #`（空白+井号）会被视为注释并剥离（如
  `QED_DB_NAME=qed_test        # qed` → `qed_test`）；`#` 前无空白（库名 `qed#x`、密码
  `secret#pass`）原样保留。曾因在 `.env` 写 `QED_DB_NAME=qed_test # qed` 导致库名拼接注释、
  服务连接 1049 失败（QED-053 排障）。带 `#` 的真实值请确保 `#` 前不留空格。

## 变更与取代

环境变更时更新本文档对应字段；机器迁移时复制本文档并修改 UUID 和主机名。
