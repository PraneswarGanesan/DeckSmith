# DeckSmith
forges structured, visually compelling presentations from raw Markdown using intelligent templates and agentic workflows. Transforms content into polished slides with automated storytelling, charts, and design consistency.
# 🚀 DeckSmith AI

DeckSmith AI is a production-grade Markdown → PPTX replication engine.

It converts structured Markdown into visually consistent, professional presentations using Slide Master templates, charts, images, and intelligent content mapping.

---

## 🎯 Core Idea

This is NOT a generic generator.

DeckSmith is a **replication engine** that:

* Reads markdown
* Understands structure
* Maps content to predefined slide layouts
* Produces high-quality PPTX outputs

---

## ⚙️ Features

* ✅ Markdown → PPTX conversion
* ✅ Slide Master-based layout system
* ✅ Automatic slide planning (10–15 slides)
* ✅ Content compression (no text overflow)
* ✅ Chart generation from tables
* ✅ Infographic mapping (timeline, comparison, etc.)
* ✅ Unsplash image integration
* ✅ Speaker notes generation
* ✅ Audience-based customization (executive / technical / sales / investor)
* ✅ Modular backend architecture

---

## 🏗️ Architecture

Single unified pipeline:

```
Markdown
 → Ingestion
 → Structuring
 → Storyline (10–15 slides)
 → Content Mapping
 → Template Mapping (Slide Master)
 → Visual Engine (images + charts + infographics)
 → Enhancement Layer
 → PPTX Builder
```

---

## 📁 Project Structure

```
DeckSmith/
│
├── backend/
│   ├── main.py
│   │
│   ├── config/
│   │   ├── settings.py
│   │   └── logger.py
│   │
│   ├── api/
│   │   └── routes.py
│   │
│   ├── pipeline/
│   │   └── orchestrator.py
│   │
│   ├── modules/
│   │   ├── ingestion/
│   │   ├── structuring/
│   │   ├── storyline/
│   │   ├── template/
│   │   ├── content/
│   │   ├── visuals/
│   │   ├── enhancement/
│   │   └── pptx/
│   │
│   ├── storage/
│   │   └── supabase.py
│   │
│   ├── tests/
│   │   ├── test_pipeline.py
│   │   └── test_end_to_end.py
│   │
│   └── requirements.txt
│
├── product_requirments/
│   ├── Sample Files/
│   ├── Slide Master/
│   ├── Test Cases/
│   └── ...
│
├── .venv/
├── .gitignore
├── README.md
└── run.py
```

---

## 🐍 Environment Setup

### 1. Create Virtual Environment (inside root)

```
python -m venv .venv
```

### 2. Activate

**Windows:**

```
.venv\Scripts\activate
```

**Mac/Linux:**

```
source .venv/bin/activate
```

---

## 📦 Install Dependencies

```
pip install -r backend/requirements.txt
```

---

## ▶️ Run Backend

```
python backend/main.py
```

or

```
uvicorn backend.main:app --reload
```

---

## 🧪 Run Tests

```
pytest backend/tests/
```

---

## 🔐 Environment Variables

Create `.env` in root:

```
SUPABASE_URL=your_url
SUPABASE_KEY=your_key
UNSPLASH_ACCESS_KEY=your_key
```

---

## 🚀 Usage

```python
from backend.pipeline.orchestrator import run_pipeline

run_pipeline(
    md_path="input.md",
    output_path="output.pptx",
    audience="executive"
)
```

---

## ⚠️ Constraints

* Slide count must be 10–15
* Must use provided Slide Master
* No text overflow
* Charts required for tabular data
* Output must open in PowerPoint / Google Slides

---

## 🧠 Philosophy

DeckSmith prioritizes:

* Structure over randomness
* Design consistency over creativity
* Reliability over experimentation

---

## 📄 License

MIT License
