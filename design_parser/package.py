import os
import sys
import tempfile
import shutil
import fnmatch
from pathlib import Path
from typing import Optional, List, Set
import zipfile
import rarfile
import py7zr

from loguru import logger

# RAR 弹窗一次性抑制：首次运行时抑制 WinRAR 弹窗并写标记文件，后续直接跳过
_RAR_INITIALIZED = False


def _ensure_rar_ready():
    """确保 RAR 解压工具已初始化，弹窗只出现一次。
    """
    global _RAR_INITIALIZED
    if _RAR_INITIALIZED:
        return

    _configure_unrar_path()

    marker = Path(tempfile.gettempdir()) / 'design_parser_rar_ready.marker'
    if not marker.exists():
        _suppress_winrar_popup()
        try:
            marker.write_text('rar backend configured', encoding='utf-8')
        except Exception:
            pass
        logger.info("RAR 解压后端首次初始化完成，后续运行将跳过弹窗")
    else:
        logger.debug("RAR 标记文件已存在，跳过注册表写入")

    _RAR_INITIALIZED = True


def _configure_unrar_path():
    """配置 unrar 工具的完整路径。

     rarfile 默认 UNRAR_TOOL='unrar'，依赖 PATH 查找。
    在打包环境中 PATH 可能不包含 unrar，此处设置完整路径确保可靠找到。
    包含打包内置路径 bin/UnRAR.exe 和常见安装路径。
    """
    # 优先用 PATH 中已有的 unrar
    unrar_path = shutil.which('unrar') or shutil.which('UnRAR')
    if not unrar_path:
        project_root = Path(__file__).parent.parent  # design_parser/ -> project root
        candidates = [
            str(project_root / 'bin' / 'UnRAR.exe'),       # 打包内置 (bin/UnRAR.exe)
            str(project_root / 'UnRAR.exe'),                 # 项目根目录
            str(Path(__file__).parent / 'UnRAR.exe'),        # design_parser/ 目录内
            r'C:\Program Files\WinRAR\UnRAR.exe',
            r'C:\Program Files (x86)\WinRAR\UnRAR.exe',
        ]
        for path in candidates:
            if os.path.exists(path):
                unrar_path = path
                break

    if unrar_path:
        rarfile.UNRAR_TOOL = unrar_path
        try:
            rarfile.tool_setup(force=True)
        except Exception:
            pass
        logger.info(f"unrar 工具路径: {unrar_path}")
    else:
        logger.error("无法找到 UnRAR.exe，RAR 解压将不可用。请确认交付包内 bin/UnRAR.exe 存在（已检查: " + "; ".join(candidates) + "）")


def _suppress_winrar_popup():
    """抑制 WinRAR 共享软件弹窗。

     通过注册表设置 ShowSharewareSplash=0 和 ShowBuyWindow=0，
    使 WinRAR 的购买提示弹窗不再显示。注册表写入一次后永久生效，
    配合标记文件实现"弹窗只出现一次"的效果。
    """
    try:
        import winreg
        key = winreg.CreateKey(winreg.HKEY_CURRENT_USER, r'Software\WinRAR')
        winreg.SetValueEx(key, 'ShowSharewareSplash', 0, winreg.REG_DWORD, 0)
        winreg.SetValueEx(key, 'ShowBuyWindow', 0, winreg.REG_DWORD, 0)
        winreg.CloseKey(key)
        logger.debug("已抑制 WinRAR 共享软件弹窗")
    except Exception as e:
        logger.debug(f"抑制 WinRAR 弹窗失败（非致命）: {e}")


