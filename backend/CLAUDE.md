# CLAUDE.md

## 🚀 Project: Multi-Agent AI Presentation Builder

---

## 🎯 Goal

Build a **multi-agent system** that:

* Accepts **Markdown input**
* Uses **RAG (BM25 + Embeddings)** for retrieval
* Uses **LangChain + LangGraph** for orchestration
* Allows users to **upload PPT templates**
* Generates **final presentations automatically**

---

## 🧠 Core System requirment
1. Core Problem Statement
Current AI-generated slides fail in:
● Visual hierarchy (titles, subtitles, body not clearly differentiated)
● Alignment & spacing (elements misaligned, outside margins)
● Overuse of random boxes (no structured layout system)
● Poor visual communication (text-heavy, low infographic usage)
● Inconsistent formatting across slides
2. Mandatory Layout Rules (Non-Negotiable)
A. Grid & Alignment System
● Implement a fixed grid system
● All elements must:
o Snap to grid
o Respect slide margins (no overflow)
● Maintain consistent:
o Padding (inside elements)
o Spacing (between elements)
● No floating or randomly placed elements.
B. Content Hierarchy Enforcement
Every slide must strictly follow:
● Title (Primary message)
● Subtitle (optional) (Context)
● Body Content (Supporting points)
Rules:
● Font sizes must clearly differentiate hierarchy
● Limit to 1 key message per slide
● Avoid mixing multiple hierarchy styles
3. Content Representation Rules
A. Replace Text with Visuals
Avoid:
● Paragraphs
● Bullet overload
Instead use:
● Icons + short labels
● Process flows
● Timelines
● Comparison tables
● Data visuals
B. Infographic First Approach
Before placing text, system should ask:
“Can this be visualized?”
If YES → Convert into:
● Diagram
● Flow
● Structured blocks
If NO → Keep text minimal (max 6–8 lines)
4. Design Consistency Rules
A. Typography
● Max 2 fonts
● Consistent sizes for:
o Title
o Body
o Labels
B. Colors
● Use theme-based palette only
● Avoid random colors per shape
● Maintain contrast for readability
C. Shapes & Elements
● Avoid excessive boxes
● Use:
o Clean containers
o Minimal borders
o Consistent corner radius
5. Spacing & Cleanliness
● Maintain visual breathing space
● No clutter
● Equal spacing between elements
● Align text baselines across shapes
Slides should look balanced, not crowded
6. Slide Quality Checklist (Before Output)
Each slide must pass:
● Proper alignment
● Clear hierarchy (title > content)
● Within margins
● Not text-heavy
● Uses visuals/infographics where possible
● Consistent with other slides
7. What Good Slides Should Feel Like
● Clean, structured, and intentional
● Easy to scan in seconds
● One clear takeaway per slide
● Visually engaging (not box-heavy)
● Professional—not auto-generated looking
## 🧠 Core System Design

### 🔥 Multi-Agent Pipeline

```
User Query
   ↓
Retriever Agent (BM25 + Embeddings)
   ↓
Planner Agent (decides slides)
   ↓
Content Agent (bullets)
   ↓
Chart Agent (tables → charts)
   ↓
Image Agent (images)
   ↓
Critic Agent (refine)
   ↓
Template Agent (build PPT)
   ↓
Output
```

---

## ⚙️ Agents Overview

### 1. Retriever Agent

* Uses:

  * BM25 (rank-bm25)
  * Embeddings (sentence-transformers)
* Fetches:

  * Relevant subsections
  * Tables

---

### 2. Planner Agent

* Input: Query + Retrieved Data
* Output:

```json
[
  {
    "title": "...",
    "subsection_id": "...",
    "type": "content/chart"
  }
]
```

---

### 3. Content Agent

* Converts subsection → bullet points
* Max 5 bullets per slide

---

### 4. Chart Agent

* If table exists:

  * Convert → structured chart data
* (No matplotlib required)

---

### 5. Image Agent

* Generates search query
* Fetches from Unsplash API

---

### 6. Critic Agent

* Improves:

  * Clarity
  * Redundancy
  * Formatting

---

### 7. Template Agent

* Takes:

  * Template file
  * Slides
  * Charts
* Outputs:

  * `.pptx`

---

## 🧱 Backend Architecture

### Framework

* FastAPI

---

### API Flow

```
POST /upload-template
POST /upload-markdown
POST /generate-presentation
GET  /output/{id}
```

---

## 🗄️ Database Design (Supabase)

---

### 1. document_structure

| column            | type |
| ----------------- | ---- |
| id                | uuid |
| asset_id          | uuid |
| doc_title         | text |
| executive_summary | text |

---

### 2. sections

