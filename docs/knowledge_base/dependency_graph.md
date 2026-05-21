# 知识依赖关系

```mermaid
graph TD
    subgraph "地基"
        01[数学分析] --> 03[点集拓扑]
        02[线性代数] --> 09[抽象代数]
    end
    subgraph "核心"
        03 --> 04[实分析]
        03 --> 05[复分析]
        01 --> 07[ODE]
    end
    subgraph "广度"
        04 --> 06[泛函分析]
        05 --> 06
        07 --> 08[PDE]
    end
    subgraph "专精"
        04 --> 11[测度论概率]
        02 --> 13[高维概率论]
        11 --> 12[随机过程]
    end
    subgraph "冲刺"
        04 --> 10{QE 综合}
        05 --> 10
        06 --> 10
        08 --> 10
        09 --> 10
        11 --> 10
        12 --> 10
        13 --> 10
    end
```

## 学习路径

1. **数学分析 + 线性代数** → **点集拓扑**（分析基础三件套）
2. **拓扑** → **实分析 + 复分析**（并行攻克 QE 重灾区）
3. **实分析** → **泛函分析**（谱理论核心链）
4. **数学分析** → **ODE → PDE**（方程方向）
5. **实分析** → **测度论概率 → 随机过程**（概率论专精线）
6. **线性代数** → **高维概率论**（算法理论线）
7. 全部 → **QE 冲刺**（Berkeley Problems + 概率论综合）

## 计算机/LLM 学习路径

```mermaid
graph TD
    subgraph "基础回顾"
        CS01[数据结构与算法]
    end
    subgraph "ML 基础"
        CS02[经典机器学习<br/>sklearn + xgboost]
    end
    subgraph "DL 基础"
        CS03[深度学习基础<br/>PyTorch + OpenCV + YOLO]
    end
    subgraph "LLM 冲刺"
        CS04[大模型算法<br/>Transformer → GPT → LLaMA]
        CS05[大模型应用<br/>RAG + Agent]
    end

    CS01 --> CS02
    CS02 --> CS03
    CS03 --> CS04
    CS04 --> CS05
```

1. **DS/Algo 回顾** → **经典 ML**（算法基础 → ML 入门）
2. **经典 ML** → **DL 基础**（统一框架 PyTorch + CV 能力）
3. **DL 基础** → **LLM 算法**（Transformer 核心链路）
4. **LLM 算法** → **LLM 应用**（RAG + Agent 工程落地）
