# Main.py
# 안전창고 재고관리 시스템 V5.3
# Python + Streamlit + Supabase

import streamlit as st
import pandas as pd
from datetime import datetime
from supabase import create_client, Client

# =========================
# 기본 설정
# =========================
st.set_page_config(
    page_title="안전창고 재고관리 시스템 V5.3",
    page_icon="📦",
    layout="wide"
)

PURCHASE_ACCOUNTS = ["일반수선비", "안전보호구"]

# =========================
# Supabase 연결
# =========================
@st.cache_resource
def init_supabase() -> Client:
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_KEY"]
    return create_client(url, key)

supabase = init_supabase()

# =========================
# 공통 함수
# =========================
def safe_int(value, default=0):
    try:
        if value is None or value == "":
            return default
        return int(float(value))
    except:
        return default


def safe_float(value, default=0):
    try:
        if value is None or value == "":
            return default
        return float(value)
    except:
        return default


def format_won(value):
    return f"{safe_int(value):,}원"


def now_text():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


# =========================
# 데이터 조회
# =========================
def load_items():
    try:
        result = supabase.table("items").select("*").order("id").execute()
        df = pd.DataFrame(result.data)

        if df.empty:
            return pd.DataFrame(columns=[
                "id", "item_name", "spec", "unit", "location",
                "stock_qty", "min_stock", "optimal_stock",
                "unit_price", "purchase_account", "created_at", "updated_at"
            ])

        for col in ["stock_qty", "min_stock", "optimal_stock", "unit_price"]:
            if col not in df.columns:
                df[col] = 0

        if "purchase_account" not in df.columns:
            df["purchase_account"] = "일반수선비"

        df["stock_qty"] = df["stock_qty"].apply(safe_int)
        df["min_stock"] = df["min_stock"].apply(safe_int)
        df["optimal_stock"] = df["optimal_stock"].apply(safe_int)
        df["unit_price"] = df["unit_price"].apply(safe_int)

        return df

    except Exception as e:
        st.error(f"품목 데이터 조회 오류: {e}")
        return pd.DataFrame()


def load_history():
    try:
        result = supabase.table("stock_history").select("*").order("id", desc=True).execute()
        return pd.DataFrame(result.data)
    except:
        return pd.DataFrame()


# =========================
# 데이터 처리
# =========================
def add_item(item_name, spec, unit, location, stock_qty, min_stock, optimal_stock, unit_price, purchase_account):
    data = {
        "item_name": item_name,
        "spec": spec,
        "unit": unit,
        "location": location,
        "stock_qty": safe_int(stock_qty),
        "min_stock": safe_int(min_stock),
        "optimal_stock": safe_int(optimal_stock),
        "unit_price": safe_int(unit_price),
        "purchase_account": purchase_account,
        "created_at": now_text(),
        "updated_at": now_text()
    }
    supabase.table("items").insert(data).execute()


def update_item(item_id, item_name, spec, unit, location, stock_qty, min_stock, optimal_stock, unit_price, purchase_account):
    data = {
        "item_name": item_name,
        "spec": spec,
        "unit": unit,
        "location": location,
        "stock_qty": safe_int(stock_qty),
        "min_stock": safe_int(min_stock),
        "optimal_stock": safe_int(optimal_stock),
        "unit_price": safe_int(unit_price),
        "purchase_account": purchase_account,
        "updated_at": now_text()
    }
    supabase.table("items").update(data).eq("id", item_id).execute()


def delete_item(item_id):
    supabase.table("items").delete().eq("id", item_id).execute()


def update_stock(item_id, current_qty, change_qty, change_type, memo):
    current_qty = safe_int(current_qty)
    change_qty = safe_int(change_qty)

    if change_type == "입고":
        new_qty = current_qty + change_qty
    else:
        new_qty = current_qty - change_qty

    if new_qty < 0:
        st.warning("출고 수량이 현재 재고보다 많습니다.")
        return False

    supabase.table("items").update({
        "stock_qty": new_qty,
        "updated_at": now_text()
    }).eq("id", item_id).execute()

    history_data = {
        "item_id": item_id,
        "change_type": change_type,
        "change_qty": change_qty,
        "before_qty": current_qty,
        "after_qty": new_qty,
        "memo": memo,
        "created_at": now_text()
    }

    supabase.table("stock_history").insert(history_data).execute()
    return True


# =========================
# 화면 제목
# =========================
st.title("📦 안전창고 재고관리 시스템 V5.3")

