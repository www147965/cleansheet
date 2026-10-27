"""
具体清洗规则。

每条规则都是一个纯函数：输入原始 DataFrame，返回清洗后的新 DataFrame，
并把"改了哪一列、改了多少处"写进 CleanReport。这样做的好处是规则之间
互不干扰，可以单独开关，也方便写单元测试。
"""

import re
import unicodedata

import pandas as pd

from .report import CleanReport


# ---------------------------------------------------------------------------
# 工具：统计一列改动了多少个单元格
# ---------------------------------------------------------------------------
def _count_changed(old: pd.Series, new: pd.Series) -> int:
    """比较前后两列，统计真正发生变化的单元格数量。

    用字符串化比较，避免 NaN != NaN 带来的误判。
    """
    old_s = old.astype("string").fillna("")
    new_s = new.astype("string").fillna("")
    return int((old_s != new_s).sum())


def _is_text_column(series: pd.Series) -> bool:
    return pd.api.types.is_object_dtype(series) or pd.api.types.is_string_dtype(series)


# ---------------------------------------------------------------------------
# 规则 1：全角字符转半角
# ---------------------------------------------------------------------------
def normalize_fullwidth(df: pd.DataFrame, report: CleanReport) -> pd.DataFrame:
    """中文输入最常见的问题：数字、字母、标点是全角的，比如 １２３（）。

    Unicode 的 NFKC 归一化会把全角英数标点映射回半角，中文字符本身不受影响。
    """
    out = df.copy()
    for col in out.columns:
        if not _is_text_column(out[col]):
            continue
        old = out[col]
        new = old.map(lambda v: unicodedata.normalize("NFKC", v) if isinstance(v, str) else v)
        report.add("全角转半角", str(col), _count_changed(old, new))
        out[col] = new
    return out


# ---------------------------------------------------------------------------
# 规则 2：清理空格
# ---------------------------------------------------------------------------
_MULTI_SPACE = re.compile(r"[ \t\u3000]+")  # 普通空格、制表符、中文全角空格

# 两个汉字之间的空格：中文人名、地名里夹的空格基本都是误输入（"张 三"其实就是"张三"）
_CJK_SPACE = re.compile(r"(?<=[一-龥])\s+(?=[一-龥])")

def clean_spaces(df: pd.DataFrame, report: CleanReport) -> pd.DataFrame:
    """去掉首尾空格，把单元格中间连续多个空格压成一个。

    特别处理 \u3000（中文全角空格），它肉眼看不见，却是中文表格常客。
    """
    out = df.copy()
    for col in out.columns:
        if not _is_text_column(out[col]):
            continue
        old = out[col]

        def _fix(v):
            if not isinstance(v, str):
                return v
            s = _MULTI_SPACE.sub(" ", v).strip()
            s = _CJK_SPACE.sub("", s)  # 删汉字之间的空格，跑两遍处理相邻情况
            s = _CJK_SPACE.sub("", s)
            return s

        new = old.map(_fix)
        report.add("清理空格", str(col), _count_changed(old, new))
        out[col] = new
    return out


# ---------------------------------------------------------------------------
# 规则 3：合并单元格展开
# ---------------------------------------------------------------------------
def fill_merged_cells(df: pd.DataFrame, report: CleanReport) -> pd.DataFrame:
    """Excel 里合并过的单元格，用 pandas 读进来后只有左上角有值，下面全是空。

    这是中文报表的重灾区。用向下填充 ffill 把缺失值补成上面那一行的值，
    相当于在逻辑上"展开"了合并单元格。
    """
    out = df.copy()
    for col in out.columns:
        if not _is_text_column(out[col]):
            continue
        old = out[col]
        new = old.ffill()
        report.add("合并单元格展开", str(col), _count_changed(old, new))
        out[col] = new
    return out


# ---------------------------------------------------------------------------
# 规则 4：日期格式统一
# ---------------------------------------------------------------------------
_DATE_KEYWORDS = ("日期", "时间", "date", "time", "生日", "入职")

def _looks_like_date_column(series: pd.Series) -> bool:
    """抽样判断一列是不是日期列：非空样本里能被 pandas 解析成日期的比例要够高。"""
    samples = series.dropna().astype(str).head(20)
    if samples.empty:
        return False
    parsed = pd.to_datetime(samples, errors="coerce", format="mixed")
    return parsed.notna().mean() >= 0.8


