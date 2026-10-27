"""核心规则的单元测试。

运行：python -m pytest tests/ -v
"""

import pandas as pd

from cleaner.report import CleanReport
from cleaner import rules


def test_fullwidth_to_halfwidth():
    df = pd.DataFrame({"col": ["１２３（４）", "ＡＢＣ"]})
    rep = CleanReport()
    out = rules.normalize_fullwidth(df, rep)
    assert out["col"].iloc[0] == "123(4)"
    assert out["col"].iloc[1] == "ABC"


def test_clean_spaces():
    df = pd.DataFrame({"col": ["  张  三　", "李 四 北京"]})  # \u3000
    rep = CleanReport()
    out = rules.clean_spaces(df, rep)
    assert out["col"].iloc[0] == "张三"      # 汉字之间的空格也要删掉
    assert out["col"].iloc[1] == "李四北京"


def test_fill_merged_cells():
    df = pd.DataFrame({"部门": ["研发部", None, None, "市场部", None]})
    rep = CleanReport()
    out = rules.fill_merged_cells(df, rep)
    assert out["部门"].tolist() == ["研发部", "研发部", "研发部", "市场部", "市场部"]


def test_normalize_dates():
    df = pd.DataFrame({"入职日期": ["2024/1/5", "2024年3月8日", "2024.02.20"]})
    rep = CleanReport()
    out = rules.normalize_dates(df, rep)
    assert out["入职日期"].tolist() == ["2024-01-05", "2024-03-08", "2024-02-20"]


def test_clean_numbers():
    df = pd.DataFrame({"金额": ["￥12,000.50", "1.2万", "9,800"]})
    rep = CleanReport()
    out = rules.clean_numbers(df, rep)
    assert out["金额"].iloc[0] == 12000.5
    assert out["金额"].iloc[1] == 12000
    assert out["金额"].iloc[2] == 9800


def test_drop_duplicates():
    df = pd.DataFrame({"a": [1, 2, 1], "b": ["x", "y", "x"]})
    rep = CleanReport()
    out = rules.drop_duplicate_rows(df, rep)
    assert len(out) == 2


def test_check_phone():
    df = pd.DataFrame({"手机号": ["13812345678", "12345", "22812345678"]})
    rep = CleanReport()
    out = rules.check_phone(df, rep)
    # 表格内容必须原封不动
    assert out["手机号"].tolist() == ["13812345678", "12345", "22812345678"]
    # 合规号不记
    raws = [item["raw"] for item in rep.invalid_values]
    assert "13812345678" not in raws
    # 两个不合规各记一条
    assert raws.count("12345") == 1
    assert raws.count("22812345678") == 1
    reasons = {item["reason"] for item in rep.invalid_values}
    assert "位数不是11" in reasons
    assert "号段格式不对" in reasons


def test_phone_float_repr():
    # Excel 长数字列遇空值会被读成 float，13812345678.0 不应被判为不合规
    df = pd.DataFrame({"手机号": [13812345678.0, 12345.0]})
    rep = CleanReport()
    rules.check_phone(df, rep)
    raws = [item["raw"] for item in rep.invalid_values]
    # 11 位那个还原成整数后是合规的，不该出现在异常列表
    assert 13812345678.0 not in raws
    assert len(rep.invalid_values) == 1  # 只有 12345 那个是错的


def test_check_idcard():
    # 110101199003077758 的校验位是按国标算过的，合法
    good = "110101199003077758"
    bad_check = "110101199003077759"   # 把最后一位 8 改成 9，校验位错
    short = "11010119900307775"        # 只有 17 位
    df = pd.DataFrame({"身份证号": [good, bad_check, short]})
    rep = CleanReport()
    out = rules.check_idcard(df, rep)
    # 原表不动
    assert out["身份证号"].tolist() == [good, bad_check, short]
    raws = [item["raw"] for item in rep.invalid_values]
    assert good not in raws
    assert bad_check in raws
    assert short in raws
    reasons = {item["reason"] for item in rep.invalid_values}
    assert "校验位不正确" in reasons
    assert "长度不是18位" in reasons


def test_pipeline_phone_and_id_check():
    from cleaner.pipeline import clean_dataframe
    df = pd.DataFrame({
        "手机号": ["13812345678", "12345"],
        "身份证号": ["110101199003077758", "110101199003077759"],
    })
    result = clean_dataframe(df, ["phone_check", "id_check"])
    # 一共 2 条不合规：手机号 1 条 + 身份证 1 条
    assert len(result.report.invalid_values) == 2
    # 原表完全没动
    assert result.df["手机号"].tolist() == ["13812345678", "12345"]
    assert result.df["身份证号"].tolist() == ["110101199003077758", "110101199003077759"]
    # as_dict 里能导出 invalid_values
    assert "invalid_values" in result.report.as_dict()


def test_drop_empty_rows():
    df = pd.DataFrame({"姓名": ["张三", None, "李四"], "月薪": [100, None, 200]})
    rep = CleanReport()
    out = rules.drop_empty_rows(df, rep)
    assert len(out) == 2  # 中间那行全空被删了
    assert out["姓名"].tolist() == ["张三", "李四"]


def test_fill_numeric_mean():
    df = pd.DataFrame({"月薪": [100, None, 300]})
    rep = CleanReport()
    out = rules.fill_numeric_mean(df, rep)
    assert out["月薪"].tolist() == [100, 200, 300]  # 均值 200


def test_fill_text_unknown():
    df = pd.DataFrame({"姓名": ["张三", None, "李四"]})
    rep = CleanReport()
    out = rules.fill_text_unknown(df, rep)
    assert out["姓名"].tolist() == ["张三", "未知", "李四"]
