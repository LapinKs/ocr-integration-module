# smart_merger.py
import sys
from pathlib import Path
from typing import List, Dict, Tuple, Optional
from bisect import bisect_left, bisect_right

sys.path.insert(0, str(Path(__file__).parent))
from app.infrastructure.merge.optimized_parser import OptimizedPageParser
from app.infrastructure.merge.domain.node import Node
from app.infrastructure.merge.domain.bbox import BBox


class AdaptiveSpatialIndex:
    def __init__(self, lines: List[Node]):
        self.lines = lines
        self.n = len(lines)
        self.last_idx = 0
        self.history = []

    def query(self, bbox: Tuple[int, int, int, int]) -> List[Node]:
        x1, y1, x2, y2 = bbox

        if self.n == 0:
            return []

        start_idx = self._find_start_galloping(y1)
        end_idx = self._find_end_galloping(start_idx, y2)

        result = []
        for i in range(start_idx, min(end_idx, self.n)):
            line = self.lines[i]
            if (line.bbox.x1 < x2 and line.bbox.x2 > x1 and
                line.bbox.y1 < y2 and line.bbox.y2 > y1):
                result.append(line)

        if result:
            self.last_idx = self.lines.index(result[-1])
            self.history.append((y1, y2, start_idx, end_idx))
            if len(self.history) > 10:
                self.history.pop(0)

        return result

    def _find_start_galloping(self, y1: int) -> int:
        idx = self.last_idx

        if idx >= self.n:
            idx = self.n - 1

        if idx < self.n and self.lines[idx].bbox.y2 >= y1:
            while idx > 0 and self.lines[idx - 1].bbox.y2 >= y1:
                idx -= 1
            return idx

        step = 1
        while idx < self.n and self.lines[idx].bbox.y2 < y1:
            idx += step
            step *= 2

        left = max(0, idx - step)
        right = min(self.n - 1, idx)

        while left < right:
            mid = (left + right) // 2
            if self.lines[mid].bbox.y2 < y1:
                left = mid + 1
            else:
                right = mid

        return left

    def _find_end_galloping(self, start_idx: int, y2: int) -> int:
        if start_idx >= self.n:
            return self.n

        idx = start_idx
        step = 1

        while idx < self.n and self.lines[idx].bbox.y1 <= y2:
            idx += step
            step *= 2

        left = start_idx
        right = min(self.n - 1, idx)

        while left < right:
            mid = (left + right + 1) // 2
            if self.lines[mid].bbox.y1 <= y2:
                left = mid
            else:
                right = mid - 1

        return left + 1


class SpatialIndex:
    def __init__(self, root_node: Node, include_types: List[str] = None):
        self.root = root_node
        if include_types is None:
            include_types = ["RIL_TEXTLINE", "RIL_TABLE", "RIL_TABLE_CELL", "RIL_PICTURE", "RIL_FORMULA"]
        self.include_types = include_types
        self.flat_objects = []
        self.y_index = []
        self._build_index()

    def _build_index(self):
        def collect(node: Node):
            if node.type in self.include_types:
                self.flat_objects.append(node)
            for child in node.children:
                collect(child)
        collect(self.root)
        self.flat_objects.sort(key=lambda n: n.bbox.y1)
        self.y_index = [(n.bbox.y1, n.bbox.y2, i) for i, n in enumerate(self.flat_objects)]
        self.y_index.sort(key=lambda x: x[0])

    def query(self, bbox: Tuple[int, int, int, int]) -> List[Node]:
        x1, y1, x2, y2 = bbox
        start_idx = bisect_left(self.y_index, y1, key=lambda item: item[1])
        end_idx = bisect_right(self.y_index, y2, key=lambda item: item[0])
        result = []
        for i in range(start_idx, end_idx):
            obj = self.flat_objects[i]
            if obj.bbox.x1 < x2 and obj.bbox.x2 > x1:
                result.append(obj)
        return result