def normalize_dates(df: pd.DataFrame, report: CleanReport) -> pd.DataFrame:
    """把 2024/1/5、2024年1月5日、2024.1.5 等乱七八糟的日期统一成 YYYY-MM-DD。

    识别策略：列名带日期关键词，或者抽样解析成功率高的列才处理。
    解析失败的原值保留不动，并记进报告，不擅自删数据。
    """
    out = df.copy()
    for col in out.columns:
        if not _is_text_column(out[col]):
            continue
        col_name = str(col).lower()
        name_hint = any(k in col_name for k in _DATE_KEYWORDS)
        if not (name_hint or _looks_like_date_column(out[col])):
            continue

        old = out[col]

        # 先把中文日期写法规范化：2024年3月8日 -> 2024-3-8
        def _cn_date_to_dash(v):
            if not isinstance(v, str):
                return v
            s = v.strip().replace("年", "-").replace("月", "-").replace("日", "")
            return s

        normalized = old.map(_cn_date_to_dash)
        parsed = pd.to_datetime(normalized, errors="coerce", format="mixed")

        # 记录没解析出来的值，便于人工复核
        for raw, ok in zip(old, parsed.notna()):
            if isinstance(raw, str) and raw.strip() and not ok:
                report.failed_dates.append({"column": str(col), "raw": raw})

        new = parsed.dt.strftime("%Y-%m-%d").where(parsed.notna(), old)
        report.add("日期统一", str(col), _count_changed(old, new))
        out[col] = new
    return out


# ---------------------------------------------------------------------------
# 规则 5：数字清洗
# ---------------------------------------------------------------------------
_AMOUNT = re.compile(r"[¥￥,\s]")

def clean_numbers(df: pd.DataFrame, report: CleanReport) -> pd.DataFrame:
    """把带人民币符号、千分位逗号、'万'/'千' 单位的文本转成纯数字。

    例如 '￥1,200.50' -> 1200.5，'1.2万' -> 12000，'8.5千' -> 8500。
    只处理看起来像金额的文本列，不会动正常的文字列。
    """
    out = df.copy()
    for col in out.columns:
        if not _is_text_column(out[col]):
            continue
        old = out[col]
        samples = old.dropna().astype(str).head(20)
        if samples.empty:
            continue
        # 只有当样本里真的出现货币符号、千分位逗号或"万/千"单位时，才认定这是金额列。
        # 纯数字列（比如手机号、工号）不能动，否则会被错误地转成小数。
        has_money_marker = samples.map(lambda v: bool(re.search(r"[¥￥万千,]", v))).mean()
        if has_money_marker < 0.5:
            continue

        def _to_number(v):
            if not isinstance(v, str):
                return v
            s = _AMOUNT.sub("", v).strip()
            multiplier = 1
            if s.endswith("万"):
                multiplier = 10000
                s = s[:-1]
            elif s.endswith("千"):
                multiplier = 1000
                s = s[:-1]
            try:
                return float(s) * multiplier
            except ValueError:
                return v  # 转不动就原样保留

        new = old.map(_to_number)
        report.add("数字清洗", str(col), _count_changed(old, new))
        out[col] = new
    return out


# ---------------------------------------------------------------------------
# 规则 6：整行去重
# ---------------------------------------------------------------------------
def drop_duplicate_rows(df: pd.DataFrame, report: CleanReport) -> pd.DataFrame:
    """按整行内容判重，完全一样的行只保留第一条。"""
    before = len(df)
    out = df.drop_duplicates(keep="first").reset_index(drop=True)
    removed = before - len(out)
    report.add("整行去重", "(全行)", removed)
    return out


# ---------------------------------------------------------------------------
# 规则 7：手机号格式校验（只标记，不改数据）
# ---------------------------------------------------------------------------
_PHONE_NAME_KEYWORDS = ("手机", "电话", "phone", "mobile", "tel")
_PHONE_RE = re.compile(r"^\d{11}$")


def _as_plain_text(v) -> str:
    """把单元格值转成干净字符串。

    Excel 里长数字列一旦有空值，pandas 会把整列读成 float，
    原本的 13800138000 会变成 1.38e+10 或 13800138000.0，
    这里尽量还原成整数字符串，避免校验误报。
    """
    if isinstance(v, float) and v == int(v):
        return str(int(v))
    return str(v)


def _looks_like_phone_column(series: pd.Series) -> bool:
    """抽样判断一列是不是手机号列：非空前 30 条里纯 11 位数字占比过半。"""
    samples = series.dropna().astype(str).head(30)
    if samples.empty:
        return False
    hit = samples.map(lambda v: bool(_PHONE_RE.match(v.strip())))
    return hit.mean() >= 0.5


