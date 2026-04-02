
import re
def clean_latex(latex: str) -> str:
    latex = latex.strip()

    latex = re.sub(r'\\hat\{\\hat\{', r'\\hat{', latex)
    latex = latex.replace(r"\\", "")
    latex = re.sub(r'\^\{+', '^{', latex)

    latex = re.sub(r'\{+', '{', latex)
    latex = re.sub(r'\}+', '}', latex)
    if latex.count("\\begin") != latex.count("\\end"):
        return ""

    if latex.count("{") != latex.count("}"):
        return ""
    return latex
def is_valid_latex(latex: str) -> bool:
    if not latex:
        return False
    return True
