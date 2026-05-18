"""Database models for PostgreSQL."""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, List, Dict, Any, Tuple
from enum import Enum


class TaskStatus(str, Enum):
    """Статусы задачи."""
    PENDING = "pending"
    SEGMENTING = "segmenting"
    OCR_PROCESSING = "ocr_processing"
    MERGING = "merging"
    COMPLETED = "completed"
    FAILED = "failed"


class FormulaStatus(str, Enum):
    """Статусы формулы."""
    SEGMENTED = "segmented"
    LATEX_READY = "latex_ready"
    PLACEHOLDER_INSERTED = "placeholder_inserted"
    MERGED = "merged"
    FAILED = "failed"


@dataclass
class TaskRecord:
    """Запись о задаче."""
    task_id: str
    status: TaskStatus
    total_pages: int
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    completed_at: Optional[datetime] = None
    error_message: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_redis_hash(self) -> Dict[str, str]:
        """Преобразует в формат для Redis."""
        return {
            "task_id": self.task_id,
            "status": self.status.value,
            "total_pages": str(self.total_pages),
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else "",
            "error_message": self.error_message or "",
            "metadata": str(self.metadata)
        }

    @classmethod
    def from_redis_hash(cls, data: Dict[bytes, bytes]) -> "TaskRecord":
        """Восстанавливает из Redis."""
        decoded = {k.decode(): v.decode() for k, v in data.items()}
        return cls(
            task_id=decoded["task_id"],
            status=TaskStatus(decoded["status"]),
            total_pages=int(decoded["total_pages"]),
            created_at=datetime.fromisoformat(decoded["created_at"]),
            updated_at=datetime.fromisoformat(decoded["updated_at"]),
            completed_at=datetime.fromisoformat(decoded["completed_at"]) if decoded.get("completed_at") else None,
            error_message=decoded.get("error_message"),
            metadata=eval(decoded.get("metadata", "{}"))
        )


@dataclass
class PageRecord:
    """Запись о странице."""
    task_id: str
    page_index: int
    status: str
    width: int = 0
    height: int = 0
    total_formulas: int = 0
    recognized_count: int = 0
    merged_count: int = 0
    ocr_path: Optional[str] = None
    tree_path: Optional[str] = None
    pdf_path: Optional[str] = None
    error_message: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    def to_redis_hash(self) -> Dict[str, str]:
        """Преобразует в формат для Redis."""
        return {
            "task_id": self.task_id,
            "page_index": str(self.page_index),
            "status": self.status,
            "width": str(self.width),
            "height": str(self.height),
            "total_formulas": str(self.total_formulas),
            "recognized_count": str(self.recognized_count),
            "merged_count": str(self.merged_count),
            "ocr_path": self.ocr_path or "",
            "tree_path": self.tree_path or "",
            "pdf_path": self.pdf_path or "",
            "error_message": self.error_message or "",
            "started_at": self.started_at.isoformat() if self.started_at else "",
            "completed_at": self.completed_at.isoformat() if self.completed_at else ""
        }


@dataclass
class FormulaRecord:
    """Запись о формуле."""
    formula_id: int
    bbox: Tuple[int, int, int, int]
    status: FormulaStatus = FormulaStatus.SEGMENTED
    latex: Optional[str] = None
    confidence: float = 0.0
    mask_path: Optional[str] = None
    placeholder_path: Optional[List[int]] = None
    merged_path: Optional[List[int]] = None
    created_at: datetime = field(default_factory=datetime.now)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_redis_hash(self) -> Dict[str, str]:
        """Преобразует в формат для Redis."""
        import json
        return {
            "formula_id": str(self.formula_id),
            "bbox_x1": str(self.bbox[0]),
            "bbox_y1": str(self.bbox[1]),
            "bbox_x2": str(self.bbox[2]),
            "bbox_y2": str(self.bbox[3]),
            "status": self.status.value,
            "latex": self.latex or "",
            "confidence": str(self.confidence),
            "mask_path": self.mask_path or "",
            "placeholder_path": json.dumps(self.placeholder_path or []),
            "merged_path": json.dumps(self.merged_path or []),
            "created_at": self.created_at.isoformat(),
            "metadata": json.dumps(self.metadata)
        }
