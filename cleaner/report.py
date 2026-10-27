"""清洗报告：记录每条规则改了哪些列、改了多少个单元格。"""

from dataclasses import dataclass, field, asdict
from typing import List, Dict, Any


@dataclass
class ReportEntry:
    rule: str            # 规则名，例如 "全角转半角"
    column: str          # 作用的列名
    changed: int         # 该列被改动的单元格数量


@dataclass
class CleanReport:
    entries: List[ReportEntry] = field(default_factory=list)
    failed_dates: List[Dict[str, Any]] = field(default_factory=list)  # 没能解析成日期的原值
    invalid_values: List[Dict[str, Any]] = field(default_factory=list)  # 校验没过的单元格（只标记，不改）

    def add(self, rule: str, column: str, changed: int) -> None:
        if changed > 0:
            self.entries.append(ReportEntry(rule=rule, column=column, changed=changed))

    def total_changed(self) -> int:
        return sum(e.changed for e in self.entries)

    def summary(self) -> str:
        lines = []
        if self.entries:
            lines.append(f"共改动 {self.total_changed()} 个单元格：")
            for e in self.entries:
                lines.append(f"  - [{e.rule}] 列「{e.column}」：改了 {e.changed} 处")
        if self.failed_dates:
            lines.append(f"  - 有 {len(self.failed_dates)} 个日期没识别出来，已原样保留，见清洗后报告。")
        if self.invalid_values:
            lines.append(f"  - 有 {len(self.invalid_values)} 个单元格未通过格式校验，已原样保留。")
        if not lines:
            return "没有需要清洗的内容，表格已经很干净。"
        return "\n".join(lines)

    def as_dict(self) -> Dict[str, Any]:
        return {
            "entries": [asdict(e) for e in self.entries],
            "failed_dates": self.failed_dates,
            "invalid_values": self.invalid_values,
        }
