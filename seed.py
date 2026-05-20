"""
seed.py — Backbone Blogging Module
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Standalone async seed script that populates the blogging database with:
  - 1 seed author user (staff)
  - 8 blog categories (Technology, Design, etc.)
  - 50 rich blog posts with varied section types
  - 5 curated playlists (10 blogs each)

Usage:
    python seed.py

Requirements:
    - .env file must be present with MONGODB_URL and DATABASE_NAME
    - Docker stack (or local MongoDB) must be running
"""

import asyncio
import logging
import os
import random
from datetime import UTC, datetime, timedelta

from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("seed")


# ── Rich seed data ────────────────────────────────────────────────────────────

CATEGORIES: list[dict] = [
    {"name": "Artificial Intelligence"},
    {"name": "Web Development"},
    {"name": "Design Systems"},
    {"name": "Cloud & DevOps"},
    {"name": "Mobile Engineering"},
    {"name": "Open Source"},
    {"name": "Career & Growth"},
    {"name": "Product & Startups"},
]

BLOGS_DATA: list[dict] = [
    # ── Artificial Intelligence ──────────────────────────────────────────
    {
        "title": "Understanding Transformer Architecture",
        "subtitle": "The backbone behind modern LLMs",
        "excerpt": "A deep dive into how attention mechanisms power today's most capable AI systems.",
        "introduction": (
            "Transformers revolutionised the field of machine learning in 2017 and have "
            "since become the default architecture for language, vision, and multimodal models."
        ),
        "conclusion": (
            "Mastering the Transformer architecture is essential for any engineer who wants "
            "to work seriously with modern AI systems."
        ),
        "category": "Artificial Intelligence",
        "sections": [
            {
                "type": "text",
                "title": "Self-Attention Explained",
                "content": (
                    "Self-attention allows every token in a sequence to attend to every other token. "
                    "The scaled dot-product attention formula is: Attention(Q,K,V) = softmax(QK^T / √d_k) · V. "
                    "Each of Q, K, V is a learned linear projection of the input embeddings."
                ),
            },
            {
                "type": "code",
                "title": "PyTorch Attention Snippet",
                "language": "python",
                "content": (
                    "import torch\nimport torch.nn.functional as F\n\n"
                    "def scaled_dot_product_attention(Q, K, V):\n"
                    "    d_k = Q.size(-1)\n"
                    "    scores = torch.matmul(Q, K.transpose(-2, -1)) / d_k ** 0.5\n"
                    "    weights = F.softmax(scores, dim=-1)\n"
                    "    return torch.matmul(weights, V)"
                ),
            },
            {
                "type": "note",
                "title": "Key Insight",
                "content": (
                    "Multi-head attention runs the attention mechanism h times in parallel with "
                    "different learned projection matrices, then concatenates the results."
                ),
            },
        ],
    },
    {
        "title": "Prompt Engineering Best Practices",
        "subtitle": "Get more from your LLMs",
        "excerpt": "Learn the techniques that separate mediocre prompts from expert-level outputs.",
        "introduction": (
            "Prompt engineering is the discipline of crafting input text that maximises the "
            "quality, accuracy, and relevance of language model responses."
        ),
        "conclusion": "Investing time in prompt design is one of the highest-leverage skills for AI practitioners today.",
        "category": "Artificial Intelligence",
        "sections": [
            {
                "type": "bullets",
                "title": "Core Prompting Techniques",
                "items": [
                    "Zero-shot prompting: ask directly without examples",
                    "Few-shot prompting: provide 2–5 representative input/output pairs",
                    "Chain-of-thought (CoT): instruct the model to reason step-by-step",
                    "ReAct: combine reasoning traces with tool-use actions",
                    "Self-consistency: sample multiple CoT paths and majority-vote",
                ],
            },
            {
                "type": "table",
                "title": "Technique Comparison",
                "headers": ["Technique", "Tokens Used", "Best For"],
                "rows": [
                    ["Zero-shot", "Low", "Simple tasks, clear instructions"],
                    ["Few-shot", "Medium", "Classification, formatting"],
                    ["Chain-of-Thought", "High", "Reasoning, math, logic"],
                    ["ReAct", "Very High", "Agentic tool use"],
                ],
            },
        ],
    },
    {
        "title": "Building a RAG Pipeline with LangChain",
        "subtitle": "Ground your AI in real data",
        "excerpt": "Retrieval-Augmented Generation lets LLMs answer questions based on your own documents.",
        "introduction": (
            "RAG is the technique of retrieving relevant documents from a vector store and "
            "injecting them into the LLM context window before generating an answer."
        ),
        "conclusion": "RAG dramatically reduces hallucinations and keeps your AI grounded in verified, up-to-date knowledge.",
        "category": "Artificial Intelligence",
        "sections": [
            {
                "type": "flowchart",
                "title": "RAG Pipeline",
                "steps": [
                    {
                        "id": "ingest",
                        "title": "Document Ingestion",
                        "description": "Load, split, and embed documents into a vector store (e.g. Chroma, Pinecone).",
                        "color": "blue",
                    },
                    {
                        "id": "retrieve",
                        "title": "Semantic Retrieval",
                        "description": "Embed the user query and find top-k nearest neighbours in the vector store.",
                        "color": "green",
                    },
                    {
                        "id": "augment",
                        "title": "Context Augmentation",
                        "description": "Inject retrieved chunks into the system prompt alongside the user query.",
                        "color": "purple",
                    },
                    {
                        "id": "generate",
                        "title": "LLM Generation",
                        "description": "Send the augmented prompt to the LLM and stream the grounded response.",
                        "color": "orange",
                    },
                ],
            },
            {
                "type": "code",
                "title": "LangChain RAG Example",
                "language": "python",
                "content": (
                    "from langchain.vectorstores import Chroma\n"
                    "from langchain.embeddings import OpenAIEmbeddings\n"
                    "from langchain.chains import RetrievalQA\n"
                    "from langchain.llms import OpenAI\n\n"
                    "vectorstore = Chroma.from_documents(docs, OpenAIEmbeddings())\n"
                    "qa_chain = RetrievalQA.from_chain_type(\n"
                    "    llm=OpenAI(), retriever=vectorstore.as_retriever()\n"
                    ")\n"
                    "answer = qa_chain.run('What is our refund policy?')"
                ),
            },
        ],
    },
    {
        "title": "Fine-Tuning vs Prompt Engineering",
        "subtitle": "Choosing the right customisation strategy",
        "excerpt": "When should you fine-tune a model, and when is a well-crafted prompt enough?",
        "introduction": (
            "Both approaches let you steer LLM behaviour, but they differ dramatically in "
            "cost, control, and complexity."
        ),
        "conclusion": "Start with prompts. Graduate to fine-tuning only when you have proven the baseline and have quality labelled data.",
        "category": "Artificial Intelligence",
        "sections": [
            {
                "type": "table",
                "title": "Decision Matrix",
                "headers": ["Criterion", "Prompt Engineering", "Fine-Tuning"],
                "rows": [
                    ["Cost", "Low (token cost only)", "High (GPU hours + data labelling)"],
                    ["Latency", "Longer context = slower", "Shorter prompt → faster"],
                    ["Consistency", "Variable", "Highly consistent"],
                    ["Data Required", "None", "Hundreds to thousands of examples"],
                    ["Iteration Speed", "Minutes", "Hours to days"],
                ],
            },
        ],
    },
    {
        "title": "Vector Databases Demystified",
        "subtitle": "The storage layer for AI applications",
        "excerpt": "Every modern AI app needs a vector store. Here's what you need to know.",
        "introduction": (
            "Vector databases are purpose-built for storing and querying high-dimensional embeddings "
            "generated by ML models."
        ),
        "conclusion": "Choosing the right vector database is a critical architectural decision for any production AI system.",
        "category": "Artificial Intelligence",
        "sections": [
            {
                "type": "bullets",
                "title": "Popular Vector Databases",
                "items": [
                    "Pinecone — fully managed, serverless, production-ready",
                    "Chroma — open-source, local-first, great for prototyping",
                    "Weaviate — multimodal support, GraphQL API",
                    "Qdrant — Rust-based, extremely fast, self-hosted",
                    "pgvector — Postgres extension, familiar SQL interface",
                ],
            },
        ],
    },
    # ── Web Development ──────────────────────────────────────────────────
    {
        "title": "FastAPI at Scale: Lessons from Production",
        "subtitle": "What nobody tells you in the tutorials",
        "excerpt": "Real-world patterns for building maintainable FastAPI services that can handle millions of requests.",
        "introduction": (
            "FastAPI is fantastic out of the box, but scaling it in production requires deliberate "
            "architecture decisions that go well beyond the official tutorial."
        ),
        "conclusion": "Production FastAPI is about boundaries, observability, and never coupling your domain to your HTTP layer.",
        "category": "Web Development",
        "sections": [
            {
                "type": "text",
                "title": "Dependency Injection Done Right",
                "content": (
                    "FastAPI's `Depends()` system is powerful but easy to abuse. Keep dependencies "
                    "stateless and free of business logic. Use them for authentication, pagination "
                    "parameters, and database session injection — nothing more."
                ),
            },
            {
                "type": "code",
                "title": "Lifespan Context Manager",
                "language": "python",
                "content": (
                    "from contextlib import asynccontextmanager\n"
                    "from fastapi import FastAPI\n\n"
                    "@asynccontextmanager\n"
                    "async def lifespan(app: FastAPI):\n"
                    "    await startup_database()\n"
                    "    await startup_cache()\n"
                    "    yield\n"
                    "    await shutdown_database()\n\n"
                    "app = FastAPI(lifespan=lifespan)"
                ),
            },
        ],
    },
    {
        "title": "Async Python: The Complete Guide",
        "subtitle": "From asyncio basics to production patterns",
        "excerpt": "Master Python's async ecosystem and write non-blocking code that actually performs.",
        "introduction": (
            "Asynchronous programming in Python enables concurrent I/O without the complexity of threads, "
            "making it ideal for web services, data pipelines, and real-time applications."
        ),
        "conclusion": "Async Python is a superpower — but only when you understand the event loop and avoid blocking the thread.",
        "category": "Web Development",
        "sections": [
            {
                "type": "code",
                "title": "Concurrent API Calls with asyncio.gather",
                "language": "python",
                "content": (
                    "import asyncio\nimport httpx\n\n"
                    "async def fetch(client: httpx.AsyncClient, url: str) -> dict:\n"
                    "    response = await client.get(url)\n"
                    "    return response.json()\n\n"
                    "async def fetch_all(urls: list[str]) -> list[dict]:\n"
                    "    async with httpx.AsyncClient() as client:\n"
                    "        return await asyncio.gather(*[fetch(client, u) for u in urls])"
                ),
            },
            {
                "type": "note",
                "title": "Never Do This",
                "content": (
                    "Calling time.sleep() inside an async function blocks the entire event loop. "
                    "Always use `await asyncio.sleep()` instead."
                ),
            },
        ],
    },
    {
        "title": "MongoDB Aggregation Pipelines",
        "subtitle": "Data transformation inside the database",
        "excerpt": "Learn to write powerful aggregation queries that process millions of documents efficiently.",
        "introduction": (
            "MongoDB's aggregation framework lets you filter, reshape, group, and sort documents "
            "directly in the database — avoiding costly round trips to your application."
        ),
        "conclusion": "Master the pipeline stages and you'll rarely need to pull raw data into Python for reporting.",
        "category": "Web Development",
        "sections": [
            {
                "type": "code",
                "title": "Blog Stats Aggregation",
                "language": "javascript",
                "content": (
                    "db.blogs.aggregate([\n"
                    "  { $match: { isPublished: true } },\n"
                    "  { $group: {\n"
                    "      _id: '$category.$id',\n"
                    "      total_blogs: { $sum: 1 },\n"
                    "      avg_views: { $avg: '$views' },\n"
                    "      top_likes: { $max: '$likes' }\n"
                    "  }},\n"
                    "  { $sort: { avg_views: -1 } },\n"
                    "  { $limit: 10 }\n"
                    "])"
                ),
            },
        ],
    },
    {
        "title": "REST vs GraphQL vs gRPC",
        "subtitle": "Choosing the right API paradigm",
        "excerpt": "A practical comparison of three dominant API styles with real-world trade-offs.",
        "introduction": (
            "The choice of API protocol has lasting implications for your developer experience, "
            "performance characteristics, and integration complexity."
        ),
        "conclusion": "Use REST for simple CRUD, GraphQL for flexible client-driven queries, and gRPC for high-performance internal services.",
        "category": "Web Development",
        "sections": [
            {
                "type": "table",
                "title": "API Paradigm Comparison",
                "headers": ["Aspect", "REST", "GraphQL", "gRPC"],
                "rows": [
                    ["Payload Format", "JSON", "JSON", "Protobuf (binary)"],
                    ["Typing", "Informal", "Schema (SDL)", "Strict (.proto)"],
                    ["Over-fetching", "Common", "Eliminated", "N/A"],
                    ["Browser Support", "Native", "via library", "via gRPC-web"],
                    ["Streaming", "SSE / WebSocket", "Subscriptions", "Native bidirectional"],
                ],
            },
        ],
    },
    {
        "title": "Rate Limiting Strategies for APIs",
        "subtitle": "Protect your service without annoying your users",
        "excerpt": "Implementing fair, transparent, and production-grade rate limiting in your API.",
        "introduction": (
            "Rate limiting is essential for protecting your service from abuse, ensuring fair usage, "
            "and maintaining quality of service for all clients."
        ),
        "conclusion": "Good rate limiting is invisible to well-behaved clients and immediately obvious to abusers.",
        "category": "Web Development",
        "sections": [
            {
                "type": "bullets",
                "title": "Common Algorithms",
                "items": [
                    "Fixed Window — simple bucket per time window, susceptible to boundary bursts",
                    "Sliding Window Log — precise but memory-intensive",
                    "Token Bucket — allows controlled bursting, widely used",
                    "Leaky Bucket — smooths traffic, no bursting allowed",
                ],
            },
        ],
    },
    # ── Design Systems ───────────────────────────────────────────────────
    {
        "title": "Building a Design System from Scratch",
        "subtitle": "Consistency at scale",
        "excerpt": "The principles, tooling, and process behind a world-class design system.",
        "introduction": (
            "A design system is a single source of truth for your product's visual and interactive language — "
            "tokens, components, patterns, and guidelines that teams reference across every touchpoint."
        ),
        "conclusion": "A great design system is not a library of components but a living contract between design and engineering.",
        "category": "Design Systems",
        "sections": [
            {
                "type": "flowchart",
                "title": "Design System Lifecycle",
                "steps": [
                    {
                        "id": "audit",
                        "title": "Visual Audit",
                        "description": "Catalogue every colour, spacing unit, typography style, and component across your product.",
                        "color": "blue",
                    },
                    {
                        "id": "tokens",
                        "title": "Define Design Tokens",
                        "description": "Extract primitive and semantic tokens: colour, spacing, radius, shadow, motion.",
                        "color": "green",
                    },
                    {
                        "id": "components",
                        "title": "Component Library",
                        "description": "Build composable, accessible, token-driven components in code and in Figma simultaneously.",
                        "color": "purple",
                    },
                    {
                        "id": "governance",
                        "title": "Governance & Contribution",
                        "description": "Define RFC processes, versioning strategy, and contribution guidelines for the team.",
                        "color": "orange",
                    },
                ],
            },
        ],
    },
    {
        "title": "Typography That Converts",
        "subtitle": "The hidden driver of UI clarity",
        "excerpt": "How font choice, sizing scales, and line lengths affect comprehension and conversion.",
        "introduction": (
            "Typography is the single most impactful visual decision in UI design. "
            "A well-chosen typeface with a mathematical size scale communicates hierarchy instantly."
        ),
        "conclusion": "Great typography is invisible — readers absorb the content without noticing the craft behind it.",
        "category": "Design Systems",
        "sections": [
            {
                "type": "table",
                "title": "Modular Type Scale (1.250 ratio)",
                "headers": ["Step", "Size (rem)", "Use Case"],
                "rows": [
                    ["xs", "0.64", "Labels, captions"],
                    ["sm", "0.80", "Helper text, badges"],
                    ["base", "1.00", "Body copy"],
                    ["lg", "1.25", "Lead paragraph"],
                    ["xl", "1.563", "Section headers"],
                    ["2xl", "1.953", "Page sub-titles"],
                    ["3xl", "2.441", "Hero headings"],
                ],
            },
        ],
    },
    {
        "title": "Colour Theory for Developers",
        "subtitle": "Stop picking bad palettes",
        "excerpt": "A practical, code-focused introduction to colour theory that every frontend developer needs.",
        "introduction": (
            "Colour is one of the first things users notice and one of the hardest for "
            "developers without a design background to get right."
        ),
        "conclusion": "You don't need a design degree — just a systematic understanding of hue, saturation, and luminance relationships.",
        "category": "Design Systems",
        "sections": [
            {
                "type": "bullets",
                "title": "Practical Colour Rules",
                "items": [
                    "Choose a primary hue and derive semantic colours using HSL adjustments",
                    "Keep saturation consistent across shades (60–70% is a safe default)",
                    "Use WCAG contrast ratios: 4.5:1 for normal text, 3:1 for large text",
                    "Never rely on colour alone to convey meaning — always pair with icon or label",
                    "Test your palette in greyscale to check luminance relationships",
                ],
            },
        ],
    },
    {
        "title": "Micro-Animations That Feel Premium",
        "subtitle": "Motion design for product engineers",
        "excerpt": "The animation patterns that distinguish polished products from generic interfaces.",
        "introduction": (
            "Micro-animations are small, purposeful movements that provide feedback, guide attention, "
            "and communicate state changes without demanding conscious effort from the user."
        ),
        "conclusion": "Animation should be felt, not watched. When done right, it makes interfaces feel alive without calling attention to itself.",
        "category": "Design Systems",
        "sections": [
            {
                "type": "code",
                "title": "CSS Spring Animation",
                "language": "css",
                "content": (
                    ".button {\n"
                    "  transition: transform 0.15s cubic-bezier(0.34, 1.56, 0.64, 1),\n"
                    "              box-shadow 0.15s ease;\n"
                    "}\n\n"
                    ".button:hover {\n"
                    "  transform: translateY(-2px);\n"
                    "  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.15);\n"
                    "}\n\n"
                    ".button:active {\n"
                    "  transform: translateY(0);\n"
                    "}"
                ),
            },
        ],
    },
    {
        "title": "Glassmorphism: The Right Way",
        "subtitle": "Blur effects without the pitfalls",
        "excerpt": "How to implement glassmorphism correctly — with accessibility, performance, and purpose in mind.",
        "introduction": (
            "Glassmorphism became the defining UI trend of the 2020s, but most implementations "
            "sacrifice readability and performance for visual flair."
        ),
        "conclusion": "Glassmorphism is a tool, not a style. Use it to layer hierarchy — never as decoration.",
        "category": "Design Systems",
        "sections": [
            {
                "type": "code",
                "title": "Accessible Glass Card",
                "language": "css",
                "content": (
                    ".glass-card {\n"
                    "  background: rgba(255, 255, 255, 0.08);\n"
                    "  backdrop-filter: blur(12px) saturate(180%);\n"
                    "  -webkit-backdrop-filter: blur(12px) saturate(180%);\n"
                    "  border: 1px solid rgba(255, 255, 255, 0.15);\n"
                    "  border-radius: 16px;\n"
                    "  /* Ensure WCAG contrast for text inside */\n"
                    "  color: #ffffff;\n"
                    "}"
                ),
            },
            {
                "type": "note",
                "content": "Always provide a solid-colour fallback for browsers that don't support backdrop-filter.",
            },
        ],
    },
    # ── Cloud & DevOps ───────────────────────────────────────────────────
    {
        "title": "Docker for Python Developers",
        "subtitle": "Containerise everything, regret nothing",
        "excerpt": "A practical guide to containerising Python applications for local development and production.",
        "introduction": (
            "Docker eliminates the 'it works on my machine' problem by packaging your application "
            "and all its dependencies into a reproducible, portable image."
        ),
        "conclusion": "Every Python project should ship as a Docker image. It's the single best investment for deployment reliability.",
        "category": "Cloud & DevOps",
        "sections": [
            {
                "type": "code",
                "title": "Production-Ready Dockerfile",
                "language": "dockerfile",
                "content": (
                    "FROM python:3.12-slim AS builder\n"
                    "WORKDIR /app\n"
                    "COPY requirements.txt .\n"
                    "RUN pip install --no-cache-dir -r requirements.txt\n\n"
                    "FROM python:3.12-slim\n"
                    "WORKDIR /app\n"
                    "COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages\n"
                    "COPY . .\n"
                    "RUN addgroup --system app && adduser --system --ingroup app app\n"
                    "USER app\n"
                    'CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]'
                ),
            },
        ],
    },
    {
        "title": "Kubernetes Explained for App Developers",
        "subtitle": "You don't need to be a DevOps engineer",
        "excerpt": "The essential Kubernetes concepts every backend developer should understand.",
        "introduction": (
            "Kubernetes is the de-facto standard for container orchestration, but its surface area is "
            "intimidating. As an app developer, you only need to understand a small subset."
        ),
        "conclusion": "Focus on Deployments, Services, and ConfigMaps. Leave the cluster internals to your platform team.",
        "category": "Cloud & DevOps",
        "sections": [
            {
                "type": "bullets",
                "title": "Core Resources You Must Know",
                "items": [
                    "Pod — smallest deployable unit; one or more containers sharing a network namespace",
                    "Deployment — manages rolling updates and replica counts for your pods",
                    "Service — stable DNS name and load-balancer for a set of pods",
                    "ConfigMap / Secret — inject environment configuration without rebuilding images",
                    "Ingress — HTTP routing rules from external traffic to your Services",
                ],
            },
        ],
    },
    {
        "title": "CI/CD with GitHub Actions",
        "subtitle": "Automate test, build, and deploy",
        "excerpt": "Build a complete CI/CD pipeline for a FastAPI service using GitHub Actions.",
        "introduction": (
            "Continuous integration and delivery are table-stakes for any professional engineering team. "
            "GitHub Actions makes it possible with zero external tooling."
        ),
        "conclusion": "A pipeline that runs tests, builds a Docker image, and deploys on merge pays for itself after the first prevented production incident.",
        "category": "Cloud & DevOps",
        "sections": [
            {
                "type": "code",
                "title": "FastAPI CI Workflow",
                "language": "yaml",
                "content": (
                    "name: CI\non:\n  push:\n    branches: [main]\n  pull_request:\njobs:\n"
                    "  test:\n    runs-on: ubuntu-latest\n    services:\n"
                    "      mongo:\n        image: mongo:7\n        ports: ['27017:27017']\n"
                    "    steps:\n      - uses: actions/checkout@v4\n"
                    "      - uses: actions/setup-python@v5\n        with:\n          python-version: '3.12'\n"
                    "      - run: pip install -r requirements.txt\n"
                    "      - run: pytest --cov=src"
                ),
            },
        ],
    },
    {
        "title": "Observability: Logs, Metrics, and Traces",
        "subtitle": "See everything that happens in production",
        "excerpt": "Building a complete observability stack for modern distributed services.",
        "introduction": (
            "Observability is the discipline of understanding what's happening inside your system "
            "from the outside. It rests on three pillars: logs, metrics, and distributed traces."
        ),
        "conclusion": "You cannot improve what you cannot measure. Invest in observability before you need it.",
        "category": "Cloud & DevOps",
        "sections": [
            {
                "type": "table",
                "title": "Observability Pillars",
                "headers": ["Pillar", "Tool", "Answers"],
                "rows": [
                    ["Logs", "Loki + Grafana", "What happened and when?"],
                    ["Metrics", "Prometheus + Grafana", "How often and how much?"],
                    ["Traces", "Tempo + Jaeger", "Where is the latency?"],
                ],
            },
        ],
    },
    {
        "title": "Terraform for Python Teams",
        "subtitle": "Infrastructure as Code without the YAML",
        "excerpt": "Provision cloud infrastructure reproducibly using Terraform's HCL language.",
        "introduction": (
            "Infrastructure as Code means treating your cloud resources — VPCs, databases, "
            "load balancers — with the same discipline as application code: version control, review, and automation."
        ),
        "conclusion": "Terraform plans are the pull-request of your infrastructure. Review them with the same rigour.",
        "category": "Cloud & DevOps",
        "sections": [
            {
                "type": "code",
                "title": "Simple EC2 Instance in Terraform",
                "language": "hcl",
                "content": (
                    'resource "aws_instance" "api_server" {\n'
                    '  ami           = "ami-0c55b159cbfafe1f0"\n'
                    '  instance_type = "t3.micro"\n\n'
                    "  tags = {\n"
                    '    Name        = "backbone-api"\n'
                    '    Environment = "production"\n'
                    "  }\n}"
                ),
            },
        ],
    },
    # ── Mobile Engineering ───────────────────────────────────────────────
    {
        "title": "React Native vs Flutter in 2025",
        "subtitle": "The definitive cross-platform comparison",
        "excerpt": "Which framework should you choose for your next mobile project?",
        "introduction": (
            "Both React Native and Flutter have matured significantly, "
            "but they make fundamentally different technical trade-offs."
        ),
        "conclusion": "Choose React Native if your team knows JavaScript and you need to share logic with a web app. Choose Flutter for pixel-perfect fidelity and performance.",
        "category": "Mobile Engineering",
        "sections": [
            {
                "type": "table",
                "title": "Framework Comparison",
                "headers": ["Factor", "React Native", "Flutter"],
                "rows": [
                    ["Language", "JavaScript / TypeScript", "Dart"],
                    ["Rendering", "Native components", "Custom renderer (Skia/Impeller)"],
                    ["Package ecosystem", "npm (massive)", "pub.dev (growing)"],
                    ["Hot reload", "Fast Refresh", "Stateful hot reload"],
                    ["Web support", "react-native-web", "Flutter Web (beta)"],
                ],
            },
        ],
    },
    {
        "title": "Offline-First Mobile Architecture",
        "subtitle": "Apps that work anywhere",
        "excerpt": "Design patterns for building resilient mobile apps that function without an internet connection.",
        "introduction": (
            "Offline-first is a design philosophy where the local device database is the source "
            "of truth, and remote sync happens opportunistically."
        ),
        "conclusion": "Users don't care about your server's uptime. They care about their data being available and their actions not being lost.",
        "category": "Mobile Engineering",
        "sections": [
            {
                "type": "flowchart",
                "title": "Offline Sync Strategy",
                "steps": [
                    {
                        "id": "local_write",
                        "title": "Local Write",
                        "description": "All user actions write to the local SQLite / Hive / Realm database first.",
                        "color": "blue",
                    },
                    {
                        "id": "queue",
                        "title": "Sync Queue",
                        "description": "Mutations are appended to an ordered sync queue with timestamps.",
                        "color": "green",
                    },
                    {
                        "id": "sync",
                        "title": "Background Sync",
                        "description": "When connectivity is available, the queue is flushed to the server with conflict resolution.",
                        "color": "purple",
                    },
                ],
            },
        ],
    },
    {
        "title": "Push Notifications at Scale",
        "subtitle": "Deliver the right message at the right time",
        "excerpt": "Building a reliable, personalised push notification system for millions of mobile users.",
        "introduction": (
            "Push notifications are one of the highest-leverage re-engagement tools in mobile, "
            "but poorly implemented systems destroy user trust."
        ),
        "conclusion": "Fewer, more relevant notifications always outperform high-volume blasts. Invest in personalisation.",
        "category": "Mobile Engineering",
        "sections": [
            {
                "type": "bullets",
                "title": "Push Best Practices",
                "items": [
                    "Request permission only after demonstrating value — not on first launch",
                    "Segment your audience; never send the same message to everyone",
                    "Respect time zones and local quiet hours",
                    "A/B test notification copy relentlessly",
                    "Provide easy in-app notification preferences management",
                ],
            },
        ],
    },
    {
        "title": "App Store Optimisation in 2025",
        "subtitle": "Organic growth for mobile apps",
        "excerpt": "Proven ASO strategies that drive downloads without paid acquisition.",
        "introduction": (
            "App Store Optimisation is the discipline of improving your app's visibility and conversion "
            "rate on the App Store and Google Play."
        ),
        "conclusion": "ASO is a compounding investment. A well-optimised listing earns downloads every day without additional spend.",
        "category": "Mobile Engineering",
        "sections": [
            {
                "type": "table",
                "title": "ASO Ranking Factors",
                "headers": ["Factor", "Impact", "Tip"],
                "rows": [
                    ["App Name / Title", "High", "Include primary keyword naturally"],
                    ["Subtitle / Short Description", "High", "Secondary keywords here"],
                    ["Screenshots", "Very High", "First screenshot is a hero — A/B test it"],
                    [
                        "Ratings & Reviews",
                        "Very High",
                        "Prompt after a positive action, not on launch",
                    ],
                    ["Downloads Velocity", "High", "Use paid to boost in first 7 days"],
                ],
            },
        ],
    },
    {
        "title": "Secure Storage in Mobile Apps",
        "subtitle": "Never store secrets in plaintext",
        "excerpt": "How to handle credentials, tokens, and sensitive data safely on iOS and Android.",
        "introduction": (
            "Mobile devices are lost and stolen. Treating device storage as a trusted secure enclave "
            "is one of the most common — and dangerous — mistakes in mobile development."
        ),
        "conclusion": "Assume the device filesystem is public. Use the Keychain (iOS) and Keystore (Android) for every sensitive value.",
        "category": "Mobile Engineering",
        "sections": [
            {
                "type": "bullets",
                "title": "Secure Storage Rules",
                "items": [
                    "Never store JWTs or API keys in AsyncStorage / SharedPreferences",
                    "Use iOS Keychain Services or Android Keystore for tokens",
                    "Encrypt sensitive local databases with SQLCipher",
                    "Clear sensitive data from memory promptly after use",
                    "Never log user credentials or access tokens",
                ],
            },
        ],
    },
    # ── Open Source ──────────────────────────────────────────────────────
    {
        "title": "How to Make Your First Open Source Contribution",
        "subtitle": "From lurker to contributor",
        "excerpt": "A practical, step-by-step guide for making a meaningful first contribution to any open source project.",
        "introduction": (
            "Contributing to open source is one of the highest-ROI career investments a developer can make. "
            "It builds reputation, sharpens skills, and creates lasting network effects."
        ),
        "conclusion": "Your first PR doesn't need to be a feature. A well-written bug report or improved documentation is enormously valuable.",
        "category": "Open Source",
        "sections": [
            {
                "type": "flowchart",
                "title": "First Contribution Workflow",
                "steps": [
                    {
                        "id": "find",
                        "title": "Find a Project",
                        "description": "Use GitHub's 'good first issue' label to find approachable tasks.",
                        "color": "blue",
                    },
                    {
                        "id": "fork",
                        "title": "Fork & Clone",
                        "description": "Fork the repository and clone your fork locally.",
                        "color": "green",
                    },
                    {
                        "id": "branch",
                        "title": "Create a Branch",
                        "description": "Name your branch descriptively: fix/typo-in-readme or feat/add-dark-mode.",
                        "color": "purple",
                    },
                    {
                        "id": "pr",
                        "title": "Open a PR",
                        "description": "Write a clear title and description. Reference the issue. Request review.",
                        "color": "orange",
                    },
                ],
            },
        ],
    },
    {
        "title": "Semantic Versioning Explained",
        "subtitle": "What MAJOR.MINOR.PATCH actually means",
        "excerpt": "Why semantic versioning matters and how to apply it correctly in your projects.",
        "introduction": (
            "Semantic versioning (SemVer) is a versioning scheme that encodes backwards-compatibility "
            "intent directly in the version number."
        ),
        "conclusion": "SemVer is a contract with your users. Break it and you break their trust.",
        "category": "Open Source",
        "sections": [
            {
                "type": "table",
                "title": "SemVer Components",
                "headers": ["Component", "When to Increment", "Example"],
                "rows": [
                    ["MAJOR", "Breaking API change", "1.0.0 → 2.0.0"],
                    ["MINOR", "New backwards-compatible feature", "1.0.0 → 1.1.0"],
                    ["PATCH", "Backwards-compatible bug fix", "1.0.0 → 1.0.1"],
                ],
            },
        ],
    },
    {
        "title": "Writing a Great README",
        "subtitle": "Your project's first impression",
        "excerpt": "The anatomy of a README that attracts contributors and earns GitHub stars.",
        "introduction": (
            "Your README is the front page of your project. Most developers decide whether to use or "
            "contribute to a library within 30 seconds of landing on its repository."
        ),
        "conclusion": "A great README is a gift to your future self and every developer who follows.",
        "category": "Open Source",
        "sections": [
            {
                "type": "bullets",
                "title": "README Checklist",
                "items": [
                    "One-sentence description at the very top",
                    "Badges: build status, coverage, version, licence",
                    "Feature list (bullet points, scannable)",
                    "Quick-start: working code in under 2 minutes",
                    "Full installation guide",
                    "API reference or link to docs",
                    "Contributing guide and code of conduct",
                    "Licence",
                ],
            },
        ],
    },
    {
        "title": "Choosing the Right Open Source Licence",
        "subtitle": "Protect your work and your users",
        "excerpt": "MIT, Apache 2.0, GPL — what they mean and how to choose the right one.",
        "introduction": (
            "The licence you choose for your open source project determines who can use it, "
            "how they can modify it, and whether they must share their changes."
        ),
        "conclusion": "When in doubt, MIT for libraries and Apache 2.0 when you need patent protection.",
        "category": "Open Source",
        "sections": [
            {
                "type": "table",
                "title": "Licence Comparison",
                "headers": ["Licence", "Commercial Use", "Patent Grant", "Copyleft"],
                "rows": [
                    ["MIT", "Yes", "No", "No"],
                    ["Apache 2.0", "Yes", "Yes", "No"],
                    ["GPL-3.0", "Yes", "Yes", "Strong — derivatives must be GPL"],
                    ["LGPL-2.1", "Yes", "Yes", "Weak — linking allowed without GPL"],
                    ["AGPL-3.0", "Yes", "Yes", "Network copyleft — SaaS must release source"],
                ],
            },
        ],
    },
    {
        "title": "Maintaining a Healthy Open Source Project",
        "subtitle": "From side project to sustainable community",
        "excerpt": "What it takes to keep an open source project alive, welcoming, and focused.",
        "introduction": (
            "Many projects die not from lack of interest but from maintainer burnout. "
            "Sustainability requires deliberate community design, not just technical excellence."
        ),
        "conclusion": "The best technical projects fail without community. The best communities can carry imperfect technical projects to success.",
        "category": "Open Source",
        "sections": [
            {
                "type": "bullets",
                "title": "Maintainer Health Checklist",
                "items": [
                    "Write a CONTRIBUTING.md before your first contributor appears",
                    "Add issue templates — bug report, feature request, question",
                    "Set up branch protection: require PR reviews and passing CI",
                    "Respond to issues within 48 hours — even if just to label them",
                    "Be explicit about what you will NOT accept to avoid wasted PRs",
                    "Consider co-maintainers early — bus factor of 1 is fatal",
                ],
            },
        ],
    },
    # ── Career & Growth ──────────────────────────────────────────────────
    {
        "title": "The Staff Engineer Career Path",
        "subtitle": "What comes after senior?",
        "excerpt": "A clear-eyed look at the staff engineering role, what it requires, and how to get there.",
        "introduction": (
            "Staff engineer is widely misunderstood. It's not just 'very senior' — it's a "
            "fundamentally different mode of operating: technical leadership without management authority."
        ),
        "conclusion": "Staff engineers shape how engineering happens, not just what gets built. That requires influence, not authority.",
        "category": "Career & Growth",
        "sections": [
            {
                "type": "table",
                "title": "IC Levels Compared",
                "headers": ["Level", "Scope", "Success Defined By"],
                "rows": [
                    ["Junior", "Task", "Completing assigned work correctly"],
                    ["Mid", "Feature", "Owning a feature end-to-end"],
                    ["Senior", "Team", "Lifting the whole team's output"],
                    ["Staff", "Org", "Improving how the org builds software"],
                    ["Principal", "Company", "Shaping multi-year technical direction"],
                ],
            },
        ],
    },
    {
        "title": "Negotiating Your Engineering Salary",
        "subtitle": "Leave no money on the table",
        "excerpt": "Evidence-based strategies for negotiating compensation packages at any career stage.",
        "introduction": (
            "Most engineers significantly undervalue themselves, and most companies rely on this. "
            "Effective negotiation is not aggressive — it's preparation, data, and patience."
        ),
        "conclusion": "The best negotiating position is a competing offer. The second best is knowing your number and being willing to walk.",
        "category": "Career & Growth",
        "sections": [
            {
                "type": "bullets",
                "title": "Negotiation Principles",
                "items": [
                    "Never give a number first — always ask for the range",
                    "Research comp data: Levels.fyi, Glassdoor, LinkedIn Salary",
                    "Negotiate total compensation, not just base salary",
                    "Always ask for time to consider — never accept on the call",
                    "Every component is negotiable: signing bonus, equity cliff, remote flexibility",
                    "Competing offers are the most powerful leverage — use them ethically",
                ],
            },
        ],
    },
    {
        "title": "Code Review Culture",
        "subtitle": "Reviews that teach, not police",
        "excerpt": "How to give and receive code reviews that improve code quality without damaging team morale.",
        "introduction": (
            "Code review is the highest-leverage activity for knowledge sharing and quality control "
            "in a software team — but only when practised with intentionality and empathy."
        ),
        "conclusion": "A culture of kind, rigorous code review is one of the most valuable things a senior engineer can build.",
        "category": "Career & Growth",
        "sections": [
            {
                "type": "bullets",
                "title": "Reviewer's Checklist",
                "items": [
                    "Comment on code, never on the author",
                    "Distinguish blocking (must fix) from non-blocking (suggestion) comments",
                    "Explain the WHY behind every requested change",
                    "Acknowledge what's done well — not just what needs improvement",
                    "Approve promptly when all blockers are resolved; don't let PRs rot",
                ],
            },
        ],
    },
    {
        "title": "Building a Personal Brand as a Developer",
        "subtitle": "Make opportunities come to you",
        "excerpt": "How writing, speaking, and open source work compound into career-changing opportunities.",
        "introduction": (
            "Personal brand is not self-promotion — it's making your work and thinking visible "
            "so that opportunities find you instead of the reverse."
        ),
        "conclusion": "The best engineers I know didn't find their best opportunities — those opportunities found them because of their visible work.",
        "category": "Career & Growth",
        "sections": [
            {
                "type": "bullets",
                "title": "Where to Build Visibility",
                "items": [
                    "Technical writing: dev.to, Medium, your own blog",
                    "Open source: ship something small and useful, maintain it",
                    "Twitter / X: share learnings, not opinions",
                    "LinkedIn: write one post per week about something you learned",
                    "Conference talks: local meetups first, then CFPs",
                ],
            },
        ],
    },
    {
        "title": "Mastering Technical Interviews",
        "subtitle": "FAANG prep without losing your soul",
        "excerpt": "A pragmatic, efficient approach to coding interview preparation that respects your time.",
        "introduction": (
            "Technical interviews are imperfect proxies for job performance, but they are the gate "
            "to the most impactful and lucrative engineering roles. Treat them as a game with known rules."
        ),
        "conclusion": "Prepare systematically, practice under realistic conditions, and remember that rejection is often about fit, not ability.",
        "category": "Career & Growth",
        "sections": [
            {
                "type": "table",
                "title": "Study Plan (8 Weeks)",
                "headers": ["Week", "Topic", "LeetCode Count"],
                "rows": [
                    ["1–2", "Arrays, Strings, Hash Maps", "30"],
                    ["3", "Two Pointers, Sliding Window", "20"],
                    ["4", "Trees, Graphs, BFS/DFS", "25"],
                    ["5", "Dynamic Programming Basics", "20"],
                    ["6", "Advanced DP, Backtracking", "15"],
                    ["7", "System Design", "5 mock designs"],
                    ["8", "Mock Interviews + Review", "Repetition"],
                ],
            },
        ],
    },
    # ── Product & Startups ───────────────────────────────────────────────
    {
        "title": "Product-Market Fit: How You Know",
        "subtitle": "The signals that don't lie",
        "excerpt": "The leading and lagging indicators that tell you whether your product has found its market.",
        "introduction": (
            "Product-market fit (PMF) is the stage where your product satisfies a strong market demand. "
            "Before PMF, everything is a fight. After PMF, growth feels almost inevitable."
        ),
        "conclusion": "PMF is not a destination — it's a continuous signal you optimise for. Markets shift; so must your product.",
        "category": "Product & Startups",
        "sections": [
            {
                "type": "bullets",
                "title": "PMF Signals",
                "items": [
                    "Sean Ellis Test: >40% of users would be 'very disappointed' if product disappeared",
                    "NPS above 50",
                    "Organic word-of-mouth accounts for >30% of new signups",
                    "Churn is decreasing month-on-month without explicit retention campaigns",
                    "Support tickets are about missing features, not broken ones",
                ],
            },
        ],
    },
    {
        "title": "The Art of the MVP",
        "subtitle": "Ship the right thing, not the full thing",
        "excerpt": "How to define, build, and learn from a minimum viable product without wasting months of engineering.",
        "introduction": (
            "An MVP is not a broken product or a prototype — it's the minimum set of features "
            "that allows you to validate a specific hypothesis about your market."
        ),
        "conclusion": "The goal of an MVP is learning, not shipping. Design every MVP around a falsifiable hypothesis.",
        "category": "Product & Startups",
        "sections": [
            {
                "type": "flowchart",
                "title": "Build-Measure-Learn Loop",
                "steps": [
                    {
                        "id": "idea",
                        "title": "Idea / Hypothesis",
                        "description": "State your riskiest assumption as a testable hypothesis.",
                        "color": "blue",
                    },
                    {
                        "id": "build",
                        "title": "Build",
                        "description": "Build only what's needed to test the hypothesis. No more.",
                        "color": "green",
                    },
                    {
                        "id": "measure",
                        "title": "Measure",
                        "description": "Instrument your MVP with analytics before launch.",
                        "color": "purple",
                    },
                    {
                        "id": "learn",
                        "title": "Learn",
                        "description": "Validated? Double down. Invalidated? Pivot or kill.",
                        "color": "orange",
                    },
                ],
            },
        ],
    },
    {
        "title": "Pricing Your SaaS Product",
        "subtitle": "The decision that determines everything",
        "excerpt": "Frameworks and psychology behind pricing strategies that maximise revenue and retention.",
        "introduction": (
            "Pricing is the most leveraged decision in a SaaS business. A 10% improvement in "
            "pricing has 3× more impact on profit than a 10% improvement in acquisition."
        ),
        "conclusion": "Raise your prices. Almost every early-stage SaaS company is underpriced.",
        "category": "Product & Startups",
        "sections": [
            {
                "type": "table",
                "title": "Pricing Models Compared",
                "headers": ["Model", "Best For", "Risk"],
                "rows": [
                    [
                        "Flat Rate",
                        "Simple, low-complexity products",
                        "Leaves money on table for power users",
                    ],
                    [
                        "Per Seat",
                        "Team / collaboration tools",
                        "Can stall adoption at large companies",
                    ],
                    ["Usage-Based", "API, infrastructure, AI", "Revenue unpredictability"],
                    ["Tiered", "Most B2B SaaS", "Package design complexity"],
                    ["Freemium", "Viral, PLG products", "High CAC:LTV ratio risk"],
                ],
            },
        ],
    },
    {
        "title": "Zero to One: The Technical Founder's Playbook",
        "subtitle": "Building before you have runway",
        "excerpt": "How technical founders can move fast, stay lean, and build the right thing before the money runs out.",
        "introduction": (
            "The early-stage technical founder faces a unique challenge: she must simultaneously "
            "be the chief engineer, product manager, and salesperson — all before achieving any validation."
        ),
        "conclusion": "Your unfair advantage as a technical founder is speed. Protect it at all costs.",
        "category": "Product & Startups",
        "sections": [
            {
                "type": "bullets",
                "title": "Technical Founder Principles",
                "items": [
                    "Build for 10 users, not 10,000 — you can always refactor",
                    "Use managed services aggressively in year one (Supabase, Railway, Vercel)",
                    "Talk to 5 potential customers before writing a single line of code",
                    "Your tech stack is not a competitive advantage at this stage",
                    "Launch an embarrassingly early public version — the market will teach you",
                ],
            },
        ],
    },
    {
        "title": "Raising a Seed Round: What Investors Actually Look For",
        "subtitle": "The signal behind the slide deck",
        "excerpt": "An insider breakdown of what early-stage investors evaluate beyond the pitch deck.",
        "introduction": (
            "Raising a seed round is a sales process, and like any sales process it helps to "
            "understand exactly what the buyer values."
        ),
        "conclusion": "Investors bet on founders first, market second, product third. In that order.",
        "category": "Product & Startups",
        "sections": [
            {
                "type": "bullets",
                "title": "What Seed Investors Evaluate",
                "items": [
                    "Founder-market fit: do you have unique insight into this problem?",
                    "Market size: is this a billion-dollar market if it works?",
                    "Traction: any signal of real demand, however small",
                    "Co-founder chemistry: can you work together under extreme stress?",
                    "Clarity of thinking: can you explain why you'll win in 2 minutes?",
                ],
            },
        ],
    },
    # ── Extra blogs (mix of categories to round out to 50) ───────────────
    {
        "title": "WebSockets vs Server-Sent Events",
        "subtitle": "Real-time communication patterns",
        "excerpt": "Choosing the right real-time protocol for your use case.",
        "introduction": "Both WebSockets and SSE enable server-to-client push, but they make very different trade-offs.",
        "conclusion": "Use SSE for one-way server push; use WebSockets when you need full duplex communication.",
        "category": "Web Development",
        "sections": [
            {
                "type": "table",
                "title": "Protocol Comparison",
                "headers": ["Feature", "WebSocket", "SSE"],
                "rows": [
                    ["Direction", "Bidirectional", "Server → Client only"],
                    ["Protocol", "ws:// / wss://", "HTTP"],
                    ["Auto-reconnect", "Manual", "Built-in"],
                    ["Load balancers", "Sticky sessions needed", "Standard HTTP"],
                ],
            }
        ],
    },
    {
        "title": "SQL Query Optimisation Fundamentals",
        "subtitle": "Make your queries fast",
        "excerpt": "The most impactful query optimisation techniques every backend developer should know.",
        "introduction": "Slow queries are the most common root cause of production performance issues in data-intensive applications.",
        "conclusion": "Indexes are free performance. Use EXPLAIN liberally. Measure before and after every change.",
        "category": "Web Development",
        "sections": [
            {
                "type": "bullets",
                "title": "Top Optimisation Techniques",
                "items": [
                    "Add indexes on columns used in WHERE, JOIN, and ORDER BY",
                    "Use EXPLAIN / EXPLAIN ANALYZE to read query plans",
                    "Avoid SELECT * — select only the columns you need",
                    "Use CTEs for readability but benchmark them against subqueries",
                    "Batch inserts instead of row-by-row",
                ],
            }
        ],
    },
    {
        "title": "Accessibility in Modern Web Apps",
        "subtitle": "Build for everyone",
        "excerpt": "A practical guide to implementing WCAG 2.2 accessibility in your React or Vue application.",
        "introduction": "Accessible web applications are better for everyone — not just users with disabilities.",
        "conclusion": "Accessibility is a quality attribute, not a feature. Ship it from day one.",
        "category": "Design Systems",
        "sections": [
            {
                "type": "bullets",
                "title": "WCAG Quick Wins",
                "items": [
                    "All interactive elements must be keyboard-navigable",
                    "Images must have meaningful alt text",
                    "Focus indicators must be visible — never `outline: none`",
                    "Use semantic HTML: <button>, <nav>, <main>, <article>",
                    "Minimum 4.5:1 contrast ratio for all body text",
                ],
            }
        ],
    },
    {
        "title": "The State of AI Coding Assistants in 2025",
        "subtitle": "Which tool should you use?",
        "excerpt": "An honest assessment of GitHub Copilot, Cursor, and the emerging wave of AI coding tools.",
        "introduction": "AI coding assistants have crossed the threshold from novelty to productivity multiplier for most working engineers.",
        "conclusion": "The best AI assistant is the one you use consistently and critically — not blindly.",
        "category": "Artificial Intelligence",
        "sections": [
            {
                "type": "table",
                "title": "Tool Comparison",
                "headers": ["Tool", "Strength", "Weakness"],
                "rows": [
                    [
                        "GitHub Copilot",
                        "IDE integration, Enterprise security",
                        "Weaker at architecture",
                    ],
                    ["Cursor", "Agent mode, codebase context", "Subscription cost"],
                    ["Claude Code", "Long context, reasoning", "Terminal-only UX"],
                    [
                        "Gemini Code Assist",
                        "Google ecosystem integration",
                        "Newer, less community data",
                    ],
                ],
            }
        ],
    },
    {
        "title": "Effective Remote Engineering Teams",
        "subtitle": "Async-first culture that actually works",
        "excerpt": "The systems, tools, and norms that make remote engineering teams outperform co-located ones.",
        "introduction": "Remote work done well is not about replicating office life on Zoom — it's a fundamentally different way of organising work.",
        "conclusion": "Async-first teams require more documentation and more explicit communication — and in return they get more focus and autonomy.",
        "category": "Career & Growth",
        "sections": [
            {
                "type": "bullets",
                "title": "Async-First Norms",
                "items": [
                    "Document decisions in writing — Notion, Confluence, or even GitHub issues",
                    "Default to async; use real-time meetings only for high-bandwidth decisions",
                    "Overlap hours should be protected for collaboration, not email",
                    "Response time expectations should be explicit and documented",
                    "Video off is fine; cameras are not a proxy for engagement",
                ],
            }
        ],
    },
    {
        "title": "LLM Safety and Alignment Basics",
        "subtitle": "What engineers need to know",
        "excerpt": "A developer-focused primer on AI safety concepts and how they affect the systems you build.",
        "introduction": "AI safety is no longer a purely academic concern — it has direct implications for engineers building LLM-powered applications.",
        "conclusion": "Safety is a systems property. Every engineer who ships AI systems shares responsibility for its outputs.",
        "category": "Artificial Intelligence",
        "sections": [
            {
                "type": "bullets",
                "title": "Developer Safety Checklist",
                "items": [
                    "Implement prompt injection defences for all user-controlled inputs",
                    "Rate-limit and audit all LLM API calls",
                    "Use structured outputs (JSON mode) to reduce hallucination surface area",
                    "Log all LLM interactions for post-incident analysis",
                    "Test adversarial inputs before launch — jailbreak attempts are inevitable",
                ],
            }
        ],
    },
    {
        "title": "MongoDB Schema Design Patterns",
        "subtitle": "Document model done right",
        "excerpt": "The embedding vs referencing decision and other schema patterns for MongoDB applications.",
        "introduction": "MongoDB's flexible document model is a superpower — until you design schemas that fight against the query patterns you actually have.",
        "conclusion": "Design your schema for your query patterns, not your data relationships. MongoDB rewards query-oriented design.",
        "category": "Web Development",
        "sections": [
            {
                "type": "table",
                "title": "Embedding vs Referencing",
                "headers": ["Factor", "Embed", "Reference"],
                "rows": [
                    ["Relationship size", "Small, bounded", "Large, unbounded"],
                    ["Read pattern", "Always together", "Sometimes separate"],
                    ["Update pattern", "Updated together", "Updated independently"],
                    ["Example", "Post + comments (few)", "Post → Author (shared)"],
                ],
            }
        ],
    },
    {
        "title": "Developer Productivity: Deep Work Principles",
        "subtitle": "Do your best work in less time",
        "excerpt": "How to apply Cal Newport's deep work principles to software engineering.",
        "introduction": "The ability to focus deeply on cognitively demanding tasks is increasingly rare and increasingly valuable in the age of AI and constant notifications.",
        "conclusion": "Protect your deep work hours like your most valuable meetings — because they are.",
        "category": "Career & Growth",
        "sections": [
            {
                "type": "bullets",
                "title": "Deep Work Rules for Engineers",
                "items": [
                    "Block 3–4 hours of uninterrupted coding time each morning",
                    "Close Slack and email during deep work blocks",
                    "Batch shallow work (code review, meetings) into the afternoon",
                    "End each day with a shutdown ritual — write tomorrow's plan",
                    "Measure deep work hours, not hours at the desk",
                ],
            }
        ],
    },
    {
        "title": "Startup vs Big Tech: Making the Choice",
        "subtitle": "Both are right — at different times",
        "excerpt": "An honest comparison of the engineering experience at early-stage startups vs large tech companies.",
        "introduction": "The startup vs big tech decision is one of the most consequential career choices an engineer makes — and it's rarely discussed with appropriate nuance.",
        "conclusion": "Big tech is a university. Startups are a trial by fire. The ideal career alternates between both.",
        "category": "Product & Startups",
        "sections": [
            {
                "type": "table",
                "title": "Experience Comparison",
                "headers": ["Dimension", "Startup (0–50 people)", "Big Tech (1000+ people)"],
                "rows": [
                    ["Ownership", "Enormous — you own everything", "Narrow — you own a subsystem"],
                    [
                        "Learning speed",
                        "Very fast — breadth forced",
                        "Deep — specialisation rewarded",
                    ],
                    [
                        "Compensation",
                        "Lower base, high equity upside",
                        "High base + RSUs, low variance",
                    ],
                    ["Job security", "Low — runway-dependent", "High — layoffs are exceptional"],
                    ["Impact", "Direct and visible", "Hard to attribute"],
                ],
            }
        ],
    },
    {
        "title": "WebAssembly: The Browser's Second Language",
        "subtitle": "Native performance on the web",
        "excerpt": "What WebAssembly is, why it matters, and when you should actually use it.",
        "introduction": "WebAssembly (Wasm) is a binary instruction format that runs in the browser at near-native speed, enabling languages beyond JavaScript on the web.",
        "conclusion": "WebAssembly is not JavaScript's replacement — it's its complement. Use it when performance is the bottleneck and JavaScript can't keep up.",
        "category": "Web Development",
        "sections": [
            {
                "type": "bullets",
                "title": "When to Use WebAssembly",
                "items": [
                    "Heavy computation: image processing, video encoding, cryptography",
                    "Porting existing C/C++/Rust libraries to the browser",
                    "Games with demanding physics or rendering loops",
                    "Scientific simulations that need near-native performance",
                    "NOT for: most web UIs, simple CRUD apps, anything JavaScript can do",
                ],
            }
        ],
    },
    {
        "title": "Event-Driven Architecture Patterns",
        "subtitle": "Decouple everything with events",
        "excerpt": "How to design scalable, resilient systems using events, queues, and asynchronous message passing.",
        "introduction": "Event-driven architecture (EDA) replaces synchronous request/response chains with asynchronous events, dramatically improving system resilience and scalability.",
        "conclusion": "Events are the lingua franca of distributed systems. Design your domain events carefully — they outlive your services.",
        "category": "Cloud & DevOps",
        "sections": [
            {
                "type": "flowchart",
                "title": "Event-Driven Order Flow",
                "steps": [
                    {
                        "id": "order",
                        "title": "Order Placed",
                        "description": "OrderService publishes OrderPlaced event to the message broker.",
                        "color": "blue",
                    },
                    {
                        "id": "inventory",
                        "title": "Inventory Reserved",
                        "description": "InventoryService consumes OrderPlaced and reserves stock.",
                        "color": "green",
                    },
                    {
                        "id": "payment",
                        "title": "Payment Processed",
                        "description": "PaymentService charges the customer and emits PaymentSucceeded.",
                        "color": "purple",
                    },
                    {
                        "id": "notify",
                        "title": "Customer Notified",
                        "description": "NotificationService sends confirmation email on PaymentSucceeded.",
                        "color": "orange",
                    },
                ],
            }
        ],
    },
    {
        "title": "Flutter State Management in 2025",
        "subtitle": "Riverpod, Bloc, or GetX?",
        "excerpt": "A clear-eyed comparison of the leading Flutter state management solutions with real code examples.",
        "introduction": "State management is the most debated topic in Flutter development, and the ecosystem has fragmented into several strong contenders.",
        "conclusion": "Riverpod for new projects. Bloc if your team already knows it. Avoid GetX — the magic hides too many bugs.",
        "category": "Mobile Engineering",
        "sections": [
            {
                "type": "table",
                "title": "State Management Comparison",
                "headers": ["Solution", "Learning Curve", "Boilerplate", "Testability"],
                "rows": [
                    ["Riverpod 2.x", "Medium", "Low", "Excellent"],
                    ["Bloc / Cubit", "High", "High", "Excellent"],
                    ["Provider", "Low", "Low", "Good"],
                    ["GetX", "Low", "Very Low", "Poor"],
                ],
            }
        ],
    },
    {
        "title": "The Engineer's Guide to PostgreSQL",
        "subtitle": "More than just a relational database",
        "excerpt": "PostgreSQL features that every application developer should know but most don't use.",
        "introduction": "PostgreSQL is one of the most feature-rich databases available, but most applications use only 20% of its capabilities.",
        "conclusion": "Before reaching for a specialised database, check whether PostgreSQL already does what you need — it usually does.",
        "category": "Web Development",
        "sections": [
            {
                "type": "bullets",
                "title": "Underused PostgreSQL Features",
                "items": [
                    "JSONB columns — flexible schema within a relational database",
                    "Full-text search — built-in tsvector/tsquery, often good enough",
                    "Row-level security — enforce data access rules in the database",
                    "LISTEN/NOTIFY — lightweight pub/sub for real-time features",
                    "Generated columns — computed fields stored alongside data",
                    "Table partitioning — automatic data archival at scale",
                ],
            }
        ],
    },
]

