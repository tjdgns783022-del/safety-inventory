# Main.py
# 안전창고 재고관리 시스템 V5.4
# 목적: 창고별 재고조사 + 구매필요목록 확인 + 엑셀 출력
# 입고/출고 기능 제거 버전

import streamlit as st
import pandas as pd
from datetime import datetime
from io import BytesIO
from supabase import create_client, Client

st.set_page_config(
    page_title="안전창고 재고관리 시스템 V5.4",
    page_icon="📦",
    layout="wide"
)

APP_VERSION = "V5.4"

PURCHASE_ACCOUNTS = ["일반수선비", "안전보호구"]

WAREHOUSE_MAP = {
    "1창고": "warehouse_1_qty",
    "2창고": "warehouse_2_qty",
    "기자재실": "material_room_qty"
}

WAREHOUSE_NAMES = ["1창고", "2창고", "기자재실"]


# =========================================================
# Supabase 연결
# =========================================================
@st.cache_resource
def init_supabase() -> Client:
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_KEY"]
    return create_client(url, key)


supabase = init_supabase()


# =========================================================
# 공통 함수
# =========================================================
def now_text():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def safe_int(value, default=0):
    try:
        if value is None or value == "":
            return default
        return int(float(value))
    except Exception:
        return default


def format_won(value):
    return f"{safe_int(value):,}원"


def normalize_account(value):
    if value in PURCHASE_ACCOUNTS:
        return value
    return "일반수선비"


def to_excel_bytes(df_dict):
    output = BytesIO()

    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        for sheet_name, df in df_dict.items():
            safe_sheet_name = str(sheet_name)[:31]
            df.to_excel(writer, index=False, sheet_name=safe_sheet_name)

    output.seek(0)
    return output.getvalue()


# =========================================================
# 데이터 조회
# =========================================================
def load_items():
    required_cols = {
        "id": 0,
        "item_name": "",
        "unit": "EA",
        "warehouse_1_qty": 0,
        "warehouse_2_qty": 0,
        "material_room_qty": 0,
        "optimal_stock": 0,
        "unit_price": 0,
        "purchase_account": "일반수선비",
        "created_at": "",
        "updated_at": ""
    }

    try:
        result = supabase.table("items").select("*").order("id").execute()
        df = pd.DataFrame(result.data or [])

        if df.empty:
            return pd.DataFrame(columns=list(required_cols.keys()))

        for col, default_value in required_cols.items():
            if col not in df.columns:
                df[col] = default_value

        number_cols = [
            "warehouse_1_qty",
            "warehouse_2_qty",
            "material_room_qty",
            "optimal_stock",
            "unit_price"
        ]

        for col in number_cols:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0).astype(int)

        df["item_name"] = df["item_name"].fillna("").astype(str)
        df["unit"] = df["unit"].fillna("EA").astype(str)
        df["purchase_account"] = df["purchase_account"].apply(normalize_account)

        return df[list(required_cols.keys())]

    except Exception as e:
        st.error(f"품목 데이터 조회 오류: {e}")
        return pd.DataFrame(columns=list(required_cols.keys()))


# =========================================================
# 데이터 저장
# =========================================================
def add_item(item_name, unit, optimal_stock, unit_price, purchase_account):
    data = {
        "item_name": item_name.strip(),
        "unit": unit.strip() if unit else "EA",
        "warehouse_1_qty": 0,
        "warehouse_2_qty": 0,
        "material_room_qty": 0,
        "optimal_stock": safe_int(optimal_stock),
        "unit_price": safe_int(unit_price),
        "purchase_account": normalize_account(purchase_account),
        "created_at": now_text(),
        "updated_at": now_text()
    }

    try:
        supabase.table("items").insert(data).execute()
        return True
    except Exception as e:
        st.error(f"품목 등록 오류: {e}")
        return False


def update_item(item_id, item_name, unit, optimal_stock, unit_price, purchase_account):
    data = {
        "item_name": item_name.strip(),
        "unit": unit.strip() if unit else "EA",
        "optimal_stock": safe_int(optimal_stock),
        "unit_price": safe_int(unit_price),
        "purchase_account": normalize_account(purchase_account),
        "updated_at": now_text()
    }

    try:
        supabase.table("items").update(data).eq("id", item_id).execute()
        return True
    except Exception as e:
        st.error(f"품목 수정 오류: {e}")
        return False


def delete_item(item_id):
    try:
        supabase.table("items").delete().eq("id", item_id).execute()
        return True
    except Exception as e:
        st.error(f"품목 삭제 오류: {e}")
        return False