def check_phone(df: pd.DataFrame, report: CleanReport) -> pd.DataFrame:
    """逐格检查手机号格式，不合规的写进 report.invalid_values。

    这是"标记"规则：表格内容原样返回，一个格子都不改，只提醒人工复核。
    简单规则：必须 11 位、第 1 位是 1、第 2 位是 3~9。
    """
    out = df.copy()
    for col in out.columns:
        col_name = str(col).lower()
        name_hint = any(k in col_name for k in _PHONE_NAME_KEYWORDS)
        if not (name_hint or _looks_like_phone_column(out[col])):
            continue

        for idx, v in out[col].items():
            if v is None:
                continue
            try:
                if pd.isna(v):
                    continue
            except (TypeError, ValueError):
                pass
            s = _as_plain_text(v).strip()
            if not s:
                continue
            reason = None
            if len(s) != 11:
                reason = "位数不是11"
            elif not s.isdigit() or s[0] != "1" or s[1] not in "3456789":
                reason = "号段格式不对"
            if reason:
                report.invalid_values.append({
                    "column": str(col), "raw": v, "reason": reason, "row": idx,
                })
    return out


# ---------------------------------------------------------------------------
# 规则 8：身份证号格式校验（只标记，不改数据）
# ---------------------------------------------------------------------------
_ID_NAME_KEYWORDS = ("身份证", "id_card", "idcard")
_ID_WEIGHTS = [7, 9, 10, 5, 8, 4, 2, 1, 6, 3, 7, 9, 10, 5, 8, 4, 2]
_ID_CHECK_CODES = ['1', '0', 'X', '9', '8', '7', '6', '5', '4', '3', '2']


def _looks_like_id_column(series: pd.Series) -> bool:
    """抽样判断一列是不是身份证列：18 位（末位可 X）占比过半。"""
    samples = series.dropna().astype(str).head(30)
    if samples.empty:
        return False

    def _ok(v: str) -> bool:
        s = v.strip().upper()
        return len(s) == 18 and s[:17].isdigit() and s[17] in "0123456789X"

    hit = samples.map(_ok)
    return hit.mean() >= 0.5


def check_idcard(df: pd.DataFrame, report: CleanReport) -> pd.DataFrame:
    """逐格检查 18 位身份证号，含国标校验位计算，不合规的写进 report.invalid_values。

    同样是"标记"规则，不改原表。
    校验位算法：前 17 位按权重加权求和 mod 11，对照校验码表得到第 18 位。
    """
    out = df.copy()
    for col in out.columns:
        col_name = str(col).lower()
        name_hint = any(k in col_name for k in _ID_NAME_KEYWORDS)
        if not (name_hint or _looks_like_id_column(out[col])):
            continue

        for idx, v in out[col].items():
            if v is None:
                continue
            try:
                if pd.isna(v):
                    continue
            except (TypeError, ValueError):
                pass
            s = _as_plain_text(v).strip()
            if not s:
                continue
            reason = None
            if len(s) != 18:
                reason = "长度不是18位"
            elif not s[:17].isdigit():
                reason = "前17位必须是数字"
            elif s[17].upper() not in "0123456789X":
                reason = "第18位必须是数字或X"
            else:
                total = sum(int(s[i]) * _ID_WEIGHTS[i] for i in range(17))
                if _ID_CHECK_CODES[total % 11] != s[17].upper():
                    reason = "校验位不正确"
            if reason:
                report.invalid_values.append({
                    "column": str(col), "raw": v, "reason": reason, "row": idx,
                })
    return out


# ---------------------------------------------------------------------------
# 规则 9：删除整行全空的行
# ---------------------------------------------------------------------------
def drop_empty_rows(df: pd.DataFrame, report: CleanReport) -> pd.DataFrame:
    """所有列都为空的行直接删掉。"""
    before = len(df)
    out = df.dropna(how="all").reset_index(drop=True)
    removed = before - len(out)
    report.add("删除空行", "(全行)", removed)
    return out


# ---------------------------------------------------------------------------
# 规则 10：数值列空值用该列均值填充
# ---------------------------------------------------------------------------
def fill_numeric_mean(df: pd.DataFrame, report: CleanReport) -> pd.DataFrame:
    """数值列里的空值，用该列平均值填充。全空的列不动。"""
    out = df.copy()
    for col in out.columns:
        if not pd.api.types.is_numeric_dtype(out[col]):
            continue
        old = out[col]
        nan_count = int(old.isna().sum())
        if nan_count == 0:
            continue
        mean_val = old.mean()
        new = old.fillna(mean_val)
        report.add("数值均值填充", str(col), nan_count)
        out[col] = new
    return out


# ---------------------------------------------------------------------------
# 规则 11：文本列空值填"未知"
# ---------------------------------------------------------------------------
def fill_text_unknown(df: pd.DataFrame, report: CleanReport) -> pd.DataFrame:
    """文本列里的空值，统一填成"未知"。数值列不处理。"""
    out = df.copy()
    for col in out.columns:
        if not _is_text_column(out[col]):
            continue
        old = out[col]
        nan_count = int(old.isna().sum())
        if nan_count == 0:
            continue
        new = old.fillna("未知")
        report.add("文本填空值", str(col), nan_count)
        out[col] = new
    return out