# ── Playlist definitions ──────────────────────────────────────────────────────

PLAYLISTS_DATA: list[dict] = [
    {
        "name": "AI Engineering Essentials",
        "description": "A curated journey through the foundational concepts every AI engineer must master.",
        "blog_titles": [
            "Understanding Transformer Architecture",
            "Prompt Engineering Best Practices",
            "Building a RAG Pipeline with LangChain",
            "Fine-Tuning vs Prompt Engineering",
            "Vector Databases Demystified",
            "The State of AI Coding Assistants in 2025",
            "LLM Safety and Alignment Basics",
            "FastAPI at Scale: Lessons from Production",
            "Async Python: The Complete Guide",
            "MongoDB Aggregation Pipelines",
        ],
    },
    {
        "name": "Modern Web Development Mastery",
        "description": "From FastAPI backends to database patterns — everything you need to ship robust web services.",
        "blog_titles": [
            "FastAPI at Scale: Lessons from Production",
            "Async Python: The Complete Guide",
            "MongoDB Aggregation Pipelines",
            "REST vs GraphQL vs gRPC",
            "Rate Limiting Strategies for APIs",
            "WebSockets vs Server-Sent Events",
            "SQL Query Optimisation Fundamentals",
            "MongoDB Schema Design Patterns",
            "The Engineer's Guide to PostgreSQL",
            "WebAssembly: The Browser's Second Language",
        ],
    },
    {
        "name": "Design That Wows",
        "description": "Visual design and systems thinking for engineers who want to build beautiful products.",
        "blog_titles": [
            "Building a Design System from Scratch",
            "Typography That Converts",
            "Colour Theory for Developers",
            "Micro-Animations That Feel Premium",
            "Glassmorphism: The Right Way",
            "Accessibility in Modern Web Apps",
            "Micro-Animations That Feel Premium",
            "Typography That Converts",
            "Colour Theory for Developers",
            "Glassmorphism: The Right Way",
        ],
    },
    {
        "name": "Cloud-Native Engineering",
        "description": "Docker, Kubernetes, CI/CD, and observability — the complete DevOps toolkit for app developers.",
        "blog_titles": [
            "Docker for Python Developers",
            "Kubernetes Explained for App Developers",
            "CI/CD with GitHub Actions",
            "Observability: Logs, Metrics, and Traces",
            "Terraform for Python Teams",
            "Event-Driven Architecture Patterns",
            "Rate Limiting Strategies for APIs",
            "WebSockets vs Server-Sent Events",
            "Async Python: The Complete Guide",
            "MongoDB Aggregation Pipelines",
        ],
    },
    {
        "name": "Career & Founder's Path",
        "description": "From salary negotiation to raising a seed round — the meta-skills that define exceptional engineering careers.",
        "blog_titles": [
            "The Staff Engineer Career Path",
            "Negotiating Your Engineering Salary",
            "Code Review Culture",
            "Building a Personal Brand as a Developer",
            "Mastering Technical Interviews",
            "Effective Remote Engineering Teams",
            "Developer Productivity: Deep Work Principles",
            "Startup vs Big Tech: Making the Choice",
            "Zero to One: The Technical Founder's Playbook",
            "Raising a Seed Round: What Investors Actually Look For",
        ],
    },
]