def update_stock_all(item_id, warehouse_1_qty, warehouse_2_qty, material_room_qty):
    data = {
        "warehouse_1_qty": safe_int(warehouse_1_qty),
        "warehouse_2_qty": safe_int(warehouse_2_qty),
        "material_room_qty": safe_int(material_room_qty),
        "updated_at": now_text()
    }

    try:
        supabase.table("items").update(data).eq("id", item_id).execute()
        return True
    except Exception as e:
        st.error(f"재고 저장 오류: {e}")
        return False


def update_stock_one(item_id, warehouse_col, qty):
    data = {
        warehouse_col: safe_int(qty),
        "updated_at": now_text()
    }

    try:
        supabase.table("items").update(data).eq("id", item_id).execute()
        return True
    except Exception as e:
        st.error(f"재고 저장 오류: {e}")
        return False


# =========================================================
# 표시용 데이터 생성
# =========================================================
def make_inventory_all_df(df):
    result = df.copy()

    result["합계"] = (
        result["warehouse_1_qty"]
        + result["warehouse_2_qty"]
        + result["material_room_qty"]
    )
    result["총금액"] = result["합계"] * result["unit_price"]
    result["재고상태"] = result.apply(
        lambda row: "구매필요" if safe_int(row["합계"]) < safe_int(row["optimal_stock"]) else "정상",
        axis=1
    )

    result = result.rename(columns={
        "id": "ID",
        "item_name": "품목명",
        "unit": "단위",
        "warehouse_1_qty": "1창고",
        "warehouse_2_qty": "2창고",
        "material_room_qty": "기자재실",
        "optimal_stock": "적정재고",
        "unit_price": "단가",
        "purchase_account": "구매계정"
    })

    return result[[
        "ID",
        "품목명",
        "단위",
        "1창고",
        "2창고",
        "기자재실",
        "합계",
        "적정재고",
        "단가",
        "구매계정",
        "총금액",
        "재고상태"
    ]]


def make_inventory_one_df(df, warehouse_name):
    warehouse_col = WAREHOUSE_MAP[warehouse_name]

    result = df.copy()
    result["현재재고"] = result[warehouse_col]
    result["총금액"] = result["현재재고"] * result["unit_price"]
    result["재고상태"] = result.apply(
        lambda row: "구매필요" if safe_int(row["현재재고"]) < safe_int(row["optimal_stock"]) else "정상",
        axis=1
    )

    result = result.rename(columns={
        "id": "ID",
        "item_name": "품목명",
        "unit": "단위",
        "optimal_stock": "적정재고",
        "unit_price": "단가",
        "purchase_account": "구매계정"
    })

    return result[[
        "ID",
        "품목명",
        "단위",
        "현재재고",
        "적정재고",
        "단가",
        "구매계정",
        "총금액",
        "재고상태"
    ]]


def make_purchase_df(df, stock_base):
    result = df.copy()

    if stock_base == "전체":
        result["현재재고"] = (
            result["warehouse_1_qty"]
            + result["warehouse_2_qty"]
            + result["material_room_qty"]
        )
    else:
        result["현재재고"] = result[WAREHOUSE_MAP[stock_base]]

    result["구매필요수량"] = result["optimal_stock"] - result["현재재고"]
    result["구매필요수량"] = result["구매필요수량"].apply(lambda x: x if x > 0 else 0)
    result["구매금액"] = result["구매필요수량"] * result["unit_price"]

    result = result[result["구매필요수량"] > 0].copy()

    result = result.rename(columns={
        "item_name": "품목명",
        "unit": "단위",
        "warehouse_1_qty": "1창고",
        "warehouse_2_qty": "2창고",
        "material_room_qty": "기자재실",
        "optimal_stock": "적정재고",
        "unit_price": "단가",
        "purchase_account": "구매계정"
    })

    if stock_base == "전체":
        return result[[
            "품목명",
            "단위",
            "1창고",
            "2창고",
            "기자재실",
            "현재재고",
            "적정재고",
            "구매필요수량",
            "단가",
            "구매금액",
            "구매계정"
        ]]
    else:
        return result[[
            "품목명",
            "단위",
            "현재재고",
            "적정재고",
            "구매필요수량",
            "단가",
            "구매금액",
            "구매계정"
        ]]


# =========================================================
# 앱 시작
# =========================================================
st.title(f"📦 안전창고 재고관리 시스템 {APP_VERSION}")

menu = st.sidebar.radio(
    "메뉴 선택",
    [
        "재고현황",
        "품목관리",
        "구매필요목록"
    ]
)

items_df = load_items()