class ProjectPackage:
    """递归解压，队列驱动，安全控制，上下文管理"""

    def __init__(self, archive_path: str, max_depth: int = 10, 
                 max_total_size: int = 1_000_000_000,  # 1GB 上限
                 max_files: int = 10000):
        self.archive_path = Path(archive_path).resolve()
        self.temp_dir = Path(tempfile.mkdtemp(prefix="proj_"))
        self._max_depth = max_depth
        self._max_total_size = max_total_size
        self._max_files = max_files
        self._current_size = 0
        self._file_count = 0
        self._visited: Set[Path] = set()
        self._queue: List[Path] = [self.archive_path]
        self.extract_failures: List[str] = []
        self._process_queue()

    def _process_queue(self):
        """BFS 处理队列，每轮拿出一个压缩文件解压，新产生的压缩包加入队尾"""
        while self._queue:
            src = self._queue.pop(0)
            abs_src = src.resolve()
            if abs_src in self._visited:
                continue
            try:
                rel = abs_src.relative_to(self.temp_dir)
                depth = len(rel.parts)
            except ValueError:
                depth = 0
            if depth > self._max_depth:
                logger.warning(f"达到最大深度 {self._max_depth}，跳过: {src}")
                self._visited.add(abs_src)
                continue

            self._visited.add(abs_src)
            if self.temp_dir in abs_src.parents or abs_src == self.temp_dir:
                dest = abs_src.parent
            else:
                dest = self.temp_dir

            try:
                self._extract_one(abs_src, dest)
            except Exception as e:
                logger.warning(f"解压 {abs_src} 失败: {e}")
                self.extract_failures.append(f"{abs_src}: {e}")
                continue

            if abs_src != self.archive_path and abs_src.exists():
                try:
                    abs_src.unlink()
                except OSError:
                    logger.warning(f"无法删除压缩包 {abs_src}")

            self._enqueue_new_archives(dest)

    def _extract_one(self, src: Path, dest: Path):
        """解压单个压缩文件，带资源限制和安全校验"""
        suffix = src.suffix.lower()
        if suffix in ('.zip', '.qgz'):
            with zipfile.ZipFile(src, 'r') as zf:
                total_size = sum(info.file_size for info in zf.infolist())
                self._check_limits(len(zf.infolist()), total_size)
                self._safe_extract_zip(zf, dest)
                logger.info(f"解压完成: {src.name}（{len(zf.infolist())} 个条目）")
        elif suffix == '.rar':
            _ensure_rar_ready()
            with rarfile.RarFile(src, 'r') as rf:
                self._check_limits(len(rf.infolist()), sum(f.file_size for f in rf.infolist()))
                rf.extractall(dest)
                logger.info(f"解压完成: {src.name}（{len(rf.infolist())} 个条目）")
        elif suffix == '.7z':
            with py7zr.SevenZipFile(src, 'r') as sz:
                infos = sz.list()
                total_size = sum(info.uncompressed for info in infos if hasattr(info, 'uncompressed'))
                self._check_limits(len(infos), total_size)
                sz.extractall(dest)
                logger.info(f"解压完成: {src.name}（{len(infos)} 个条目）")
        elif src.is_file():
            self._check_limits(1, src.stat().st_size)
            shutil.copy2(src, dest / src.name)
        else:
            logger.debug(f"跳过目录或特殊文件: {src}")

    def _safe_extract_zip(self, zf, dest):
        """防止路径穿越的 zip 解压"""
        dest = dest.resolve()
        for member in zf.infolist():
            member_path = (dest / member.filename).resolve()
            if not str(member_path).startswith(str(dest) + os.sep) and member_path != dest:
                raise ValueError(f"路径穿越攻击: {member.filename}")
            if member.is_dir():
                member_path.mkdir(parents=True, exist_ok=True)
            else:
                member_path.parent.mkdir(parents=True, exist_ok=True)
                with zf.open(member) as source, open(member_path, "wb") as target:
                    shutil.copyfileobj(source, target)

    def _check_limits(self, files_add: int, size_add: int):
        """资源上限检查"""
        if self._file_count + files_add > self._max_files:
            raise RuntimeError(f"超过文件数上限 {self._max_files}")
        if self._current_size + size_add > self._max_total_size:
            raise RuntimeError(f"超过总解压大小上限 {self._max_total_size}")
        self._file_count += files_add
        self._current_size += size_add

    def _enqueue_new_archives(self, directory: Path):
        """扫描目录直接子项，将新压缩包入队（避免递归 rglob）"""
        for item in directory.iterdir():
            if item.is_file() and item.suffix.lower() in ('.zip', '.rar', '.7z', '.qgz'):
                if item.resolve() not in self._visited:
                    self._queue.append(item)

    def find_file(self, pattern: str) -> Optional[Path]:
        for path in self.temp_dir.rglob('*'):
            if path.is_file() and fnmatch.fnmatch(path.name, pattern):
                return path
        return None

    def list_all_files(self) -> list:
        return [str(p.relative_to(self.temp_dir)) for p in self.temp_dir.rglob('*') if p.is_file()]

    def cleanup(self):
        if self.temp_dir.exists():
            shutil.rmtree(self.temp_dir, ignore_errors=True)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.cleanup()
        return False

    def __del__(self):
        self.cleanup()