# ── Seeding functions ─────────────────────────────────────────────────────────


async def seed_categories(category_names: list[str]) -> dict[str, object]:
    """
    Insert all blog categories and return a name → document mapping.
    Skips categories that already exist (idempotent).
    """
    from blogging.schemas.blog import BlogCategory

    created: dict[str, object] = {}
    for name in category_names:
        existing = await BlogCategory.find_one(BlogCategory.name == name)
        if existing:
            logger.info("  category already exists — skipping: %s", name)
            created[name] = existing
            continue
        category = BlogCategory(name=name)
        await category.insert()
        created[name] = category
        logger.info("  ✔ category: %s", name)
    return created


async def seed_author() -> object:
    """
    Upsert the seed author user. Returns the User document.
    """
    from backbone.core.models import User

    email = "seed-author@njtechstudio.in"
    existing = await User.find_one(User.email == email)
    if existing:
        logger.info("  seed author already exists — reusing")
        return existing

    import bcrypt

    hashed = bcrypt.hashpw(b"SeedAuthor@2025!", bcrypt.gensalt()).decode()
    user = User(
        email=email,
        full_name="NJ Tech Studio",
        hashed_password=hashed,
        is_active=True,
        is_verified=True,
        is_staff=True,
    )
    await user.insert()
    logger.info("  ✔ seed author created: %s", email)
    return user


