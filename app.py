"""CleanSheet 中文表格清洗器的网页界面。

启动方式：
    streamlit run app.py
"""

import tempfile
from io import BytesIO
from pathlib import Path

import pandas as pd
import streamlit as st

from cleaner.pipeline import clean_dataframe, RULES, DEFAULT_RULES
from cleaner.io import read_table, write_table


# 规则 key 到中文说明的映射，没命中就显示 key 本身
RULE_LABELS = {
    "fullwidth": "全角转半角",
    "spaces": "清理空格",
    "unmerge": "合并单元格展开",
    "dates": "日期统一",
    "numbers": "数字清洗",
    "dedup": "整行去重",
    "phone_check": "手机号校验",
    "id_check": "身份证校验",
    "drop_empty": "删除全空行",
    "fill_mean": "数值列均值填空",
    "fill_text": "文本列填未知",
}


def format_rule(key: str) -> str:
    return RULE_LABELS.get(key, key)


st.set_page_config(page_title="CleanSheet 中文表格清洗器")
st.title("🧹 CleanSheet 中文表格清洗器")
st.write("拖一份乱表格进来，勾规则，导出干净表格，全程本地。")


uploaded = st.file_uploader("上传表格", type=["xlsx", "csv"])

if uploaded is None:
    st.info("请先上传一份 .xlsx 或 .csv 文件")
else:
    # 上传对象是内存里的，read_table 需要 Path，所以先落一个临时文件再读，读完删掉
    suffix = Path(uploaded.name).suffix
    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp.write(uploaded.getbuffer())
            tmp_path = Path(tmp.name)

        try:
            raw_df = read_table(tmp_path)
        except Exception as e:
            st.exception(e)
            st.stop()
    finally:
        if tmp_path is not None:
            try:
                tmp_path.unlink()
            except OSError:
                pass

    st.subheader("选择清洗规则")

    # 空值处理策略单独做成单选，避免用户多选
    EMPTY_RULES = ["drop_empty", "fill_mean", "fill_text"]
    empty_labels = {
        "drop_empty": "删除全空行",
        "fill_mean": "数值列用均值填充",
        "fill_text": "文本列填“未知”",
    }
    core_options = [k for k in RULES.keys() if k not in EMPTY_RULES]

    selected = st.multiselect(
        "清洗规则",
        options=core_options,
        default=[],
        format_func=format_rule,
    )

    empty_choice = st.radio(
        "空值怎么处理",
        options=["不处理", "drop_empty", "fill_mean", "fill_text"],
        format_func=lambda x: "保持原样" if x == "不处理" else empty_labels[x],
        horizontal=True,
    )
    if empty_choice != "不处理":
        selected.append(empty_choice)

    if not selected:
        st.warning("请先在上面勾选至少一条清洗规则，或选择一种空值处理方式。")
    elif st.button("开始清洗", type="primary"):
        st.subheader("清洗前")
        st.dataframe(raw_df, use_container_width=True)

        try:
            result = clean_dataframe(raw_df, selected)
        except Exception as e:
            st.exception(e)
            st.stop()

        st.subheader("清洗后")
        st.dataframe(result.df, use_container_width=True)

        st.text(result.report.summary())

        # 把报告里的异常项展开看看
        report_dict = result.report.as_dict()
        failed_dates = report_dict.get("failed_dates", [])
        invalid_values = report_dict.get("invalid_values", [])
        if failed_dates:
            st.warning(f"有 {len(failed_dates)} 个日期没识别出来，已原样保留：")
            st.json(failed_dates)
        if invalid_values:
            st.warning(f"有 {len(invalid_values)} 个单元格未通过格式校验，已原样保留：")
            st.json(invalid_values)

        st.subheader("导出")
        bio = BytesIO()
        result.df.to_excel(bio, index=False)
        bio.seek(0)
        st.download_button(
            label="下载清洗后的 xlsx",
            data=bio.getvalue(),
            file_name="cleaned.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

        report_text = result.report.summary()
        st.download_button(
            label="下载清洗报告 (txt)",
            data=report_text.encode("utf-8"),
            file_name="clean_report.txt",
            mime="text/plain",
        )
