from app.curricula.base import Curriculum, Course, TextbookTarget, VideoTarget, ArticleTarget, Confidence

CS_LLM_SPRINT = Curriculum(
    name="计算机 — LLM 冲刺",
    description="AI 开发工程师 / 大模型应用工程师 / RAG 方向：DS+Algo → ML → DL → LLM 算法 → LLM 应用",
    courses=[
        Course(
            id="cs01_ds_algo",
            name="数据结构与算法",
            stage="基础回顾",
            textbooks=[
                TextbookTarget(
                    title="Introduction to Algorithms", author="CLRS", lang="en",
                    confidence=Confidence.B, query="CLRS Introduction to Algorithms 4th"
                ),
                TextbookTarget(
                    title="Algorithms", author="Sedgewick", lang="en",
                    confidence=Confidence.B, query="Sedgewick Algorithms 4th"
                ),
            ],
        ),
        Course(
            id="cs02_ml_classic",
            name="经典机器学习",
            stage="ML 基础",
            textbooks=[
                TextbookTarget(
                    title="An Introduction to Statistical Learning",
                    author="James Witten Hastie", lang="en",
                    confidence=Confidence.B, query="ISLR James Witten Hastie"
                ),
                TextbookTarget(
                    title="The Elements of Statistical Learning",
                    author="Hastie Tibshirani Friedman", lang="en",
                    confidence=Confidence.B, query="ESL Hastie Tibshirani Friedman"
                ),
            ],
            videos=[
                VideoTarget(
                    title="Stanford CS229 Machine Learning",
                    platform="YouTube",
                    url="https://www.youtube.com/playlist?list=PLoROMvodv4rMiGQp3WXShtMGgzqpfVfbU",
                    channel="Stanford Online",
                ),
            ],
        ),
        Course(
            id="cs03_dl_foundation",
            name="深度学习基础",
            stage="DL 基础",
            textbooks=[
                TextbookTarget(
                    title="Dive into Deep Learning", author="Zhang Lipton Li Smola",
                    lang="en", confidence=Confidence.B,
                    query="d2l.ai Dive into Deep Learning"
                ),
            ],
            videos=[
                VideoTarget(
                    title="Stanford CS231n Convolutional Neural Networks",
                    platform="YouTube",
                    url="https://www.youtube.com/playlist?list=PL3FW7Lu3i5JvHM8ljYj-zLfQRF3EO8sYv",
                    channel="Stanford Online",
                ),
            ],
        ),
        Course(
            id="cs04_llm_algorithm",
            name="大模型算法",
            stage="LLM 冲刺",
            textbooks=[
                TextbookTarget(
                    title="Speech and Language Processing", author="Jurafsky Martin",
                    lang="en", confidence=Confidence.B,
                    query="Jurafsky Martin Speech and Language Processing"
                ),
            ],
            articles=[
                ArticleTarget(
                    title="Attention Is All You Need",
                    platform="arXiv",
                    keywords=["transformer", "attention"],
                ),
                ArticleTarget(
                    title="GPT-4 Technical Report",
                    platform="arXiv",
                    keywords=["GPT", "LLM"],
                ),
                ArticleTarget(
                    title="LLaMA: Open and Efficient Foundation Language Models",
                    platform="arXiv",
                    keywords=["LLaMA", "foundation model"],
                ),
            ],
        ),
        Course(
            id="cs05_llm_application",
            name="大模型应用",
            stage="LLM 冲刺",
            videos=[
                VideoTarget(
                    title="Stanford CS224N Natural Language Processing",
                    platform="YouTube",
                    url="https://www.youtube.com/playlist?list=PLoROMvodv4rMFqRtEuo6GjNsmU7QxL7cA",
                    channel="Stanford Online",
                ),
            ],
            articles=[
                ArticleTarget(
                    title="Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks",
                    platform="arXiv",
                    keywords=["RAG", "retrieval"],
                ),
            ],
        ),
    ],
)
