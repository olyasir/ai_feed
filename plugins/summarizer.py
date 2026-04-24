from __future__ import annotations

import logging
import os
from abc import ABC, abstractmethod

import anthropic

logger = logging.getLogger(__name__)


class BaseSummarizer(ABC):
    """Interface for future AI summarization plugins."""

    @abstractmethod
    async def summarize(self, title: str, text: str) -> str:
        """Return a concise summary of the article text."""
        ...


class NoOpSummarizer(BaseSummarizer):
    """Default no-op summarizer. Returns empty string."""

    async def summarize(self, title: str, text: str) -> str:
        return ""


async def summarize_llamacpp_release(title: str, body: str) -> str | None:
    """Summarize a llama.cpp release body into plain English.

    Returns a short HTML snippet describing what was shipped/fixed, or None
    if the API key is missing or the call fails.
    """
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return None

    body = (body or "").strip()
    if not body:
        return None

    # Cap input: release notes can be huge (full changelogs). 8k chars is plenty
    # for the model to identify the main themes.
    truncated = body[:8000]

    prompt = f"""You are summarizing a llama.cpp release for developers who want to know what actually changed, without reading raw commit messages.

Release: {title}

Raw release notes:
{truncated}

Write a concise, plain-English summary (3-6 bullet points) covering:
- Notable new features or model support added
- Important bug fixes (especially anything affecting correctness, crashes, or performance)
- Breaking changes or behavior changes users should know about
- Significant performance improvements (with approximate numbers if mentioned)

Skip trivial items (typo fixes, CI tweaks, minor refactors). If the release is mostly routine maintenance, say so in one line instead of listing bullets.

Output HTML only, using <ul><li>...</li></ul> for bullets or a single <p> for a one-line summary. No headings, no preamble."""

    try:
        client = anthropic.AsyncAnthropic(api_key=api_key)
        message = await client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=600,
            messages=[{"role": "user", "content": prompt}],
        )
        return message.content[0].text.strip()
    except Exception as e:
        logger.warning("llama.cpp release summarization failed: %s", e)
        return None


async def generate_trend_summary(articles: list) -> str:
    """Generate an HTML trend summary of AI agent articles using Claude."""
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        logger.warning("ANTHROPIC_API_KEY not set, returning fallback summary")
        return "<p><em>Summary unavailable — set ANTHROPIC_API_KEY to enable AI-powered trend analysis.</em></p>"

    digest_lines = []
    for i, a in enumerate(articles[:50], 1):
        snippet = (a.snippet or "")[:200]
        digest_lines.append(f"{i}. [{a.source}] {a.title}\n   {snippet}")

    digest = "\n\n".join(digest_lines)

    prompt = f"""You are an AI research analyst specializing in LOCAL AI agents — agents that run on-device without cloud dependencies. Below are {len(articles)} recent articles about AI agents from the past week.

Analyze the key trends and themes with a strong focus on LOCAL agent capabilities: on-device inference, edge deployment, small/quantized models, P2P agent collaboration, local tool calling, mobile AI agents, and privacy-preserving agent architectures.

Produce an HTML-formatted trend report with these sections:

1. **Executive Summary** (2-3 sentences focusing on local/edge agent trends)

2. **Key Trends** — 3-5 trend sections, each with an <h3> heading and 2-3 sentence analysis. Prioritize trends related to:
   - Running agents locally (on-device LLM inference, quantization, small models)
   - Agent tool use and function calling on local hardware
   - Multi-modal local agents (text, vision, audio)
   - P2P or decentralized agent systems
   - Mobile/embedded agent deployment
   For each trend, mention specific articles that illustrate it.

3. **QVAC Opportunities** — A dedicated section (<h3>Opportunities for QVAC</h3>) analyzing how these trends create opportunities for QVAC, an open-source local-first AI SDK. QVAC provides:
   - Local LLM inference via llama.cpp (with tool calling, multimodal support)
   - Local speech-to-text (whisper.cpp), text-to-speech (ONNX), translation (nmt.cpp), OCR
   - P2P model sharing and delegated inference via Hyperswarm
   - Cross-platform support (desktop, mobile iOS/Android, Node.js, Bare Runtime)
   - Built-in RAG pipeline with vector search
   - Embeddings generation for semantic search
   For each relevant trend, explain concretely how QVAC could add a feature, integration, or improvement to capitalize on it. Be specific and actionable.

4. **Outlook** — Brief forward-looking section on where local AI agents are heading.

Use only these HTML tags: <h3>, <p>, <ul>, <li>, <strong>, <em>. Do not include <html>, <head>, <body>, or <h1>/<h2> tags.

Articles:
{digest}"""

    client = anthropic.AsyncAnthropic(api_key=api_key)
    message = await client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=3500,
        messages=[{"role": "user", "content": prompt}],
    )
    return message.content[0].text
