#!/usr/bin/env python3
import subprocess
from pathlib import Path

def convert_one(docx_path):
    docx_path = Path(docx_path)
    parent = docx_path.parent
    stem = docx_path.stem
    pdf_path = parent / f"{stem}.pdf"
    img_path = parent / f"{stem}.png"

    try:
        # 1. LibreOffice docx -> pdf
        r = subprocess.run(
            ['libreoffice', '--headless', '--convert-to', 'pdf',
             '--outdir', str(parent), str(docx_path)],
            capture_output=True, text=True, timeout=120
        )
        if r.returncode != 0 or not pdf_path.exists():
            return f"LibreOffice失败: {r.stderr[:200]}"

        # 2. ImageMagick 读 PDF 拼接为一页白底长图
        # -background white: 白底
        # -append: 纵向拼接所有页面
        r = subprocess.run(
            ['convert', '-background', 'white', '-append',
             str(pdf_path), str(img_path)],
            capture_output=True, text=True, timeout=120
        )
        if r.returncode != 0:
            return f"ImageMagick失败: {r.stderr[:200]}"

        if not img_path.exists():
            return f"图片未生成"

        pdf_path.unlink(missing_ok=True)
        return "ok"
    except subprocess.TimeoutExpired:
        return "超时"
    except Exception as e:
        return str(e)

def main():
    base = Path("/C20545/jeremyj/pro/volkswagen_intention_eval/data/02_CIDAS场景/CIDAS场景_xml")
    docx_files = sorted(base.rglob("*.docx"))
    print(f"找到 {len(docx_files)} 个 docx\n")

    ok = fail = 0
    for i, p in enumerate(docx_files, 1):
        rel = str(p.relative_to(base))
        print(f"[{i}/{len(docx_files)}] {rel}...", end=" ", flush=True)
        res = convert_one(p)
        if res == "ok":
            print("成功")
            ok += 1
        else:
            print(f"失败: {res}")
            fail += 1

    print(f"\n完成！成功: {ok}, 失败: {fail}")

if __name__ == "__main__":
    main()
