"""
帮助搜索引擎
============
Level 1: BM25 关键词全文搜索（零依赖）
Level 2: FAISS 语义向量搜索（可选: pip install sentence-transformers faiss-cpu）
Level 3: LLM RAG 问答（可选: 配置 API endpoint）
"""

from __future__ import annotations

import math
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


# ═══════════════════════════════════════════════════════════════
# 文档分块
# ═══════════════════════════════════════════════════════════════

@dataclass
class HelpChunk:
    """帮助文档的一个章节块。"""
    id: str            # e.g., "ch3"
    title: str         # e.g., "3. 模板准备"
    content: str       # 纯文本内容（去 HTML 标签）
    html_content: str  # 原始 HTML 片段
    tokens: List[str] = field(default_factory=list)


def _strip_html(text: str) -> str:
    """去除 HTML 标签，保留文本。"""
    text = re.sub(r'<style[^>]*>.*?</style>', '', text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r'<script[^>]*>.*?</script>', '', text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r'<[^>]+>', ' ', text)
    text = re.sub(r'&[a-z]+;', ' ', text)
    text = re.sub(r'\s+', ' ', text)
    return text.strip()


def _tokenize(text: str) -> List[str]:
    """中文+英文混合分词。"""
    # 提取中文字符序列 + 英文单词 + 数字
    tokens = []
    # 中文: 连续 CJK 字符
    for m in re.finditer(r'[一-鿿㐀-䶿]+', text):
        for char in m.group():
            if len(char.strip()) >= 1:
                tokens.append(char)
    # 英文/数字: 连续字母数字
    for m in re.finditer(r'[a-zA-Z0-9]+', text):
        t = m.group().lower()
        if len(t) >= 1:
            tokens.append(t)
    return tokens


