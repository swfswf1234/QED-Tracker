from app.curricula.base import Curriculum, Course, TextbookTarget, Confidence

MATH_QE = Curriculum(
    name="突破朗道位垒",
    description="面向数学博士资格考试 (QE) 的《突破朗道位垒》课程体系，10 门课分四个阶段",
    courses=[
        Course(
            id="01_math_analysis",
            name="数学分析",
            stage="地基",
            textbooks=[
                TextbookTarget(
                    title="数学分析原理", author="Rudin", lang="zh",
                    confidence=Confidence.A, query="数学分析原理 Rudin"
                ),
                TextbookTarget(
                    title="Principles of Mathematical Analysis", author="Rudin", lang="en",
                    confidence=Confidence.B, query="Principles of Mathematical Analysis Rudin"
                ),
            ],
            exercises=[
                TextbookTarget(
                    title="吉米多维奇数学分析习题集", author="吉米多维奇", lang="zh",
                    confidence=Confidence.A, query="吉米多维奇 数学分析习题集"
                ),
            ],
        ),
        Course(
            id="02_linear_algebra",
            name="线性代数",
            stage="地基",
            textbooks=[
                TextbookTarget(
                    title="线性代数应该这样学", author="Axler", lang="zh",
                    confidence=Confidence.A, query="线性代数应该这样学 Axler"
                ),
                TextbookTarget(
                    title="Linear Algebra Done Right", author="Axler", lang="en",
                    confidence=Confidence.B, query="Linear Algebra Done Right Axler"
                ),
            ],
            exercises=[
                TextbookTarget(
                    title="线性代数习题集", author="苏联", lang="zh",
                    confidence=Confidence.A, query="苏联 线性代数 习题集"
                ),
            ],
        ),
        Course(
            id="03_topology",
            name="点集拓扑",
            stage="地基",
            textbooks=[
                TextbookTarget(
                    title="点集拓扑学", author="熊金城", lang="zh",
                    confidence=Confidence.A, query="点集拓扑学 熊金城"
                ),
                TextbookTarget(
                    title="Topology", author="Munkres", lang="en",
                    confidence=Confidence.B, query="Munkres Topology"
                ),
            ],
        ),
        Course(
            id="04_real_analysis",
            name="实分析",
            stage="核心",
            textbooks=[
                TextbookTarget(
                    title="实变函数论", author="周民强", lang="zh",
                    confidence=Confidence.A, query="实变函数论 周民强"
                ),
                TextbookTarget(
                    title="Real Analysis", author="Stein", lang="en",
                    confidence=Confidence.B, query="Stein Real Analysis"
                ),
            ],
            exercises=[
                TextbookTarget(
                    title="实变函数解题指南", author="周民强", lang="zh",
                    confidence=Confidence.A, query="实变函数解题指南 周民强"
                ),
            ],
        ),
        Course(
            id="05_complex_analysis",
            name="复分析",
            stage="核心",
            textbooks=[
                TextbookTarget(
                    title="复分析", author="Ahlfors", lang="zh",
                    confidence=Confidence.A, query="复分析 Ahlfors"
                ),
                TextbookTarget(
                    title="Complex Analysis", author="Ahlfors", lang="en",
                    confidence=Confidence.B, query="Ahlfors Complex Analysis"
                ),
                TextbookTarget(
                    title="Complex Analysis", author="Stein", lang="en",
                    confidence=Confidence.B, query="Stein Complex Analysis"
                ),
            ],
            exercises=[
                TextbookTarget(
                    title="复变函数习题集", author="方企勤", lang="zh",
                    confidence=Confidence.A, query="复变函数习题集 方企勤"
                ),
            ],
        ),
        Course(
            id="06_functional_analysis",
            name="泛函分析",
            stage="核心",
            textbooks=[
                TextbookTarget(
                    title="泛函分析", author="张恭庆", lang="zh",
                    confidence=Confidence.A, query="泛函分析 张恭庆"
                ),
                TextbookTarget(
                    title="Functional Analysis", author="Stein", lang="en",
                    confidence=Confidence.B, query="Stein Functional Analysis"
                ),
            ],
            exercises=[
                TextbookTarget(
                    title="泛函分析学习指导", author="", lang="zh",
                    confidence=Confidence.A, query="泛函分析学习指导"
                ),
            ],
        ),
        Course(
            id="07_ode",
            name="常微分方程",
            stage="广度",
            textbooks=[
                TextbookTarget(
                    title="常微分方程", author="丁同仁", lang="zh",
                    confidence=Confidence.A, query="常微分方程 丁同仁"
                ),
                TextbookTarget(
                    title="Ordinary Differential Equations", author="Tenenbaum", lang="en",
                    confidence=Confidence.B, query="Tenenbaum Ordinary Differential Equations"
                ),
            ],
            exercises=[
                TextbookTarget(
                    title="常微分方程习题解", author="", lang="zh",
                    confidence=Confidence.A, query="常微分方程习题解"
                ),
            ],
        ),
        Course(
            id="08_pde",
            name="偏微分方程",
            stage="广度",
            textbooks=[
                TextbookTarget(
                    title="偏微分方程", author="Evans", lang="zh",
                    confidence=Confidence.A, query="偏微分方程 Evans"
                ),
                TextbookTarget(
                    title="Partial Differential Equations", author="Evans", lang="en",
                    confidence=Confidence.B, query="Evans Partial Differential Equations"
                ),
            ],
        ),
        Course(
            id="09_abstract_algebra",
            name="抽象代数",
            stage="广度",
            textbooks=[
                TextbookTarget(
                    title="近世代数引论", author="冯克勤", lang="zh",
                    confidence=Confidence.A, query="近世代数引论 冯克勤"
                ),
                TextbookTarget(
                    title="Abstract Algebra", author="Dummit", lang="en",
                    confidence=Confidence.B, query="Dummit Abstract Algebra"
                ),
            ],
        ),
        Course(
            id="10_qe_prep",
            name="QE 冲刺",
            stage="冲刺",
            textbooks=[
                TextbookTarget(
                    title="伯克利数学问题集", author="", lang="zh",
                    confidence=Confidence.A, query="伯克利数学问题集"
                ),
                TextbookTarget(
                    title="Berkeley Problems in Mathematics", author="", lang="en",
                    confidence=Confidence.B, query="Berkeley Problems in Mathematics"
                ),
            ],
        ),
    ],
)
