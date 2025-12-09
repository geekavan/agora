"""
项目工具模块
获取项目结构和上下文信息
"""

import os
import subprocess
import logging

from config import PROJECT_ROOT, AUTO_INCLUDE_TREE, MAX_TREE_DEPTH

logger = logging.getLogger(__name__)


def get_project_tree(root_path: str, max_depth: int = 3) -> str:
    """获取项目目录结构"""
    # 使用tree命令（如果可用）
    try:
        result = subprocess.run(
            ["tree", "-L", str(max_depth), "-I", "__pycache__|*.pyc|node_modules|.git", root_path],
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode == 0:
            return result.stdout
    except (subprocess.TimeoutExpired, FileNotFoundError, subprocess.SubprocessError) as e:
        logger.debug(f"tree command failed: {e}")

    # 降级方案：使用find命令
    try:
        result = subprocess.run(
            ["find", root_path, "-maxdepth", str(max_depth), "-type", "f", "-name", "*.py"],
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode == 0:
            files = result.stdout.strip().split('\n')[:20]
            return "\n".join(files)
    except (subprocess.TimeoutExpired, FileNotFoundError, subprocess.SubprocessError) as e:
        logger.debug(f"find command failed: {e}")

    # 最终降级：使用Python内置os模块
    try:
        files = []
        for root, dirs, filenames in os.walk(root_path):
            depth = root.replace(root_path, '').count(os.sep)
            if depth >= max_depth:
                dirs.clear()
                continue
            for filename in filenames:
                if not filename.startswith('.') and not filename.endswith('.pyc'):
                    files.append(os.path.join(root, filename))
        return "\n".join(files[:20]) if files else "No files found"
    except Exception as e:
        logger.error(f"Failed to read directory: {e}")
        return f"无法读取目录: {root_path}"


def get_project_context() -> str:
    """获取项目上下文信息"""
    if not AUTO_INCLUDE_TREE:
        return ""

    context = f"""
【项目信息】
工作目录: {PROJECT_ROOT}

项目结构:
```
{get_project_tree(PROJECT_ROOT, MAX_TREE_DEPTH)}
```
"""
    return context
