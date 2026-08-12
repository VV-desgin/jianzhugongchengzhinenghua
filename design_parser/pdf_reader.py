import pdfplumber
from pathlib import Path

def extract_text_from_pdf(file_path: str) -> str:
    """提取 PDF 全文文本"""
    if not Path(file_path).exists():
        raise FileNotFoundError(f"PDF 文件不存在: {file_path}")
    text = ""
    try:
        with pdfplumber.open(file_path) as pdf:
            for page in pdf.pages:
                page_text = page.extract_text()
                if page_text:
                    text += page_text + "\n"
    except Exception as e:
        raise RuntimeError(f"PDF 解析失败: {e}")
    return text