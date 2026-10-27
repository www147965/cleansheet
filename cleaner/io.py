"""表格读写：xlsx/csv 的读取与写出，命令行和网页界面共用。"""

from pathlib import Path

import pandas as pd


def read_table(path: Path) -> pd.DataFrame:
    suffix = path.suffix.lower()
    if suffix in (".xlsx", ".xls"):
        return pd.read_excel(path)
    if suffix == ".csv":
        # 中文 csv 常见 gbk 编码，先试 utf-8 再退到 gbk
        try:
            return pd.read_csv(path)
        except UnicodeDecodeError:
            return pd.read_csv(path, encoding="gbk")
    raise ValueError(f"不支持的文件类型：{suffix}（支持 .xlsx / .csv）")


def write_table(df: pd.DataFrame, path: Path) -> None:
    suffix = path.suffix.lower()
    if suffix in (".xlsx", ".xls"):
        df.to_excel(path, index=False)
    elif suffix == ".csv":
        df.to_csv(path, index=False, encoding="utf-8-sig")
    else:
        raise ValueError("输出文件必须是 .xlsx 或 .csv")