menu = st.sidebar.radio(
    "메뉴 선택",
    [
        "재고현황",
        "입고/출고",
        "품목관리",
        "구매필요목록",
        "입출고 이력"
    ]
)

items_df = load_items()

# =========================
# 재고현황
# =========================
if menu == "재고현황":
    st.subheader("📋 재고현황")

    if items_df.empty:
        st.info("등록된 품목이 없습니다.")
    else:
        keyword = st.text_input("품목명 검색")

        view_df = items_df.copy()

        if keyword:
            view_df = view_df[
                view_df["item_name"].astype(str).str.contains(keyword, case=False, na=False)
            ]

        view_df["총금액"] = view_df["stock_qty"] * view_df["unit_price"]
        view_df["재고상태"] = view_df.apply(
            lambda row: "구매필요" if row["stock_qty"] <= row["min_stock"] else "정상",
            axis=1
        )

        show_cols = [
            "id", "item_name", "spec", "unit", "location",
            "stock_qty", "min_stock", "optimal_stock",
            "unit_price", "purchase_account", "총금액", "재고상태"
        ]

        st.dataframe(
            view_df[show_cols],
            use_container_width=True,
            hide_index=True
        )

        total_stock_amount = view_df["총금액"].sum()

        col1, col2, col3 = st.columns(3)
        col1.metric("전체 품목 수", f"{len(view_df):,}개")
        col2.metric("구매필요 품목 수", f"{len(view_df[view_df['재고상태'] == '구매필요']):,}개")
        col3.metric("현재 재고 총금액", format_won(total_stock_amount))


# =========================
# 입고/출고
# =========================
elif menu == "입고/출고":
    st.subheader("🔄 입고 / 출고 처리")

    if items_df.empty:
        st.info("등록된 품목이 없습니다.")
    else:
        item_options = {
            f"{row['item_name']} / 현재재고: {row['stock_qty']} {row.get('unit', '')}": row
            for _, row in items_df.iterrows()
        }

        selected_label = st.selectbox("품목 선택", list(item_options.keys()))
        selected_item = item_options[selected_label]

        col1, col2 = st.columns(2)

        with col1:
            change_type = st.radio("구분", ["입고", "출고"], horizontal=True)

        with col2:
            change_qty = st.number_input("수량", min_value=1, step=1)

        memo = st.text_input("비고")

        if st.button("처리하기", type="primary"):
            success = update_stock(
                selected_item["id"],
                selected_item["stock_qty"],
                change_qty,
                change_type,
                memo
            )

            if success:
                st.success(f"{change_type} 처리가 완료되었습니다.")
                st.rerun()


# =========================
# 품목관리
# =========================
elif menu == "품목관리":
    st.subheader("🛠 품목관리")

    tab1, tab2 = st.tabs(["품목 등록", "품목 수정/삭제"])

    with tab1:
        st.markdown("### 신규 품목 등록")

        with st.form("add_item_form"):
            col1, col2 = st.columns(2)

            with col1:
                item_name = st.text_input("품목명")
                spec = st.text_input("규격")
                unit = st.text_input("단위", value="EA")
                location = st.text_input("보관위치")

            with col2:
                stock_qty = st.number_input("현재재고", min_value=0, step=1)
                min_stock = st.number_input("최소재고", min_value=0, step=1)
                optimal_stock = st.number_input("적정재고", min_value=0, step=1)
                unit_price = st.number_input("단가", min_value=0, step=100)
                purchase_account = st.selectbox("구매계정", PURCHASE_ACCOUNTS)

            submitted = st.form_submit_button("등록")

            if submitted:
                if not item_name:
                    st.warning("품목명을 입력해주세요.")
                else:
                    add_item(
                        item_name,
                        spec,
                        unit,
                        location,
                        stock_qty,
                        min_stock,
                        optimal_stock,
                        unit_price,
                        purchase_account
                    )
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
                    edit_item_name = st.text_input("품목명", value=str(selected_item.get("item_name", "")))
                    edit_spec = st.text_input("규격", value=str(selected_item.get("spec", "")))
                    edit_unit = st.text_input("단위", value=str(selected_item.get("unit", "")))
                    edit_location = st.text_input("보관위치", value=str(selected_item.get("location", "")))

                with col2:
                    edit_stock_qty = st.number_input(
                        "현재재고",
                        min_value=0,
                        step=1,
                        value=safe_int(selected_item.get("stock_qty", 0))
                    )
                    edit_min_stock = st.number_input(
                        "최소재고",
                        min_value=0,
                        step=1,
                        value=safe_int(selected_item.get("min_stock", 0))
                    )
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

                    current_account = selected_item.get("purchase_account", "일반수선비")
                    if current_account not in PURCHASE_ACCOUNTS:
                        current_account = "일반수선비"

                    edit_purchase_account = st.selectbox(
                        "구매계정",
                        PURCHASE_ACCOUNTS,
                        index=PURCHASE_ACCOUNTS.index(current_account)
                    )

                col_save, col_delete = st.columns(2)

                save_clicked = col_save.form_submit_button("수정 저장")
                delete_clicked = col_delete.form_submit_button("삭제")

                if save_clicked:
                    update_item(
                        selected_item["id"],
                        edit_item_name,
                        edit_spec,
                        edit_unit,
                        edit_location,
                        edit_stock_qty,
                        edit_min_stock,
                        edit_optimal_stock,
                        edit_unit_price,
                        edit_purchase_account
                    )
                    st.success("품목 정보가 수정되었습니다.")
                    st.rerun()

                if delete_clicked:
                    delete_item(selected_item["id"])
                    st.success("품목이 삭제되었습니다.")
                    st.rerun()


