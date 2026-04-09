# SYSTEM SPECIFICATION: Aegis PPT-Agent Backend (Prototype v3)

## 1. PROJECT OVERVIEW
**Aegis PPT-Agent** is a multi-tenant, agentic microservice that converts large Markdown (.md) files into professional .pptx presentations. It uses a deterministic math engine for layout instead of LLM guessing, adapts to user-uploaded Slide Masters, and generates a full "Performance Script" with speaker notes.

---

## 2. BACKEND FOLDER STRUCTURE
The system MUST follow this structure. Each package requires a `test.py` and a local `requirements.txt`.

/backend
├── main.py                     # FastAPI + JWT Auth + User Middleware
├── .env                        # Credentials (Supabase, Unsplash, Ollama)
├── core_agent/                 # ORCHESTRATION
│   ├── graph.py                # LangGraph definition (Checkpointers + Feedback Loop)
│   ├── states.py               # RLS-aware State (VisualFatigue, User_ID)
│   ├── storyboarder.py         # Content planning logic
│   └── feedback_processor.py   # Partial slide re-generator
├── ingestor/                   # DATA & STORAGE
│   ├── md_parser.py            # Chunker (preserves tables/H-levels)
│   ├── template_analyzer.py    # XML Scanner for Slide Master coordinates
│   └── indexer.py              # Supabase pgvector + BM25 (RLS partition)
├── designer/                   # VISUAL GEN
│   ├── geometry_engine.py      # MATH: Bounding boxes & Collision math
│   ├── infographic_gen.py      # SHAPES: Turning bullets into diagrams
│   ├── chart_factory.py        # DATA: Native PPTX chart creation
│   └── unsplash_client.py      # ASSETS: License-compliant image fetching
├── renderer/                   # ASSEMBLY
│   ├── ppt_engine.py           # Final python-pptx assembly + Notes Pane
│   ├── constraint_mapper.py    # Mapping AI intent to Template placeholders
│   └── style_guard.py          # RGB/Font theme enforcement
├── delivery_expert/            # PERFORMANCE
│   ├── notes_engine.py         # 2-4 line clarifiers + Speaker notes
│   └── script_gen.py           # MD script with cues ([Pause], [Highlight])
└── utils/                      # HELPERS
    ├── ollama_wrapper.py       # Local LLM Interface
    └── auth_helpers.py         # Supabase Auth verification





This architecture operates as a Tenant-Isolated Intelligence Pipeline. It ensures that every user’s data is mathematically separated, highly searchable, and visually optimized for professional presentations.1. User Authentication & Isolated ProvisioningLogin & Handshake: The user authenticates via Supabase Auth (JWT).Tenant Isolation: Upon the first upload, the system creates a unique Row Level Security (RLS) partition in the user_assets table.Vector Store: A private index is initialized in pgvector using the user’s auth.uid as the primary key. This ensures that a search query from User A can never retrieve data belonging to User B.2. High-Fidelity "Content-Aware" IngestionUnlike standard recursive splitters, our Ingestor uses a Semantic Boundary Detector:Structural Parsing: The engine identifies H1 (Title), H2 (Section), and H3 (Sub-section) tags to maintain the document hierarchy.Table Preservation: Tables are extracted as distinct objects. The parser ensures row/column integrity is kept intact so the Chart Factory can later convert them into native PPTX charts.Boundary Detection: It detects logical ends of topics to prevent "sentence splitting," ensuring each chunk is a self-contained idea.3. Metadata & Enrichment EngineFor every chunk generated, the Enrichment Agent runs three parallel processes:Keyword Extraction: Identifies 5–10 core entities (e.g., "Accenture," "GenAI") for BM25 Keyword Search.Contextual Summary: Generates a 1-sentence "Global Context" for the chunk so the LLM understands its place in the larger document.Question Generation: Automatically creates 3 "Potential User Questions" based on the chunk. These are embedded alongside the text to improve Retrieval Accuracy (hitting the chunk even if the user's prompt is vague).4. Template-Guided GenerationTemplate Analysis: When a user uploads a .pptx template, the Template Analyzer scans the XML to find Safe Zones, color palettes (Hex codes), and font pairings.Constraint Mapping: The agent selects the best layout from the user's specific master (e.g., "Two Content" or "Comparison").Visual Enhancement: If a chunk contains bullet points, the Infographic Gen uses the Geometry Engine to draw native shapes (chevrons, boxes) and place text inside them, making the slide visually dynamic rather than text-heavy.5. The Feedback Loop (The "Edit" Flow)User Request: "I want Slide 4 to be a timeline instead of bullets."State Retrieval: The LangGraph identifies Slide 4’s specific metadata and original source chunk.Targeted Re-Gen: The Geometry Engine recalculates new coordinates for a timeline layout.Binary Patch: The Renderer deletes only the objects on Slide 4 and replaces them, leaving the rest of the 15-slide deck untouched.Summary of System TasksComponentResponsibilityTechnical ImplementationIngestorHigh-fidelity parsingMarkdown Regex + Table ExtractorsSupabaseMulti-tenant storagepgvector + RLS Policies + BM25Core AgentStoryboarding & VarietyLangGraph State MachineGeometryLayout & AlignmentDeterministic Coordinate MathDeliveryScripts & Speaker NotesNarrative Synthesis Agent

