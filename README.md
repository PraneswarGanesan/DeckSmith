# 🧠 Template-Aware Multi-Agent RAG System

## 📌 Overview

This project is a **Template-Aware Multi-Agent RAG System** that converts structured Markdown (`.md`) files into fully formatted presentations (PPT/DOC).

It combines:

* Structured parsing
* Retrieval-Augmented Generation (RAG)
* Multi-agent orchestration
* Template-driven rendering

---

## 🚀 What the System Does

* Accepts structured `.md` files
* Parses them into:

  * Sections
  * Subsections
  * Tables
* Stores structured data in Supabase
* Uses RAG (BM25 + embeddings) for retrieval
* Uses multi-agents (LangChain / LangGraph) to:

  * Plan slides
  * Generate content
  * Generate charts from tables
  * Fetch images (Unsplash)
* Injects content into user-uploaded templates
* Outputs final PPT/DOC files

---

## 🔄 End-to-End Flow

```
Upload MD + Template
        ↓
Supabase Storage
        ↓
Ingestor (parse + store structured data)
        ↓
Embeddings (nomic)
        ↓
Retriever (BM25 + vector)
        ↓
Planner Agent
        ↓
 ├── Content Agent
 ├── Chart Agent
 ├── Image Agent
        ↓
Template Mapper (python-pptx)
        ↓
Final Output (stored in Supabase)
```

---

## 🗄️ Database Schema

### 1. user_profile

Stores user information

| Column        | Type        |
| ------------- | ----------- |
| id            | uuid (PK)   |
| username      | text        |
| email         | text        |
| password_hash | text        |
| created_at    | timestamptz |

---

### 2. user_assets

Tracks uploaded files

| Column       | Type        |
| ------------ | ----------- |
| id           | uuid (PK)   |
| user_id      | uuid (FK)   |
| filename     | text        |
| filetype     | text        |
| storage_path | text        |
| created_at   | timestamptz |

---

### 3. document_structure

Represents one markdown document

| Column            | Type        |
| ----------------- | ----------- |
| id                | uuid (PK)   |
| asset_id          | uuid (FK)   |
| doc_title         | text        |
| executive_summary | text        |
| created_at        | timestamptz |

---

### 4. sections

Represents `##` headings

| Column        | Type        |
| ------------- | ----------- |
| id            | uuid (PK)   |
| doc_id        | uuid (FK)   |
| section_index | int         |
| section_title | text        |
| created_at    | timestamptz |

---

### 5. subsections ⭐ (Main RAG Unit)

| Column           | Type        |
| ---------------- | ----------- |
| id               | uuid (PK)   |
| section_id       | uuid (FK)   |
| subsection_index | int         |
| subsection_title | text        |
| content          | text        |
| summary          | text        |
| keywords         | text[]      |
| embedding        | vector(768) |
| created_at       | timestamptz |

---

### 6. tables_data ⭐ (For Charts)

| Column        | Type        |
| ------------- | ----------- |
| id            | uuid (PK)   |
| subsection_id | uuid (FK)   |
| table_title   | text        |
| headers       | text[]      |
| rows          | jsonb       |
| created_at    | timestamptz |

---

### 7. presentation_templates

| Column            | Type        |
| ----------------- | ----------- |
| id                | uuid (PK)   |
| user_id           | uuid (FK)   |
| template_name     | text        |
| storage_path      | text        |
| placeholders_json | jsonb       |
| created_at        | timestamptz |

---

### 8. generated_outputs

| Column      | Type        |
| ----------- | ----------- |
| id          | uuid (PK)   |
| user_id     | uuid (FK)   |
| template_id | uuid (FK)   |
| output_path | text        |
| status      | text        |
| created_at  | timestamptz |

---

## 📁 Backend Folder Structure