# =========================================================
# 재고현황
# =========================================================
if menu == "재고현황":
    st.subheader("📋 재고현황 / 창고별 재고조사")

    col1, col2 = st.columns(2)

    with col1:
        selected_warehouse = st.selectbox(
            "창고 선택",
            ["전체"] + WAREHOUSE_NAMES
        )

    with col2:
        keyword = st.text_input("품목명 검색")

    df = items_df.copy()

    if keyword:
        df = df[df["item_name"].astype(str).str.contains(keyword, case=False, na=False)]

    if df.empty:
        st.info("등록된 품목이 없습니다.")
    else:
        if selected_warehouse == "전체":
            st.info("전체 선택 시 1창고, 2창고, 기자재실 재고를 모두 수정할 수 있습니다.")

            display_df = make_inventory_all_df(df)

            edited_df = st.data_editor(
                display_df,
                use_container_width=True,
                hide_index=True,
                disabled=[
                    "ID",
                    "품목명",
                    "단위",
                    "합계",
                    "적정재고",
                    "단가",
                    "구매계정",
                    "총금액",
                    "재고상태"
                ],
                column_config={
                    "1창고": st.column_config.NumberColumn("1창고", min_value=0, step=1),
                    "2창고": st.column_config.NumberColumn("2창고", min_value=0, step=1),
                    "기자재실": st.column_config.NumberColumn("기자재실", min_value=0, step=1)
                }
            )

            if st.button("재고 저장", type="primary"):
                success_count = 0

                for _, row in edited_df.iterrows():
                    if update_stock_all(
                        row["ID"],
                        row["1창고"],
                        row["2창고"],
                        row["기자재실"]
                    ):
                        success_count += 1

                st.success(f"재고가 저장되었습니다. 저장 품목 수: {success_count}개")
                st.rerun()

            metric_df = make_inventory_all_df(df)

        else:
            st.info(f"{selected_warehouse} 재고만 수정할 수 있습니다.")

            display_df = make_inventory_one_df(df, selected_warehouse)

            edited_df = st.data_editor(
                display_df,
                use_container_width=True,
                hide_index=True,
                disabled=[
                    "ID",
                    "품목명",
                    "단위",
                    "적정재고",
                    "단가",
                    "구매계정",
                    "총금액",
                    "재고상태"
                ],
                column_config={
                    "현재재고": st.column_config.NumberColumn("현재재고", min_value=0, step=1)
                }
            )

            if st.button("재고 저장", type="primary"):
                success_count = 0
                warehouse_col = WAREHOUSE_MAP[selected_warehouse]

                for _, row in edited_df.iterrows():
                    if update_stock_one(
                        row["ID"],
                        warehouse_col,
                        row["현재재고"]
                    ):
                        success_count += 1

                st.success(f"{selected_warehouse} 재고가 저장되었습니다. 저장 품목 수: {success_count}개")
                st.rerun()

            metric_df = make_inventory_one_df(df, selected_warehouse)

        m1, m2, m3 = st.columns(3)

        m1.metric("표시 품목 수", f"{len(metric_df):,}개")
        m2.metric("구매필요 품목 수", f"{len(metric_df[metric_df['재고상태'] == '구매필요']):,}개")
        m3.metric("표시 기준 재고금액", format_won(metric_df["총금액"].sum()))


# =========================================================
# 품목관리
# =========================================================
elif menu == "품목관리":
    st.subheader("🛠 품목관리")

    tab1, tab2 = st.tabs(["품목 등록", "품목 수정 / 삭제"])

    with tab1:
        st.markdown("### 신규 품목 등록")

        with st.form("add_item_form"):
            col1, col2 = st.columns(2)

            with col1:
                item_name = st.text_input("품목명")
                unit = st.text_input("단위", value="EA")

            with col2:
                optimal_stock = st.number_input("적정재고", min_value=0, step=1)
                unit_price = st.number_input("단가", min_value=0, step=100)
                purchase_account = st.selectbox("구매계정", PURCHASE_ACCOUNTS)

            st.info("재고 수량은 재고현황 메뉴에서만 입력합니다.")

            submitted = st.form_submit_button("등록")

            if submitted:
                if not item_name.strip():
                    st.warning("품목명을 입력해주세요.")
                else:
                    if add_item(
                        item_name,
                        unit,
                        optimal_stock,
                        unit_price,
                        purchase_account
                    ):
                        st.success("품목이 등록되었습니다.")
                        st.rerun()

    with tab2:
        st.markdown("### 기존 품목 수정 / 삭제")

        if items_df.empty:
            st.info("등록된 품목이 없습니다.")
        else:
            item_options = {
                f"{row['id']} - {row['item_name']}": row
                for _, row in items_df.iterrows()
            }

            selected_label = st.selectbox("수정할 품목 선택", list(item_options.keys()))
            selected_item = item_options[selected_label]

            with st.form("edit_item_form"):
                col1, col2 = st.columns(2)

                with col1:
                    edit_item_name = st.text_input(
                        "품목명",
                        value=str(selected_item.get("item_name", ""))
                    )
                    edit_unit = st.text_input(
                        "단위",
                        value=str(selected_item.get("unit", "EA"))
                    )

                with col2:
                    edit_optimal_stock = st.number_input(
                        "적정재고",
                        min_value=0,
                        step=1,
                        value=safe_int(selected_item.get("optimal_stock", 0))
                    )
                    edit_unit_price = st.number_input(
                        "단가",
                        min_value=0,
                        step=100,
                        value=safe_int(selected_item.get("unit_price", 0))
                    )

                    current_account = normalize_account(
                        selected_item.get("purchase_account", "일반수선비")
                    )

                    edit_purchase_account = st.selectbox(
                        "구매계정",
                        PURCHASE_ACCOUNTS,
                        index=PURCHASE_ACCOUNTS.index(current_account)
                    )

                st.info("재고 수량은 재고현황 메뉴에서만 수정합니다.")

                col_save, col_delete = st.columns(2)

                save_clicked = col_save.form_submit_button("수정 저장")
                delete_clicked = col_delete.form_submit_button("삭제")

                if save_clicked:
                    if not edit_item_name.strip():
                        st.warning("품목명을 입력해주세요.")
                    else:
                        if update_item(
                            selected_item["id"],
                            edit_item_name,
                            edit_unit,
                            edit_optimal_stock,
                            edit_unit_price,
                            edit_purchase_account
                        ):
                            st.success("품목 정보가 수정되었습니다.")
                            st.rerun()

                if delete_clicked:
                    if delete_item(selected_item["id"]):
                        st.success("품목이 삭제되었습니다.")
                        st.rerun()


