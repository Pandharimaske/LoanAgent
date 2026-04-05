# LoanAgent — The Loan Officer Who Never Forgets

A comprehensive loan management and intelligent agent-based system built with modern web technologies and a powerful Python backend. LoanAgent features an SLM-powered memory layer that allows conversational bank agents to remember applicant details across sessions, days, and multiple interactions.

## 🎯 Overview

LoanAgent is a full-stack application designed to streamline loan processing, management, and decision-making through an intelligent agent-based system. By eliminating the frustrations of repetitive data entry, powered by Local SLMs, LangGraph, ChromaDB, and SQLite, every conversation naturally retains user context to create a seamless customer experience.

## 📊 Tech Stack

### Backend & Orchestration
- **Python Frameworks**: FastAPI, Uvicorn, LangGraph, and Langchain for robust API and session state machine orchestration.
- **Data Validation**: Pydantic for typed entity validation and memory schemas.

### AI & Inference
- **Local Inference**: Ollama running **Qwen2.5-3B-Instruct** for secure, GPU-accelerated local inference.
- **Vector Embeddings**: `sentence-transformers` (`paraphrase-multilingual-MiniLM-L12-v2`) on CPU.
- **Summarization**: Anthropic Claude API for sliding-window conversational chunk compression.
- **NLP**: `langdetect` for dual Hindi & English conversational support.

### Memory & Storage
- **Tier 1 Storage**: **SQLite** for structured, O(1) lookup of fixed entities (e.g., loan amount, income).
- **Tier 2 Storage**: **ChromaDB** for unstructured, dynamic vector memory and semantic search.

### Frontend
- **Web App**: React, JavaScript, Vite, CSS, and HTML for a responsive and modern user interface.
- **Demo Platform**: Streamlit for real-time memory state panel inspection.

## 🏗️ System Architecture & Workflow

The architecture supports a dynamic, real-time conversational workflow with a highly robust 3-tier memory approach:

### The Interaction Workflow (LangGraph State Machine)
1. **Agent Turn Input**: Receives inputs (Hindi, English, or Hinglish via API).
2. **Context Assembly**: `load_memory` retrieves existing knowledge about the customer.
3. **Entity Extraction**: The SLM isolates structured data points from the most recent user message.
4. **Conflict Detection**: Matches newly extracted unstructured facts against the fixed database. If conflicts exist, the agent asks for explicit user clarification.
5. **Context Retrieval**: Compiles fixed facts, Top-5 semantic chunks from ChromaDB, and recent summaries.
6. **Inference**: A context-enriched prompt is passed to the localized Qwen SLM to generate a natural, conversational response.
7. **Sliding-Window Summary**: Triggers conversation compression via the Claude API if token limits are exceeded (reducing context window blow-ups).
8. **End of Session**: Memory is persistently updated, and a session summary is logged in the database.

### 🧠 The 3-Tier Memory Architecture
- **Tier 1 (Structured KV - SQLite)**: Stores fixed, always-relevant loan entities (e.g., EMI amounts, property location) with `PENDING`, `CONFIRMED`, or `RETRACTED` statuses.
- **Tier 2 (Vector Store - ChromaDB)**: Stores conversational chunks with rich metadata. Allows chronological and semantic searches across prior context that doesn't fit standard schemas.
- **Tier 3 (Summary Buffer)**: Retains compressed session logs to supply the prompt prefix for resuming sessions later.

## 🚀 Getting Started

### Prerequisites

- Python 3.8+
- Node.js 16+
- npm or yarn
- Installed and running instance of [Ollama](https://ollama.com/) with `qwen2.5:3b` model
- Valid Anthropic API Key for summarization fallbacks

### Environment Setup

Add the following to a `.env` file in your `backend` directory:
```env
ANTHROPIC_API_KEY=sk-ant-...
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=qwen2.5:3b
EMBED_MODEL=paraphrase-multilingual-MiniLM-L12-v2
TOKEN_THRESHOLD=2000
CHROMA_PATH=./data/chroma_db
SQLITE_PATH=./data/memory.db
SUMMARIZE_LANGUAGE=en
```

### Backend Setup

1. Navigate to the backend directory:
```bash
cd backend
```

2. Create a virtual environment and install dependencies:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
```

3. Ensure Ollama model is downloaded:
```bash
ollama pull qwen2.5:3b
```

4. Run the backend server:
```bash
python main.py
```
*(Depending on implementation, you might also use Streamlit: `streamlit run demo/streamlit_app.py` or `uvicorn api.routes:app`)*

### Frontend Setup

1. Navigate to the frontend directory:
```bash
cd frontend
```

2. Install dependencies:
```bash
npm install
```

3. Start the development server:
```bash
npm run dev
```

## 📁 Project Structure

```
LoanAgent/
├── backend/          # Python FastAPI, LangGraph, Memory Pipeline
├── data/             # Persistent Storage (SQLite & ChromaDB)
├── demo/             # Streamlit Demo interface
├── frontend/         # React + Vite frontend application
├── ps01_master_plan.md # Comprehensive Technical Architecture document
└── README.md         # This file
```

## 🛠️ Development Highlights

- **Data Privacy:** Sensitive fields (like PAN and incomes) are regex-masked locally before hitting external summarization APIs to maintain customer security.
- **Human-in-the-Loop Memory:** Conflicting facts are verified and confirmed by the customer dynamically, ensuring an accurate and clean system of record.
- **Fast Prototyping:** The Streamlit dashboard showcases behind-the-scenes LangGraph workflow changes side-by-side with conversational flow.

## 📝 License

This project is open source and available under the MIT License.

## 👤 Author

[Pandharimaske](https://github.com/Pandharimaske)

## 📞 Support

For questions or issues, please open a GitHub issue in the repository.