"""清洗流水线：按顺序调用规则，并汇总结果。"""

from dataclasses import dataclass

import pandas as pd

from .report import CleanReport
from . import rules


# 规则注册表：名字 -> 函数。命令行和后面的 Streamlit 界面都靠它做开关。
RULES = {
    "fullwidth": rules.normalize_fullwidth,
    "spaces": rules.clean_spaces,
    "unmerge": rules.fill_merged_cells,
    "dates": rules.normalize_dates,
    "numbers": rules.clean_numbers,
    "dedup": rules.drop_duplicate_rows,
    "phone_check": rules.check_phone,
    "id_check": rules.check_idcard,
}

DEFAULT_RULES = list(RULES.keys())


@dataclass
class CleanResult:
    df: pd.DataFrame
    report: CleanReport


def clean_dataframe(df: pd.DataFrame, rule_names=None) -> CleanResult:
    """对 DataFrame 依次执行选中的规则，返回清洗后的表和报告。"""
    if rule_names is None:
        rule_names = DEFAULT_RULES
    report = CleanReport()
    out = df
    for name in rule_names:
        if name not in RULES:
            raise ValueError(f"未知规则：{name}，可选：{list(RULES.keys())}")
        out = RULES[name](out, report)
    return CleanResult(df=out, report=report)
