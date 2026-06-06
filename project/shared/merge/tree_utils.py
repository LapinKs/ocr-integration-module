from typing import List, Optional
from shared.domain.node import Node


def get_node_path(node: Node, target_node: Node, current_path: Optional[List[int]] = None) -> Optional[List[int]]:

    if current_path is None:
        current_path = []
    if node is target_node:
        return current_path
    for i, child in enumerate(node.children):
        result = get_node_path(child, target_node, current_path + [i])
        if result:
            return result
    return None


def get_node_by_path(node: Node, path: List[int]) -> Optional[Node]:

    current = node
    for idx in path:
        if idx < len(current.children):
            current = current.children[idx]
        else:
            return None
    return current
