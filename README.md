# EduPrime Support Ticket Triage Agent

An AI agent that reads incoming student support queries, classifies them (refund, batch access, payment, technical, academic doubt), drafts a reply grounded in a knowledge base with verified citations, and decides whether to auto-reply or escalate to a human.

> Work in progress — full README (architecture, models, cost per run, evaluation, limitations) coming soon.

## Stack
- **Backend:** Python 3.12, FastAPI, LangChain + LangGraph, SQLite
- **LLMs:** Google Gemini (Flash-Lite / Flash) with Groq (Llama 3.3 70B) fallback
- **Observability & eval:** LangSmith, scikit-learn
- **Frontend:** React (Vite), Tailwind CSS, Recharts
- **Deploy:** Docker → Hugging Face Spaces (live demo) and Azure