def chunk_document(html_path: str) -> List[HelpChunk]:
    """将 USER_GUIDE.html 按 <h2> 标签拆分为章节块。"""
    with open(html_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # 按 <h2> 拆分
    sections = re.split(r'(<h2[^>]*>.*?</h2>)', content, flags=re.IGNORECASE)

    chunks = []
    # 第一段是 h2 之前的内容（标题页等），跳过或作为 overview
    preamble = sections[0] if sections else ""

    i = 1
    while i < len(sections):
        header_html = sections[i]
        body_html = sections[i + 1] if i + 1 < len(sections) else ""

        # 提取标题文本
        title = _strip_html(header_html)
        if not title:
            i += 2
            continue

        # 合并 HTML 内容
        full_html = header_html + body_html
        plain = _strip_html(full_html)
        tokens = _tokenize(plain)

        chunk_id = f"ch{len(chunks)}"
        chunks.append(HelpChunk(
            id=chunk_id,
            title=title,
            content=plain,
            html_content=full_html,
            tokens=tokens,
        ))
        i += 2

    return chunks


# ═══════════════════════════════════════════════════════════════
# Level 1: BM25 关键词搜索（零依赖）
# ═══════════════════════════════════════════════════════════════

class BM25Index:
    """BM25 全文搜索索引。"""

    def __init__(self, k1: float = 1.5, b: float = 0.75):
        self.k1 = k1
        self.b = b
        self.chunks: List[HelpChunk] = []
        self._df: Dict[str, int] = {}       # document frequency
        self._doc_len: List[int] = []        # token count per doc
        self._avgdl: float = 0.0
        self._built = False

    def build(self, chunks: List[HelpChunk]):
        self.chunks = chunks
        self._df.clear()
        self._doc_len = []

        for ch in chunks:
            unique_terms = set(ch.tokens)
            for t in unique_terms:
                self._df[t] = self._df.get(t, 0) + 1
            self._doc_len.append(len(ch.tokens))

        n = len(chunks)
        self._avgdl = sum(self._doc_len) / n if n > 0 else 0
        self._built = True

    def search(self, query: str, top_k: int = 5) -> List[Tuple[HelpChunk, float]]:
        """BM25 搜索，返回 (chunk, score) 列表。"""
        if not self._built:
            return []

        query_tokens = _tokenize(query)
        n = len(self.chunks)
        scores = []

        for idx, ch in enumerate(self.chunks):
            score = 0.0
            dl = self._doc_len[idx]
            for qt in query_tokens:
                df = self._df.get(qt, 0)
                if df == 0:
                    continue
                # BM25 formula
                idf = math.log(1 + (n - df + 0.5) / (df + 0.5))
                tf = ch.tokens.count(qt)
                numerator = tf * (self.k1 + 1)
                denominator = tf + self.k1 * (1 - self.b + self.b * dl / self._avgdl)
                score += idf * numerator / denominator

            if score > 0:
                scores.append((ch, score))

        scores.sort(key=lambda x: -x[1])
        return scores[:top_k]


# ═══════════════════════════════════════════════════════════════
# Level 2: FAISS 语义搜索（可选）
# ═══════════════════════════════════════════════════════════════

class SemanticIndex:
    """基于 sentence-transformers + FAISS 的语义搜索。"""

    def __init__(self):
        self._model = None
        self._index = None
        self._chunks: List[HelpChunk] = []
        self._available = False

    @property
    def available(self) -> bool:
        return self._available

    def build(self, chunks: List[HelpChunk]):
        try:
            from sentence_transformers import SentenceTransformer
            import numpy as np

            self._model = SentenceTransformer(
                'paraphrase-multilingual-MiniLM-L12-v2')
            self._chunks = chunks
            texts = [ch.content[:2000] for ch in chunks]
            embeddings = self._model.encode(texts, show_progress_bar=False)
            embeddings = np.array(embeddings).astype('float32')

            try:
                import faiss
                dim = embeddings.shape[1]
                self._index = faiss.IndexFlatIP(dim)  # inner product
                # Normalize for cosine similarity
                faiss.normalize_L2(embeddings)
                self._index.add(embeddings)
            except ImportError:
                # Fallback: brute-force numpy
                self._index = embeddings
                self._faiss = False
            else:
                self._faiss = True

            self._available = True
        except ImportError:
            self._available = False

    def search(self, query: str, top_k: int = 5) -> List[Tuple[HelpChunk, float]]:
        if not self._available or not self._chunks:
            return []

        import numpy as np
        q_emb = self._model.encode([query], show_progress_bar=False)
        q_emb = np.array(q_emb).astype('float32')

        if getattr(self, '_faiss', False):
            import faiss
            faiss.normalize_L2(q_emb)
            scores, indices = self._index.search(q_emb, top_k)
            results = []
            for score, idx in zip(scores[0], indices[0]):
                if idx >= 0 and idx < len(self._chunks):
                    results.append((self._chunks[idx], float(score)))
            return results
        else:
            # Brute-force cosine
            norms = np.linalg.norm(self._index, axis=1)
            q_norm = np.linalg.norm(q_emb)
            if q_norm == 0:
                return []
            sims = np.dot(self._index, q_emb.T).flatten() / (norms * q_norm + 1e-9)
            top_indices = np.argsort(sims)[::-1][:top_k]
            return [(self._chunks[i], float(sims[i])) for i in top_indices if sims[i] > 0]


# ═══════════════════════════════════════════════════════════════
# HelpEngine — 统一入口
# ═══════════════════════════════════════════════════════════════

@dataclass
class RAGSettings:
    """LLM RAG 配置。"""
    enabled: bool = False
    api_base: str = "https://api.anthropic.com/v1/messages"
    api_key: str = ""
    model: str = "claude-sonnet-4-6"
    use_local: bool = False       # 使用本地 Ollama 模型
    local_model: str = "qwen2.5:7b"  # Ollama 模型名
    local_endpoint: str = "http://localhost:11434"  # Ollama 服务地址


class HelpEngine:
    """帮助搜索引擎 — 组合 BM25 + 可选语义搜索 + 可选 LLM RAG。"""

    def __init__(self, html_path: Optional[str] = None):
        self._chunks: List[HelpChunk] = []
        self._bm25 = BM25Index()
        self._semantic = SemanticIndex()
        self._rag_settings = RAGSettings()

        if html_path is None:
            # 查找 USER_GUIDE.html: PyInstaller bundle → 项目根目录
            html_path = self._find_guide()

        if html_path and os.path.exists(html_path):
            self._chunks = chunk_document(html_path)
            if self._chunks:
                self._bm25.build(self._chunks)

    @staticmethod
    def _find_guide() -> Optional[str]:
        """查找 USER_GUIDE.html 路径（支持 PyInstaller 打包和开发模式）。"""
        import sys
        # PyInstaller 打包后 sys._MEIPASS 指向临时解压目录
        if getattr(sys, 'frozen', False):
            base = sys._MEIPASS
        else:
            base = str(Path(__file__).parent.parent)
        # 尝试几个可能的位置
        candidates = [
            os.path.join(base, 'USER_GUIDE.html'),
            os.path.join(base, '..', 'USER_GUIDE.html'),
            str(Path(__file__).parent.parent / 'USER_GUIDE.html'),
        ]
        for p in candidates:
            if os.path.exists(p):
                return p
        return None
                # 语义索引延迟构建（首次搜索时）

    @property
    def chunk_count(self) -> int:
        return len(self._chunks)

    @property
    def semantic_available(self) -> bool:
        return self._semantic.available

    @property
    def rag_settings(self) -> RAGSettings:
        return self._rag_settings

    def set_rag_settings(self, settings: RAGSettings):
        self._rag_settings = settings

    def search(self, query: str, top_k: int = 5,
               use_semantic: bool = True) -> List[Dict[str, Any]]:
        """搜索帮助文档。

        Returns: [{"title": ..., "content": ..., "html": ..., "score": ..., "source": "bm25"|"semantic"}, ...]
        """
        results = []

        # BM25 always runs
        bm25_results = self._bm25.search(query, top_k)
        for ch, score in bm25_results:
            results.append(_chunk_to_result(ch, score, "bm25"))

        # Semantic if available and enabled
        if use_semantic and not self._semantic.available:
            # 首次调用时尝试构建
            if self._chunks:
                self._semantic.build(self._chunks)

        if use_semantic and self._semantic.available:
            sem_results = self._semantic.search(query, top_k)
            seen_ids = {r["id"] for r in results}
            for ch, score in sem_results:
                if ch.id not in seen_ids:
                    results.append(_chunk_to_result(ch, score, "semantic"))

        # 排序: 混合 BM25 + semantic 结果
        results.sort(key=lambda r: -r["score"])
        return results[:top_k]

    def ask(self, question: str, top_k: int = 3) -> Dict[str, Any]:
        """LLM RAG 问答。

        Returns: {"answer": "...", "sources": [...], "error": None|str}
        """
        # 本地模式无需 API Key, 云模式需要
        if not self._rag_settings.enabled:
            return {"answer": "", "sources": [], "error": "RAG 未启用"}
        if not self._rag_settings.use_local and not self._rag_settings.api_key:
            return {"answer": "", "sources": [],
                    "error": "云 API 模式需要配置 API Key，或切换到本地 Ollama 模式"}

        # 检索相关章节
        search_results = self.search(question, top_k=top_k, use_semantic=True)
        if not search_results:
            return {"answer": "", "sources": [],
                    "error": "未找到相关文档"}

        # 构建 context
        context_parts = []
        for r in search_results:
            context_parts.append(f"## {r['title']}\n{r['content'][:1500]}")
        context = "\n\n".join(context_parts)

        # 构建 prompt
        system_prompt = (
            "你是天线测试后处理工具的帮助助手。"
            "根据以下帮助文档内容回答用户问题。"
            "如果文档中没有相关信息，请诚实说明。"
            "用中文回答，保持简洁专业。"
        )
        user_prompt = (
            f"帮助文档内容:\n\n{context}\n\n"
            f"用户问题: {question}\n\n"
            f"请根据上述文档内容回答用户问题。"
        )

        try:
            import json
            import urllib.request

            # 本地 Ollama 模式
            if self._rag_settings.use_local:
                endpoint = self._rag_settings.local_endpoint.rstrip("/")
                payload = {
                    "model": self._rag_settings.local_model,
                    "system": system_prompt,
                    "prompt": user_prompt,
                    "stream": False,
                }
                req = urllib.request.Request(
                    f"{endpoint}/api/generate",
                    data=json.dumps(payload).encode(),
                    headers={"Content-Type": "application/json"},
                )
                with urllib.request.urlopen(req, timeout=120) as resp:
                    data = json.loads(resp.read().decode())
                answer = data.get("response", "")
                return {
                    "answer": answer.strip(),
                    "sources": [r["title"] for r in search_results],
                    "error": None,
                }

            # 判断云 API 类型: Anthropic vs OpenAI-compatible
            base = self._rag_settings.api_base.rstrip("/")
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self._rag_settings.api_key}",
            }

            if "anthropic" in base.lower():
                # Anthropic Messages API
                headers["anthropic-version"] = "2023-06-01"
                payload = {
                    "model": self._rag_settings.model,
                    "max_tokens": 1024,
                    "system": system_prompt,
                    "messages": [
                        {"role": "user", "content": user_prompt}
                    ],
                }
                req = urllib.request.Request(
                    f"{base}/messages",
                    data=json.dumps(payload).encode(),
                    headers=headers,
                )
            else:
                # OpenAI-compatible /v1/chat/completions
                payload = {
                    "model": self._rag_settings.model,
                    "max_tokens": 1024,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                }
                url = base if "/chat/completions" in base else f"{base}/chat/completions"
                req = urllib.request.Request(
                    url,
                    data=json.dumps(payload).encode(),
                    headers=headers,
                )

            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read().decode())

            # 提取回答
            if "anthropic" in base.lower():
                answer = data.get("content", [{}])[0].get("text", "")
            else:
                answer = data.get("choices", [{}])[0].get("message", {}).get("content", "")

            return {
                "answer": answer.strip(),
                "sources": [r["title"] for r in search_results],
                "error": None,
            }

        except Exception as e:
            return {"answer": "", "sources": [r["title"] for r in search_results],
                    "error": str(e)}


def _chunk_to_result(ch: HelpChunk, score: float, source: str) -> Dict[str, Any]:
    return {
        "id": ch.id,
        "title": ch.title,
        "content": ch.content[:500],
        "html": ch.html_content,
        "score": round(score, 4),
        "source": source,
    }