class BBoxUtils:
    @staticmethod
    def intersects(b1: BBox, b2: BBox) -> bool:
        return not (b1.x2 <= b2.x1 or b1.x1 >= b2.x2 or b1.y2 <= b2.y1 or b1.y1 >= b2.y2)

    @staticmethod
    def intersection_area(b1: BBox, b2: BBox) -> int:
        if not BBoxUtils.intersects(b1, b2):
            return 0
        x1 = max(b1.x1, b2.x1)
        y1 = max(b1.y1, b2.y1)
        x2 = min(b1.x2, b2.x2)
        y2 = min(b1.y2, b2.y2)
        return max(0, x2 - x1) * max(0, y2 - y1)


class MaskUtils:
    @staticmethod
    def word_intersects_mask(word: Node, formula_bbox: Tuple[int, int, int, int],
                              formula_mask: np.ndarray) -> bool:
        if formula_mask is None:
            fx1, fy1, fx2, fy2 = formula_bbox
            wx1, wy1, wx2, wy2 = word.bbox.x1, word.bbox.y1, word.bbox.x2, word.bbox.y2
            return (wx1 < fx2 and wx2 > fx1 and wy1 < fy2 and wy2 > fy1)
        mask_h, mask_w = formula_mask.shape
        fx1, fy1, fx2, fy2 = formula_bbox
        wx1 = max(0, int(word.bbox.x1))
        wy1 = max(0, int(word.bbox.y1))
        wx2 = min(mask_w, int(word.bbox.x2))
        wy2 = min(mask_h, int(word.bbox.y2))
        if wx2 <= wx1 or wy2 <= wy1:
            return False
        submask = formula_mask[wy1:wy2, wx1:wx2]
        if submask.size == 0:
            return False
        import numpy as np
        intersection = np.count_nonzero(submask)
        area = (wx2 - wx1) * (wy2 - wy1)
        ratio = intersection / max(area, 1)
        return ratio > 0.15 or intersection > 15


class BBoxUpdater:
    @staticmethod
    def update_line_bbox(line: Node, on_empty_remove: bool = True):
        if not line.children:
            if on_empty_remove and line.parent and line in line.parent.children:
                line.parent.children.remove(line)
                BBoxUpdater.update_parent_bbox(line.parent)
            return
        min_x = min(c.bbox.x1 for c in line.children)
        min_y = min(c.bbox.y1 for c in line.children)
        max_x = max(c.bbox.x2 for c in line.children)
        max_y = max(c.bbox.y2 for c in line.children)
        line.bbox = BBox(min_x, min_y, max_x, max_y)
        BBoxUpdater.update_parent_bbox(line.parent)

    @staticmethod
    def update_parent_bbox(parent: Node):
        if not parent or not parent.children:
            return
        min_x = min(c.bbox.x1 for c in parent.children)
        min_y = min(c.bbox.y1 for c in parent.children)
        max_x = max(c.bbox.x2 for c in parent.children)
        max_y = max(c.bbox.y2 for c in parent.children)
        parent.bbox = BBox(min_x, min_y, max_x, max_y)
        if parent.parent:
            BBoxUpdater.update_parent_bbox(parent.parent)


