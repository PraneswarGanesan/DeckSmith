def format_for_slide(text: str):
    lines = text.split("\n")
    bullets = [l.strip() for l in lines if l.strip()]

    # truncate for slide readability
    return bullets[:5]