| column        | type |
| ------------- | ---- |
| id            | uuid |
| doc_id        | uuid |
| section_index | int  |
| section_title | text |

---

### 3. subsections

| column           | type   |
| ---------------- | ------ |
| id               | uuid   |
| section_id       | uuid   |
| subsection_index | int    |
| subsection_title | text   |
| content          | text   |
| summary          | text   |
| keywords         | json   |
| embedding        | vector |

---

### 4. tables_data

| column        | type |
| ------------- | ---- |
| id            | uuid |
| subsection_id | uuid |
| table_title   | text |
| headers       | json |
| rows          | json |

---

### 5. presentation_templates

| column       | type |
| ------------ | ---- |
| id           | uuid |
| name         | text |
| storage_path | text |

---

### 6. generated_outputs

| column      | type |
| ----------- | ---- |
| id          | uuid |
| user_id     | uuid |
| template_id | uuid |
| output_path | text |
| status      | text |

---

## 📂 Folder Structure

```
backend/
│
├── agents/
│
├── core/

│
├── services/

│
├── utils/
| --- config.py
│
├── templates/
│   └── *.pptx
│
├── tests/
│
├── main.py
├── requirements.txt
└── .env
```

---

## 🔗 LangGraph Orchestration

```python
retrieve → plan → content → chart → image → critique → template
```

---

## ⚡ Key Design Principles

* Keep agents **independent**
* Avoid heavy dependencies (no pandas/matplotlib)
* Use **pure Python + JSON**
* Prefer **structured outputs**
* Avoid LangChain agent wrappers if unstable
* Use LangGraph for orchestration only

---

## 🔐 Environment Variables

```
SUPABASE_URL=
SUPABASE_SERVICE_KEY=
UNSPLASH_ACCESS_KEY=
LLM_API_KEY=
```

---

## 🧪 Testing Strategy

* Unit test each agent
* Integration test:

  ```
  python -m tests.test_full_agentic
  ```

---

## 🏁 Final Output

* Generated PPT stored in Supabase Storage
* Returned URL to user

---

## 💡 Future Improvements

* Layout intelligence (design system)
* Visual hierarchy scoring
* Auto theme adaptation
* Slide-level personalization

---

## 🧠 Summary

This system is:
* no dependcy issues should arise and build the things for python 1.13 

* Multi-agent
* Retrieval-augmented
* Template-driven
* Fully automated PPT generator

---

1. Core Problem Statement
Current AI-generated slides fail in:
● Visual hierarchy (titles, subtitles, body not clearly differentiated)
● Alignment & spacing (elements misaligned, outside margins)
● Overuse of random boxes (no structured layout system)
● Poor visual communication (text-heavy, low infographic usage)
● Inconsistent formatting across slides
2. Mandatory Layout Rules (Non-Negotiable)
A. Grid & Alignment System
● Implement a fixed grid system
● All elements must:
o Snap to grid
o Respect slide margins (no overflow)
● Maintain consistent:
o Padding (inside elements)
o Spacing (between elements)
● No floating or randomly placed elements.
B. Content Hierarchy Enforcement
Every slide must strictly follow:
● Title (Primary message)
● Subtitle (optional) (Context)
● Body Content (Supporting points)
Rules:
● Font sizes must clearly differentiate hierarchy
● Limit to 1 key message per slide
● Avoid mixing multiple hierarchy styles
3. Content Representation Rules
A. Replace Text with Visuals
Avoid:
● Paragraphs
● Bullet overload
Instead use:
● Icons + short labels
● Process flows
● Timelines
● Comparison tables
● Data visuals
B. Infographic First Approach
Before placing text, system should ask:
“Can this be visualized?”
If YES → Convert into:
● Diagram
● Flow
● Structured blocks
If NO → Keep text minimal (max 6–8 lines)
4. Design Consistency Rules
A. Typography
● Max 2 fonts
● Consistent sizes for:
o Title
o Body
o Labels
B. Colors
● Use theme-based palette only
● Avoid random colors per shape
● Maintain contrast for readability
C. Shapes & Elements
● Avoid excessive boxes
● Use:
o Clean containers
o Minimal borders
o Consistent corner radius
5. Spacing & Cleanliness
● Maintain visual breathing space
● No clutter
● Equal spacing between elements
● Align text baselines across shapes
Slides should look balanced, not crowded
6. Slide Quality Checklist (Before Output)
Each slide must pass:
● Proper alignment
● Clear hierarchy (title > content)
● Within margins
● Not text-heavy
● Uses visuals/infographics where possible
● Consistent with other slides
7. What Good Slides Should Feel Like
● Clean, structured, and intentional
● Easy to scan in seconds
● One clear takeaway per slide
● Visually engaging (not box-heavy)
● Professional—not auto-generated looking
