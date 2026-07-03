# Main.py
# 안전창고 재고관리 시스템 V5.3 Final
# Streamlit + Supabase

import streamlit as st
import pandas as pd
from datetime import datetime
from supabase import create_client, Client

st.set_page_config(
    page_title="안전창고 재고관리 시스템 V5.3",
    page_icon="📦",
    layout="wide"
)

APP_VERSION = "V5.3 Final"
PURCHASE_ACCOUNTS = ["일반수선비", "안전보호구"]

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
    except:
        return default

def format_won(value):
    return f"{safe_int(value):,}원"

def normalize_account(value):
    if value in PURCHASE_ACCOUNTS:
        return value
    return "일반수선비"

def safe_dataframe_columns(df, columns):
    for col in columns:
        if col not in df.columns:
            df[col] = ""
    return df

def clean_payload(data):
    return {k: v for k, v in data.items() if v is not None}

# =========================================================
# 데이터 조회
# =========================================================
def load_items():
    try:
        result = supabase.table("items").select("*").order("id").execute()
        raw_data = result.data or []
        df = pd.DataFrame(raw_data)

        required_cols = {
            "id": 0,
            "item_name": "",
            "spec": "",
            "unit": "EA",
            "location": "",
            "stock_qty": 0,
            "min_stock": 0,
            "optimal_stock": 0,
            "unit_price": 0,
            "purchase_account": "일반수선비",
            "created_at": "",
            "updated_at": ""
        }

        if df.empty:
            return pd.DataFrame(columns=list(required_cols.keys()))

        for col, default_value in required_cols.items():
            if col not in df.columns:
                df[col] = default_value

        for col in ["stock_qty", "min_stock", "optimal_stock", "unit_price"]:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0).astype(int)

        df["purchase_account"] = df["purchase_account"].apply(normalize_account)

        return df

    except Exception as e:
        st.error(f"품목 데이터 조회 오류: {e}")
        return pd.DataFrame(columns=[
            "id", "item_name", "spec", "unit", "location",
            "stock_qty", "min_stock", "optimal_stock",
            "unit_price", "purchase_account", "created_at", "updated_at"
        ])

def load_history():
    try:
        result = supabase.table("stock_history").select("*").order("id", desc=True).execute()
        df = pd.DataFrame(result.data or [])

        required_cols = [
            "id", "item_id", "change_type", "change_qty",
            "before_qty", "after_qty", "memo", "created_at"
        ]

        for col in required_cols:
            if col not in df.columns:
                df[col] = ""

        return df

    except Exception as e:
        st.warning(f"입출고 이력 조회 오류: {e}")
        return pd.DataFrame()

# =========================================================
# 데이터 저장
# =========================================================
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
        "purchase_account": normalize_account(purchase_account),
        "created_at": now_text(),
        "updated_at": now_text()
    }

    try:
        supabase.table("items").insert(clean_payload(data)).execute()
        return True
    except Exception as e:
        st.error(f"품목 등록 오류: {e}")
        return False

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
        "purchase_account": normalize_account(purchase_account),
        "updated_at": now_text()
    }

    try:
        supabase.table("items").update(clean_payload(data)).eq("id", item_id).execute()
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

    try:
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

    except Exception as e:
        st.error(f"입출고 처리 오류: {e}")
        return False

# =========================================================
# 화면 시작
# =========================================================
st.title(f"📦 안전창고 재고관리 시스템 {APP_VERSION}")

menu = st.sidebar.radio(
    "메뉴 선택",
    ["재고현황", "입고/출고", "품목관리", "구매필요목록", "입출고 이력"]
)

items_df = load_items()

# =========================================================
# 재고현황
# =========================================================
if menu == "재고현황":
    st.subheader("📋 재고현황")

    keyword = st.text_input("품목명 검색")

    df = items_df.copy()

    if not df.empty and keyword:
        df = df[df["item_name"].astype(str).str.contains(keyword, case=False, na=False)]

    if df.empty:
        st.info("등록된 품목이 없습니다.")
    else:
        df["총금액"] = df["stock_qty"] * df["unit_price"]
        df["재고상태"] = df.apply(
            lambda row: "구매필요" if safe_int(row["stock_qty"]) <= safe_int(row["min_stock"]) else "정상",
            axis=1
        )

        show_cols = [
            "id", "item_name", "spec", "unit", "location",
            "stock_qty", "min_stock", "optimal_stock",
            "unit_price", "purchase_account", "총금액", "재고상태"
        ]

        df = safe_dataframe_columns(df, show_cols)

        st.dataframe(df[show_cols], use_container_width=True, hide_index=True)

        col1, col2, col3 = st.columns(3)
        col1.metric("전체 품목 수", f"{len(df):,}개")
        col2.metric("구매필요 품목 수", f"{len(df[df['재고상태'] == '구매필요']):,}개")
        col3.metric("현재 재고 총금액", format_won(df["총금액"].sum()))