class TreeCleaner:
    @staticmethod
    def clean_line_words(line: Node, formula_bbox: Tuple[int, int, int, int],
                         formula_mask: np.ndarray = None):
        new_children = []
        fx1, fy1, fx2, fy2 = formula_bbox
        for child in line.children:
            if child.type == "RIL_WORD":
                if formula_mask is not None:
                    if not MaskUtils.word_intersects_mask(child, formula_bbox, formula_mask):
                        new_children.append(child)
                else:
                    if not (child.bbox.x1 < fx2 and child.bbox.x2 > fx1 and
                            child.bbox.y1 < fy2 and child.bbox.y2 > fy1):
                        new_children.append(child)
            else:
                new_children.append(child)
        line.children = new_children
        if not line.children and line.parent:
            BBoxUpdater.update_line_bbox(line)

    @staticmethod
    def clean_table(table: Node, formula_bbox: Tuple[int, int, int, int]):
        cells_to_remove = []
        fx1, fy1, fx2, fy2 = formula_bbox
        for cell in table.children:
            if cell.type == "RIL_TABLE_CELL":
                if (cell.bbox.x1 < fx2 and cell.bbox.x2 > fx1 and
                    cell.bbox.y1 < fy2 and cell.bbox.y2 > fy1):
                    cells_to_remove.append(cell)
        for cell in cells_to_remove:
            table.children.remove(cell)
        if not table.children and table.parent:
            table.parent.children.remove(table)

    @staticmethod
    def clean_picture(picture: Node):
        if picture.parent:
            picture.parent.children.remove(picture)


class TreeInserter:
    @staticmethod
    def insert_inline(line: Node, formula_node: Node, center_x: float):
        insert_idx = 0
        for i, child in enumerate(line.children):
            if child.type == "RIL_WORD":
                child_center = (child.bbox.x1 + child.bbox.x2) / 2
                if child_center > center_x:
                    insert_idx = i
                    break
            insert_idx = i + 1
        line.children.insert(insert_idx, formula_node)
        formula_node.parent = line
        BBoxUpdater.update_line_bbox(line)

    @staticmethod
    def insert_between_lines(parent: Node, lines: List[Node], formula_node: Node):
        if lines and lines[-1] in parent.children:
            idx = parent.children.index(lines[-1]) + 1
            parent.children.insert(idx, formula_node)
            formula_node.parent = parent
            BBoxUpdater.update_parent_bbox(parent)
        else:
            parent.add_child(formula_node)
            BBoxUpdater.update_parent_bbox(parent)

    @staticmethod
    def insert_as_block(tree: Node, formula_node: Node):
        tree.add_child(formula_node)
        if formula_node.parent:
            BBoxUpdater.update_parent_bbox(formula_node.parent)


class FormulaNodeBuilder:
    @staticmethod
    def create_node(formula_id: int, bbox: Tuple[int, int, int, int],
                    latex: str = None, recognition_status: str = "pending") -> Node:
        x1, y1, x2, y2 = bbox
        data = {
            "@type": "RIL_FORMULA",
            "@X": str(x1),
            "@Y": str(y1),
            "@W": str(x2 - x1),
            "@H": str(y2 - y1),
            "formula_id": formula_id,
            "latex": latex,
            "recognition_status": recognition_status
        }
        return Node(
            type="RIL_FORMULA",
            bbox=BBox(x1, y1, x2, y2),
            data=data
        )