```
backend/
│
├── main.py
├── config.py
├── requirements.txt
├── .env
│
├── agents/
│   ├── ingestor_agent.py
│   ├── retriever_agent.py
│   ├── planner_agent.py
│   ├── content_agent.py
│   ├── chart_agent.py
│   ├── image_agent.py
│   ├── template_agent.py
│
├── services/
│   ├── supabase_client.py
│   ├── embedding_service.py
│   ├── storage_service.py
│
├── utils/
│   ├── markdown_parser.py
│   ├── chunking.py
│   ├── table_parser.py
│   ├── chart_utils.py
│   ├── template_utils.py
│
├── core/
│   ├── graph.py
│   ├── state.py
│
├── routes/
│   ├── upload.py
│   ├── generate.py
│
├── tests/
│   ├── test_ingestor.py
│   ├── test_parser.py
│   ├── test_chart.py
│
└── templates/
    ├── sample.pptx
```

---

## 📄 File Descriptions

### Root

**main.py**

* FastAPI entry point
* Registers routes

**config.py**

* Loads environment variables
* Stores API keys and configs

**.env**

* Secrets (Supabase, Ollama, Unsplash)

**requirements.txt**

* Python dependencies

---

## 🤖 Agents

**ingestor_agent.py**

* Parses markdown
* Stores structured data
* Generates embeddings

**retriever_agent.py**

* Hybrid retrieval (BM25 + vector)

**planner_agent.py**

* Creates slide plan (core logic)

**content_agent.py**

* Formats text for slides

**chart_agent.py**

* Converts tables → charts

**image_agent.py**

* Fetches images from Unsplash

**template_agent.py**

* Injects content into PPT using python-pptx

---

## 🧠 Services

**supabase_client.py**

* Handles DB operations

**embedding_service.py**

* Generates embeddings (Ollama + Nomic)

**storage_service.py**

* Handles file uploads/downloads

---

## 🧰 Utils

**markdown_parser.py**

* Extracts sections & subsections

**table_parser.py**

* Extracts tables into JSON

**chunking.py**

* Optional text splitting

**chart_utils.py**

* Generates charts

**template_utils.py**

* Handles template placeholders

---

## 🔁 Core (LangGraph)

**graph.py**

* Defines agent workflow

**state.py**

* Shared state across agents

---

## 🌐 Routes

**upload.py**

* Upload files to Supabase

**generate.py**

* Runs full pipeline

---

## 🧪 Tests

**test_ingestor.py**

* Tests ingestion pipeline

**test_parser.py**

* Tests markdown parsing

**test_chart.py**

* Tests chart generation

---

## 🎯 System Characteristics

* Structured (hierarchical parsing)
* Template-aware
* Chart-aware
* Multi-agent architecture
* Deterministic output


#Execution Order
```
config.py
main.py

services/
    supabase_client.py
    storage_service.py
    embedding_service.py
    auth_service.py
    user_service.py

utils/
    markdown_parser.py
    table_parser.py
    chart_utils.py
    template_utils.py

agents/
    ingestor_agent.py
    retriever_agent.py
    planner_agent.py
    content_agent.py
    chart_agent.py
    image_agent.py
    template_agent.py

core/
    state.py
    graph.py

routes/
    auth.py
    user.py
    upload.py
    generate.py

tests/
    test_config.py
    test_auth.py
    test_supabase_storage.py
    test_ingestor.py
    test_parser.py
    test_chart.py
```