# =========================
# 구매필요목록
# =========================
elif menu == "구매필요목록":
    st.subheader("🛒 구매필요목록")

    if items_df.empty:
        st.info("등록된 품목이 없습니다.")
    else:
        purchase_df = items_df.copy()

        purchase_df["구매필요수량"] = purchase_df["optimal_stock"] - purchase_df["stock_qty"]
        purchase_df["구매필요수량"] = purchase_df["구매필요수량"].apply(lambda x: x if x > 0 else 0)
        purchase_df["구매금액"] = purchase_df["구매필요수량"] * purchase_df["unit_price"]

        purchase_df = purchase_df[
            (purchase_df["stock_qty"] <= purchase_df["min_stock"]) |
            (purchase_df["구매필요수량"] > 0)
        ]

        if purchase_df.empty:
            st.success("현재 구매가 필요한 품목이 없습니다.")
        else:
            total_purchase_amount = purchase_df["구매금액"].sum()

            st.metric("전체 구매금액", format_won(total_purchase_amount))

            account_summary = purchase_df.groupby("purchase_account", as_index=False)["구매금액"].sum()
            account_summary["구매금액"] = account_summary["구매금액"].apply(format_won)

            st.markdown("### 구매계정별 합계")
            st.dataframe(account_summary, use_container_width=True, hide_index=True)

            st.markdown("### 구매계정별 구매필요목록")

            for account in PURCHASE_ACCOUNTS:
                account_df = purchase_df[purchase_df["purchase_account"] == account].copy()

                if account_df.empty:
                    continue

                account_total = account_df["구매금액"].sum()

                st.markdown(f"#### {account} / 합계: {format_won(account_total)}")

                show_df = account_df[[
                    "item_name",
                    "spec",
                    "unit",
                    "location",
                    "stock_qty",
                    "min_stock",
                    "optimal_stock",
                    "구매필요수량",
                    "unit_price",
                    "구매금액",
                    "purchase_account"
                ]].copy()

                st.dataframe(show_df, use_container_width=True, hide_index=True)

            excel_df = purchase_df[[
                "item_name",
                "spec",
                "unit",
                "location",
                "stock_qty",
                "min_stock",
                "optimal_stock",
                "구매필요수량",
                "unit_price",
                "구매금액",
                "purchase_account"
            ]].copy()

            csv = excel_df.to_csv(index=False).encode("utf-8-sig")

            st.download_button(
                label="구매필요목록 CSV 다운로드",
                data=csv,
                file_name="purchase_required_list_v5_3.csv",
                mime="text/csv"
            )


# =========================
# 입출고 이력
# =========================
elif menu == "입출고 이력":
    st.subheader("📑 입출고 이력")

    history_df = load_history()

    if history_df.empty:
        st.info("입출고 이력이 없습니다.")
    else:
        if not items_df.empty and "item_id" in history_df.columns:
            item_name_map = dict(zip(items_df["id"], items_df["item_name"]))
            history_df["품목명"] = history_df["item_id"].map(item_name_map)

        show_cols = []

        for col in [
            "created_at",
            "품목명",
            "change_type",
            "change_qty",
            "before_qty",
            "after_qty",
            "memo"
        ]:
            if col in history_df.columns:
                show_cols.append(col)

        st.dataframe(
            history_df[show_cols],
            use_container_width=True,
            hide_index=True
        )