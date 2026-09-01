# 本地开发环境

状态：Current
确认状态：已确认
最后更新：2026-08-31
治理对象：本地机器标识、环境依赖、构建命令与开发约定（仅机器绑定事实）
依据：QED-Engine 根仓库 `docs/standards/local-dev.md` 治理模式，适配单仓库规模
关联测试：无

## 目的与边界

本文档标注 QED-Tracker 本地开发环境的机器绑定事实，供开发者快速确认环境一致性、减少重复
探索与误判。本文档仅在 UUID 为 `2C6ECD2C-BBEE-11ED-8A95-F0D4154ABBA8` 的机器上生效；
其他环境需复制并修改。

**本地 vs 可移植边界**：本文只登记机器绑定事实（机器标识、绝对路径、conda 环境名）；
可移植配置以仓库内文件为唯一事实源——Python 版本与依赖看 `pyproject.toml`，alembic 看
`alembic.ini`，服务配置看根 `.env` 的 `QED_*` 变量（`src/qed_tracker/config.py` 直读）。
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

## 变更与取代

环境变更时更新本文档对应字段；机器迁移时复制本文档并修改 UUID 和主机名。