def _build_sections(raw_sections: list[dict]) -> list:
    """Convert raw section dicts into typed BlogSection union models."""
    from blogging.schemas.blog import (
        BlogSectionBullets,
        BlogSectionCode,
        BlogSectionFlowchart,
        BlogSectionFlowchartStep,
        BlogSectionImage,
        BlogSectionLinks,
        BlogSectionNote,
        BlogSectionTable,
        BlogSectionText,
    )

    section_map = {
        "text": BlogSectionText,
        "bullets": BlogSectionBullets,
        "table": BlogSectionTable,
        "note": BlogSectionNote,
        "links": BlogSectionLinks,
        "image": BlogSectionImage,
        "code": BlogSectionCode,
        "flowchart": BlogSectionFlowchart,
    }

    result = []
    for raw in raw_sections:
        section_type = raw.get("type", "text")
        cls = section_map.get(section_type, BlogSectionText)

        # Flowchart needs nested step objects
        if section_type == "flowchart" and "steps" in raw:
            raw = dict(raw)
            raw["steps"] = [BlogSectionFlowchartStep(**s) for s in raw["steps"]]

        try:
            result.append(cls(**raw))
        except Exception as exc:
            logger.warning("  Could not parse section %s: %s", section_type, exc)
    return result


async def seed_blogs(
    author: object,
    categories: dict[str, object],
) -> dict[str, object]:
    """
    Insert all 50 seed blog posts. Returns a title → document mapping.
    Skips blogs that already exist (idempotent).
    """

    from blogging.schemas.blog import Blog

    created: dict[str, object] = {}
    base_date = datetime(2024, 1, 1, tzinfo=UTC)

    for i, data in enumerate(BLOGS_DATA):
        title = data["title"]
        existing = await Blog.find_one(Blog.title == title)
        if existing:
            logger.info("  blog already exists — skipping: %s", title)
            created[title] = existing
            continue

        category_name = data.get("category")
        category = categories.get(category_name) if category_name else None

        sections = _build_sections(data.get("sections", []))

        # Spread publish dates across the last 16 months for realistic data
        publish_offset = timedelta(days=i * 9)
        published_date = base_date + publish_offset

        blog = Blog(
            title=title,
            subtitle=data.get("subtitle"),
            excerpt=data["excerpt"],
            introduction=data.get("introduction"),
            conclusion=data.get("conclusion"),
            author=author,
            category=category,
            sections=sections,
            isPublished=True,
            publishedDate=published_date,
            views=random.randint(120, 8500),
            likes=random.randint(10, 420),
        )
        await blog.insert()
        created[title] = blog
        logger.info("  ✔ blog [%02d/50]: %s", i + 1, title)

    return created


