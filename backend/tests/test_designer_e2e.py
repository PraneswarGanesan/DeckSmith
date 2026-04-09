from designer.agent import DesignerAgent


def test_designer():
    agent = DesignerAgent()

    chunks = [
        {
            "content": "# AI\n- Healthcare\n- Finance",
            "heading": "AI"
        }
    ]

    result = agent.run(chunks)

    print("\n--- DESIGN OUTPUT ---")
    for slide in result:
        print(slide)


if __name__ == "__main__":
    test_designer()