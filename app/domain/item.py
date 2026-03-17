from typing import Union
from app.domain.text import TextBlock
from app.domain.formula import Formula

DocumentItem = Union[TextBlock, Formula]