class TreeMerger:
    def __init__(self, use_adaptive_index: bool = True):
        self.use_adaptive_index = use_adaptive_index
        self.spatial_index = None
        self.adaptive_index = None

    def merge_page(self, tree: Node, formulas: List[Dict], use_mask: bool = False) -> Node:
        lines = tree.get_text_lines()

        if self.use_adaptive_index and len(lines) > 0:
            self.adaptive_index = AdaptiveSpatialIndex(lines)
        else:
            self.spatial_index = SpatialIndex(tree)

        formula_nodes = []
        for f in formulas:
            formula_node = FormulaNodeBuilder.create_node(
                f['id'], f['bbox'], f.get('latex'), f.get('recognition_status', 'pending')
            )
            formula_nodes.append(formula_node)
            self._merge_one_formula(tree, formula_node, f.get('mask'), use_mask)

        self._sort_tree(tree)
        return tree

    def _merge_one_formula(self, tree: Node, formula_node: Node,
                           formula_mask: np.ndarray, use_mask: bool):
        fx1, fy1, fx2, fy2 = formula_node.bbox.x1, formula_node.bbox.y1, formula_node.bbox.x2, formula_node.bbox.y2
        formula_center_y = (fy1 + fy2) / 2

        if self.use_adaptive_index and self.adaptive_index is not None:
            candidates = self.adaptive_index.query((fx1, fy1, fx2, fy2))
        else:
            candidates = self.spatial_index.query((fx1, fy1, fx2, fy2))

        text_lines = []
        other_nodes = []
        for node in candidates:
            if node.type == "RIL_TEXTLINE":
                text_lines.append(node)
            else:
                other_nodes.append(node)

        for node in other_nodes:
            self._handle_non_text_node(node, formula_node, formula_mask, use_mask)

        if not text_lines:
            TreeInserter.insert_as_block(tree, formula_node)
            return

        intersecting_lines = []
        for line in text_lines:
            has_intersection = False
            for word in line.children:
                if word.type != "RIL_WORD":
                    continue
                if use_mask and formula_mask is not None:
                    if MaskUtils.word_intersects_mask(word, (fx1, fy1, fx2, fy2), formula_mask):
                        has_intersection = True
                        break
                else:
                    if BBoxUtils.intersects(word.bbox, formula_node.bbox):
                        has_intersection = True
                        break
            if has_intersection:
                intersecting_lines.append(line)
                TreeCleaner.clean_line_words(line, (fx1, fy1, fx2, fy2), formula_mask if use_mask else None)

        remaining_lines = [line for line in intersecting_lines if line in tree.get_text_lines()]

        if len(remaining_lines) == 1:
            self._insert_inline(remaining_lines[0], formula_node)
        elif len(remaining_lines) > 1:
            parent_ids = set(id(line.parent) for line in remaining_lines if line.parent)
            if len(parent_ids) == 1 and remaining_lines[0].parent:
                TreeInserter.insert_between_lines(remaining_lines[0].parent, remaining_lines, formula_node)
            else:
                TreeInserter.insert_as_block(tree, formula_node)
        else:
            TreeInserter.insert_as_block(tree, formula_node)

    def _handle_non_text_node(self, node: Node, formula_node: Node,
                               formula_mask: np.ndarray, use_mask: bool):
        if node.type == "RIL_TABLE":
            TreeCleaner.clean_table(node, (formula_node.bbox.x1, formula_node.bbox.y1,
                                           formula_node.bbox.x2, formula_node.bbox.y2))
        elif node.type == "RIL_PICTURE":
            TreeCleaner.clean_picture(node)
        elif node.type == "RIL_FORMULA":
            if node.parent:
                idx = node.parent.children.index(node)
                node.parent.children[idx] = formula_node
                formula_node.parent = node.parent
        elif node.type == "RIL_TABLE_CELL":
            TreeCleaner.clean_line_words(node, (formula_node.bbox.x1, formula_node.bbox.y1,
                                                formula_node.bbox.x2, formula_node.bbox.y2),
                                         formula_mask if use_mask else None)

    def _insert_inline(self, line: Node, formula_node: Node):
        cx = (formula_node.bbox.x1 + formula_node.bbox.x2) / 2
        insert_idx = 0
        for i, child in enumerate(line.children):
            if child.type == "RIL_WORD":
                child_center = (child.bbox.x1 + child.bbox.x2) / 2
                if child_center > cx:
                    insert_idx = i
                    break
            insert_idx = i + 1
        line.children.insert(insert_idx, formula_node)
        formula_node.parent = line
        BBoxUpdater.update_line_bbox(line)

    def _sort_tree(self, node: Node):
        if node.type in ["RIL_PAGE", "RIL_TEXT", "RIL_LIST_ITEM", "RIL_SECTION_HEADER"]:
            node.children.sort(key=lambda n: n.bbox.y1)
        elif node.type == "RIL_TEXTLINE":
            node.children.sort(key=lambda n: n.bbox.x1)
        for child in node.children:
            self._sort_tree(child)