# =========================================================
# 입고/출고
# =========================================================
elif menu == "입고/출고":
    st.subheader("🔄 입고 / 출고 처리")

    if items_df.empty:
        st.info("등록된 품목이 없습니다.")
    else:
        item_options = {
            f"{row['id']} - {row['item_name']} / 현재재고: {row['stock_qty']} {row['unit']}": row
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
            if update_stock(
                selected_item["id"],
                selected_item["stock_qty"],
                change_qty,
                change_type,
                memo
            ):
                st.success(f"{change_type} 처리가 완료되었습니다.")
                st.rerun()

# =========================================================
# 품목관리
# =========================================================
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
                if not item_name.strip():
                    st.warning("품목명을 입력해주세요.")
                else:
                    if add_item(
                        item_name,
                        spec,
                        unit,
                        location,
                        stock_qty,
                        min_stock,
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
                    edit_item_name = st.text_input("품목명", value=str(selected_item.get("item_name", "")))
                    edit_spec = st.text_input("규격", value=str(selected_item.get("spec", "")))
                    edit_unit = st.text_input("단위", value=str(selected_item.get("unit", "EA")))
                    edit_location = st.text_input("보관위치", value=str(selected_item.get("location", "")))

                with col2:
                    edit_stock_qty = st.number_input("현재재고", min_value=0, step=1, value=safe_int(selected_item.get("stock_qty", 0)))
                    edit_min_stock = st.number_input("최소재고", min_value=0, step=1, value=safe_int(selected_item.get("min_stock", 0)))
                    edit_optimal_stock = st.number_input("적정재고", min_value=0, step=1, value=safe_int(selected_item.get("optimal_stock", 0)))
                    edit_unit_price = st.number_input("단가", min_value=0, step=100, value=safe_int(selected_item.get("unit_price", 0)))

                    current_account = normalize_account(selected_item.get("purchase_account", "일반수선비"))

                    edit_purchase_account = st.selectbox(
                        "구매계정",
                        PURCHASE_ACCOUNTS,
                        index=PURCHASE_ACCOUNTS.index(current_account)
                    )

                col_save, col_delete = st.columns(2)

                save_clicked = col_save.form_submit_button("수정 저장")
                delete_clicked = col_delete.form_submit_button("삭제")

                if save_clicked:
                    if update_item(
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

            st.markdown("### 구매계정별 합계")

            summary_df = purchase_df.groupby("purchase_account", as_index=False)["구매금액"].sum()
            summary_df["구매금액"] = summary_df["구매금액"].apply(format_won)

            st.dataframe(summary_df, use_container_width=True, hide_index=True)

            st.markdown("### 구매계정별 구매필요목록")

            for account in PURCHASE_ACCOUNTS:
                account_df = purchase_df[purchase_df["purchase_account"] == account].copy()

                if account_df.empty:
                    continue

                account_total = account_df["구매금액"].sum()

                st.markdown(f"#### {account} / 합계: {format_won(account_total)}")

                show_cols = [
                    "item_name", "spec", "unit", "location",
                    "stock_qty", "min_stock", "optimal_stock",
                    "구매필요수량", "unit_price", "구매금액", "purchase_account"
                ]

                account_df = safe_dataframe_columns(account_df, show_cols)

                st.dataframe(account_df[show_cols], use_container_width=True, hide_index=True)

            csv_df = purchase_df.copy()
            csv = csv_df.to_csv(index=False).encode("utf-8-sig")

            st.download_button(
                label="구매필요목록 CSV 다운로드",
                data=csv,
                file_name="purchase_required_list_v5_3.csv",
                mime="text/csv"
            )

# =========================================================
# 입출고 이력
# =========================================================
elif menu == "입출고 이력":
    st.subheader("📑 입출고 이력")

    history_df = load_history()

    if history_df.empty:
        st.info("입출고 이력이 없습니다.")
    else:
        if not items_df.empty and "item_id" in history_df.columns:
            item_map = dict(zip(items_df["id"], items_df["item_name"]))
            history_df["품목명"] = history_df["item_id"].map(item_map)

        show_cols = [
            "created_at", "품목명", "change_type",
            "change_qty", "before_qty", "after_qty", "memo"
        ]

        history_df = safe_dataframe_columns(history_df, show_cols)

        st.dataframe(history_df[show_cols], use_container_width=True, hide_index=True)