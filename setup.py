# setup.py —— design_parser 打包配置
from setuptools import setup, find_packages
from setuptools.command.build_py import build_py
from pathlib import Path

this_dir = Path(__file__).parent

# 读取 requirements.txt
requirements = []
req_path = this_dir / "requirements.txt"
if req_path.exists():
    requirements = [
        line.strip()
        for line in req_path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.startswith("#")
    ]

# 排除无法读取的文件（bom_fiber_parser.py 等）
# 这些文件 os.path.exists 返回 True 但 open() 失败，且无任何模块导入它们
EXCLUDED_MODULES = {'bom_fiber_parser', 'procedure_kb', 'rules_parser'}

class CustomBuildPy(build_py):
    """自定义 build_py 命令，跳过无法读取的文件"""
    def find_package_modules(self, package, package_dir):
        modules = super().find_package_modules(package, package_dir)
        return [
            (pkg, mod, fname) for (pkg, mod, fname) in modules
            if mod not in EXCLUDED_MODULES
        ]

    def build_module(self, module, module_file, package):
        # 跳过无法读取的文件
        module_name = module.split('.')[-1] if '.' in module else module
        if module_name in EXCLUDED_MODULES:
            return
        try:
            return super().build_module(module, module_file, package)
        except (IOError, OSError):
            print(f"  跳过无法读取的文件: {module_file}")
            return

setup(
    name="design_parser",
    version="0.3.0",
    description="通信建筑工程设计文件解析与审查 Agent",
    # fiona 仅提供 3.10~3.13 wheel；3.14+ 由 pyshp 纯 Python 回退，仍可运行
    python_requires=">=3.10,<3.15",
    packages=find_packages(include=["design_parser", "design_parser.*"]),
    # 顶层模块（api.py, schemas.py）
    py_modules=["api", "schemas"],
    package_data={
        "design_parser": ["mappings/*.yaml"],
    },
    # 额外数据文件（UnRAR.exe）
    data_files=[
        ("bin", ["bin/UnRAR.exe"]) if (this_dir / "bin" / "UnRAR.exe").exists() else ("bin", ["UnRAR.exe"]) if (this_dir / "UnRAR.exe").exists() else ("bin", []),
    ],
    install_requires=requirements,
    entry_points={
        "console_scripts": [
            "design-parser-api=api:main",
        ],
    },
    include_package_data=True,
    cmdclass={"build_py": CustomBuildPy},
)