```
You are helping build a **Template-Aware Multi-Agent RAG System (Production-grade, Hackathon-speed)**.

STRICT RULES:

* Do NOT over-engineer
* Always follow existing database schema and relationships
* Always give FULL working code (no pseudo code)
* Always respect user-centric + table-centric design
* Always enforce storage structure based on username
* Always keep agents modular but deterministic
* Prefer clarity over abstraction

---

🧠 SYSTEM OVERVIEW

We are building:

Template-Aware Multi-Agent RAG System
Structured Markdown → Presentation (PPT/DOC)

Core capabilities:

* Parse structured markdown into hierarchy
* Store in Supabase (relational + vector)
* Retrieve using BM25 + embeddings
* Use multi-agents (LangChain / LangGraph)
* Generate:

  * slide content
  * charts from tables
  * images (Unsplash)
* Inject into templates using python-pptx

---

🔄 SYSTEM FLOW

Upload MD + Template
→ Supabase Storage
→ Ingestor (parse + DB insert)
→ Embeddings (nomic via Ollama)
→ Retriever (BM25 + vector hybrid)
→ Planner Agent (decides slides)
→ Content + Chart + Image Agents
→ Template Agent (python-pptx)
→ Store final output

---

🗄️ DATABASE (STRICT RELATIONAL DESIGN)

Tables:

user_profile
user_assets
document_structure
sections
subsections (MAIN RAG UNIT)
tables_data (FOR CHARTS)
presentation_templates
generated_outputs

RELATION FLOW:

user_profile
→ user_assets
→ document_structure
→ sections
→ subsections
→ tables_data

IMPORTANT:

* Always use foreign keys (no loose mapping)
* Never use filename for linking
* Always use IDs

---

📊 RAG DESIGN

* Only embed: subsections.content
* Each subsection = semantic unit
* tables_data is NOT embedded
* Retrieval:

  * BM25 → keyword match
  * Vector → semantic match
* Combine both

---

📁 STORAGE DESIGN (CRITICAL RULE)

All files MUST be stored like:

{bucket}/{username}/{category}/{filename}

Buckets:

* raw-assets
* generated-output
* images

Structure:

raw-assets/{username}/markdown/
raw-assets/{username}/templates/

generated-output/{username}/outputs/

images/{username}/charts/
images/{username}/unsplash/

RULES:

* NEVER store at root
* ALWAYS include username
* Supabase auto-creates folders (no manual step)
* Always store FULL path in DB

Example:
raw-assets/test_user_123/markdown/1712345678_report.md

---

👤 USER DESIGN (MANDATORY)

* Multi-user system
* No hardcoding test_user_123
* Always pass:
  user_id
  username

Every service/agent must receive:
{
"user_id": "...",
"username": "..."
}

---

📁 BACKEND STRUCTURE

config.py
main.py

services/
supabase_client.py
storage_service.py
embedding_service.py
auth_service.py
user_service.py

utils/
markdown_parser.py
table_parser.py
chart_utils.py
template_utils.py

agents/
ingestor_agent.py
retriever_agent.py
planner_agent.py
content_agent.py
chart_agent.py
image_agent.py
template_agent.py

core/
state.py
graph.py

routes/
auth.py
user.py
upload.py
generate.py

tests/
test_config.py
test_auth.py
test_supabase_storage.py
test_ingestor.py
test_parser.py
test_chart.py

---

🤖 AGENT RULES

Planner Agent = BRAIN (returns structured JSON)

Template Agent = DETERMINISTIC (NO LLM)

Chart Agent:

* Reads tables_data
* Generates matplotlib charts

Image Agent:

* Uses Unsplash API (ACCESS KEY only)

---

🧠 MARKDOWN PARSING RULE

Markdown structure:

# → document title

## → sections

### → subsections

Tables → tables_data

Do NOT chunk randomly
Use hierarchy

---

⚙️ IMPLEMENTATION RULES

When generating code:

1. Mention prerequisites (DB / storage / env)
2. Give FULL file code
3. Follow folder structure strictly
4. Use real DB relations
5. Use username-based storage paths
6. Include test file
7. Include run command

---

🎯 OUTPUT EXPECTATION

* Clean architecture
* Working code
* No hallucinated logic
* Fully connected system
* DB-aware, user-aware, storage-aware

---

REFERENCE CONTEXT:
Use the structured system definition and schema described here: 

---

If anything is unclear:

* Make reasonable assumption
* But DO NOT break schema or storage rules

```