async def seed_playlists(
    owner: object,
    blogs_by_title: dict[str, object],
) -> None:
    """
    Create 5 curated playlists, each referencing 10 blogs by title.
    Skips playlists that already exist (idempotent).
    """
    from blogging.schemas.playlist import Playlist

    for data in PLAYLISTS_DATA:
        name = data["name"]
        existing = await Playlist.find_one(Playlist.name == name)
        if existing:
            logger.info("  playlist already exists — skipping: %s", name)
            continue

        linked_blogs = []
        for title in data["blog_titles"]:
            blog = blogs_by_title.get(title)
            if blog:
                linked_blogs.append(blog)
            else:
                logger.warning("  blog not found for playlist '%s': %s", name, title)

        # Deduplicate while preserving order
        seen_ids: set = set()
        unique_blogs = []
        for b in linked_blogs:
            if b.id not in seen_ids:
                unique_blogs.append(b)
                seen_ids.add(b.id)

        playlist = Playlist(
            owner=owner,
            name=name,
            description=data["description"],
            blogs=unique_blogs,
            is_public=True,
        )
        await playlist.insert()
        logger.info("  ✔ playlist: %s (%d blogs)", name, len(unique_blogs))


# ── Main entry point ──────────────────────────────────────────────────────────


async def main() -> None:
    """Bootstrap database connection and run all seed operations."""
    from beanie import init_beanie

    from backbone.core.models import Attachment, Store, User
    from blogging.schemas.blog import Blog, BlogCategory, BlogLike, BlogView
    from blogging.schemas.playlist import Playlist

    mongodb_url = os.getenv("MONGODB_URL", "mongodb://localhost:27017")
    database_name = os.getenv("DATABASE_NAME", "backbone_app")

    logger.info("Connecting to MongoDB: %s / %s", mongodb_url, database_name)
    client = AsyncIOMotorClient(mongodb_url)

    await init_beanie(
        database=client[database_name],
        document_models=[User, Attachment, Store, BlogCategory, Blog, BlogLike, BlogView, Playlist],
    )
    logger.info("Beanie initialised ✔\n")

    # ── 1. Categories ────────────────────────────────────────────────────
    logger.info("── Seeding categories ──────────────────────────────────────")
    category_names = [c["name"] for c in CATEGORIES]
    categories = await seed_categories(category_names)
    logger.info("")

    # ── 2. Author ────────────────────────────────────────────────────────
    logger.info("── Seeding author ──────────────────────────────────────────")
    author = await seed_author()
    logger.info("")

    # ── 3. Blogs ─────────────────────────────────────────────────────────
    logger.info("── Seeding blogs (50 total) ────────────────────────────────")
    blogs_by_title = await seed_blogs(author, categories)
    logger.info("")

    # ── 4. Playlists ─────────────────────────────────────────────────────
    logger.info("── Seeding playlists (5 total) ─────────────────────────────")
    await seed_playlists(author, blogs_by_title)
    logger.info("")

    # ── Summary ───────────────────────────────────────────────────────────
    total_blogs = await Blog.count()
    total_playlists = await Playlist.count()
    total_categories = await BlogCategory.count()

    logger.info("═══════════════════════════════════════════════════════════")
    logger.info("  Seed complete!")
    logger.info("  Categories : %d", total_categories)
    logger.info("  Blogs      : %d", total_blogs)
    logger.info("  Playlists  : %d", total_playlists)
    logger.info("═══════════════════════════════════════════════════════════")

    client.close()


if __name__ == "__main__":
    asyncio.run(main())
