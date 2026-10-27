"""命令行入口：

    python main.py 输入.xlsx -o 输出.xlsx
    python main.py 输入.xlsx -o 输出.xlsx --rules spaces,dates
"""

import argparse
import sys
from pathlib import Path

from cleaner.pipeline import clean_dataframe, DEFAULT_RULES
from cleaner.io import read_table, write_table


def main():
    parser = argparse.ArgumentParser(description="CleanSheet 中文表格一键清洗")
    parser.add_argument("input", help="输入表格路径，支持 .xlsx / .csv")
    parser.add_argument("-o", "--output", required=True, help="输出表格路径")
    parser.add_argument(
        "--rules",
        default=",".join(DEFAULT_RULES),
        help=f"要启用的规则，逗号分隔，可选：{', '.join(DEFAULT_RULES)}。默认全部启用。",
    )
    args = parser.parse_args()

    in_path = Path(args.input)
    out_path = Path(args.output)
    if not in_path.exists():
        sys.exit(f"找不到输入文件：{in_path}")

    df = read_table(in_path)
    rule_names = [r.strip() for r in args.rules.split(",") if r.strip()]
    result = clean_dataframe(df, rule_names)

    write_table(result.df, out_path)
    print(result.report.summary())
    print(f"\n已输出干净表格：{out_path.resolve()}")


if __name__ == "__main__":
    main()
