import ast
import sys

files = [
    'agents/retriever_agent.py',
    'agents/grouper_agent.py',
    'agents/planner_agent.py',
    'agents/content_agent.py',
    'agents/critic_agent.py',
    'agents/visual_composer_agent.py',
    'agents/validator_agent.py',
    'agents/image_agent.py',
    'agents/template_agent.py',
    'tests/test_training_templates.py',
]

ok = 0
bad = 0
for f in files:
    try:
        with open(f, encoding='utf-8') as fh:
            ast.parse(fh.read())
        print(f"  OK  {f}")
        ok += 1
    except Exception as e:
        print(f"  FAIL {f}: {e}")
        bad += 1

print(f"\n{ok} OK, {bad} FAIL")
sys.exit(bad)