# =========================================================
# 구매필요목록
# =========================================================
elif menu == "구매필요목록":
    st.subheader("🛒 구매필요목록")

    if items_df.empty:
        st.info("등록된 품목이 없습니다.")
    else:
        filter_col1, filter_col2, filter_col3 = st.columns(3)

        with filter_col1:
            stock_base = st.selectbox(
                "재고 기준",
                ["전체"] + WAREHOUSE_NAMES
            )

        with filter_col2:
            account_filter = st.selectbox(
                "구매계정",
                ["전체"] + PURCHASE_ACCOUNTS
            )

        with filter_col3:
            sort_option = st.selectbox(
                "정렬",
                ["구매금액 큰순", "구매필요수량 큰순", "품목명순"]
            )

        purchase_df = make_purchase_df(items_df, stock_base)

        if account_filter != "전체":
            purchase_df = purchase_df[purchase_df["구매계정"] == account_filter]

        if sort_option == "구매금액 큰순":
            purchase_df = purchase_df.sort_values("구매금액", ascending=False)
        elif sort_option == "구매필요수량 큰순":
            purchase_df = purchase_df.sort_values("구매필요수량", ascending=False)
        else:
            purchase_df = purchase_df.sort_values("품목명", ascending=True)

        if purchase_df.empty:
            st.success("현재 구매가 필요한 품목이 없습니다.")
        else:
            total_amount = purchase_df["구매금액"].sum()
            total_qty = purchase_df["구매필요수량"].sum()

            m1, m2, m3 = st.columns(3)
            m1.metric("구매필요 품목 수", f"{len(purchase_df):,}개")
            m2.metric("구매필요 총수량", f"{safe_int(total_qty):,}개")
            m3.metric("전체 구매금액", format_won(total_amount))

            st.markdown("### 구매계정별 합계")

            summary_df = (
                purchase_df
                .groupby("구매계정", as_index=False)
                .agg(
                    구매필요품목수=("품목명", "count"),
                    구매필요총수량=("구매필요수량", "sum"),
                    구매금액=("구매금액", "sum")
                )
            )

            summary_display_df = summary_df.copy()
            summary_display_df["구매필요총수량"] = summary_display_df["구매필요총수량"].apply(lambda x: f"{safe_int(x):,}개")
            summary_display_df["구매금액"] = summary_display_df["구매금액"].apply(format_won)

            st.dataframe(summary_display_df, use_container_width=True, hide_index=True)

            st.markdown("### 구매필요 상세목록")

            display_purchase_df = purchase_df.copy()
            display_purchase_df["단가"] = display_purchase_df["단가"].apply(format_won)
            display_purchase_df["구매금액"] = display_purchase_df["구매금액"].apply(format_won)

            st.dataframe(display_purchase_df, use_container_width=True, hide_index=True)

            excel_data = to_excel_bytes({
                "구매필요목록": purchase_df,
                "구매계정별합계": summary_df
            })

            st.download_button(
                label="엑셀 다운로드",
                data=excel_data,
                file_name=f"구매필요목록_{APP_VERSION}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )