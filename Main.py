# Main.py
# 안전창고 재고관리 시스템 V5.3.1
# 변경사항:
# 1. 규격, 최소재고 제거
# 2. 창고 컬럼 추가
# 3. 사용자 컬럼 추가/수정/삭제 기능 추가
# 4. 표 표시 컬럼명 한글화

import streamlit as st
import pandas as pd
from datetime import datetime
from supabase import create_client, Client
import json

st.set_page_config(
    page_title="안전창고 재고관리 시스템 V5.3.1",
    page_icon="📦",
    layout="wide"
)

APP_VERSION = "V5.3.1"
PURCHASE_ACCOUNTS = ["일반수선비", "안전보호구"]
WAREHOUSES = ["1창고", "2창고"]

DEFAULT_EXTRA_COLUMNS = []

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

def normalize_warehouse(value):
    if value in WAREHOUSES:
        return value
    return "1창고"

def safe_json(value):
    if value is None or value == "":
        return {}
    if isinstance(value, dict):
        return value
    try:
        return json.loads(value)
    except:
        return {}

def get_extra_columns():
    try:
        result = (
            supabase.table("app_settings")
            .select("*")
            .eq("setting_key", "item_extra_columns")
            .execute()
        )

        if result.data:
            value = result.data[0].get("setting_value", [])
            if isinstance(value, list):
                return value
            if isinstance(value, str):
                return json.loads(value)

        return DEFAULT_EXTRA_COLUMNS

    except:
        return DEFAULT_EXTRA_COLUMNS

def save_extra_columns(columns):
    columns = list(dict.fromkeys([c.strip() for c in columns if c.strip()]))

    try:
        result = (
            supabase.table("app_settings")
            .select("*")
            .eq("setting_key", "item_extra_columns")
            .execute()
        )

        data = {
            "setting_key": "item_extra_columns",
            "setting_value": columns,
            "updated_at": now_text()
        }

        if result.data:
            supabase.table("app_settings").update(data).eq("setting_key", "item_extra_columns").execute()
        else:
            supabase.table("app_settings").insert(data).execute()

        return True

    except Exception as e:
        st.error(f"컬럼 설정 저장 오류: {e}")
        return False

def rename_extra_column(old_name, new_name):
    new_name = new_name.strip()

    if not old_name or not new_name:
        return False

    columns = get_extra_columns()

    if old_name not in columns:
        return False

    if new_name in columns:
        st.warning("이미 존재하는 컬럼명입니다.")
        return False

    columns = [new_name if c == old_name else c for c in columns]

    items_df = load_items()

    for _, row in items_df.iterrows():
        extra = safe_json(row.get("extra_fields", {}))
        if old_name in extra:
            extra[new_name] = extra.pop(old_name)
            supabase.table("items").update({
                "extra_fields": extra,
                "updated_at": now_text()
            }).eq("id", row["id"]).execute()

    return save_extra_columns(columns)

def delete_extra_column(column_name):
    columns = get_extra_columns()
    columns = [c for c in columns if c != column_name]

    items_df = load_items()

    for _, row in items_df.iterrows():
        extra = safe_json(row.get("extra_fields", {}))
        if column_name in extra:
            extra.pop(column_name, None)
            supabase.table("items").update({
                "extra_fields": extra,
                "updated_at": now_text()
            }).eq("id", row["id"]).execute()

    return save_extra_columns(columns)

def make_display_df(df, extra_columns=None):
    if extra_columns is None:
        extra_columns = get_extra_columns()

    result = df.copy()

    result["총금액"] = result["stock_qty"] * result["unit_price"]
    result["재고상태"] = result.apply(
        lambda row: "구매필요" if safe_int(row["stock_qty"]) < safe_int(row["optimal_stock"]) else "정상",
        axis=1
    )

    for col in extra_columns:
        result[col] = result["extra_fields"].apply(lambda x: safe_json(x).get(col, ""))

    display_cols = [
        "id",
        "warehouse",
        "item_name",
        "unit",
        "location",
        "stock_qty",
        "optimal_stock",
        "unit_price",
        "purchase_account",
        "총금액",
        "재고상태"
    ] + extra_columns

    result = result[display_cols]

    result = result.rename(columns={
        "id": "ID",
        "warehouse": "창고",
        "item_name": "품목명",
        "unit": "단위",
        "location": "보관위치",
        "stock_qty": "현재재고",
        "optimal_stock": "적정재고",
        "unit_price": "단가",
        "purchase_account": "구매계정"
    })

    return result

# =========================================================
# 데이터 조회
# =========================================================
def load_items():
    try:
        result = supabase.table("items").select("*").order("id").execute()
        df = pd.DataFrame(result.data or [])

        required_cols = {
            "id": 0,
            "warehouse": "1창고",
            "item_name": "",
            "unit": "EA",
            "location": "",
            "stock_qty": 0,
            "optimal_stock": 0,
            "unit_price": 0,
            "purchase_account": "일반수선비",
            "extra_fields": {},
            "created_at": "",
            "updated_at": ""
        }

        if df.empty:
            return pd.DataFrame(columns=list(required_cols.keys()))

        for col, default_value in required_cols.items():
            if col not in df.columns:
                df[col] = default_value

        for col in ["stock_qty", "optimal_stock", "unit_price"]:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0).astype(int)

        df["warehouse"] = df["warehouse"].apply(normalize_warehouse)
        df["purchase_account"] = df["purchase_account"].apply(normalize_account)
        df["extra_fields"] = df["extra_fields"].apply(safe_json)

        return df

    except Exception as e:
        st.error(f"품목 데이터 조회 오류: {e}")
        return pd.DataFrame(columns=[
            "id", "warehouse", "item_name", "unit", "location",
            "stock_qty", "optimal_stock", "unit_price",
            "purchase_account", "extra_fields", "created_at", "updated_at"
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

    except:
        return pd.DataFrame()

# =========================================================
# 데이터 저장
# =========================================================
def add_item(warehouse, item_name, unit, location, stock_qty, optimal_stock, unit_price, purchase_account, extra_fields):
    data = {
        "warehouse": normalize_warehouse(warehouse),
        "item_name": item_name,
        "unit": unit,
        "location": location,
        "stock_qty": safe_int(stock_qty),
        "optimal_stock": safe_int(optimal_stock),
        "unit_price": safe_int(unit_price),
        "purchase_account": normalize_account(purchase_account),
        "extra_fields": extra_fields,
        "created_at": now_text(),
        "updated_at": now_text()
    }

    try:
        supabase.table("items").insert(data).execute()
        return True
    except Exception as e:
        st.error(f"품목 등록 오류: {e}")
        return False

def update_item(item_id, warehouse, item_name, unit, location, stock_qty, optimal_stock, unit_price, purchase_account, extra_fields):
    data = {
        "warehouse": normalize_warehouse(warehouse),
        "item_name": item_name,
        "unit": unit,
        "location": location,
        "stock_qty": safe_int(stock_qty),
        "optimal_stock": safe_int(optimal_stock),
        "unit_price": safe_int(unit_price),
        "purchase_account": normalize_account(purchase_account),
        "extra_fields": extra_fields,
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
    [
        "재고현황",
        "입고/출고",
        "품목관리",
        "구매필요목록",
        "컬럼관리",
        "입출고 이력"
    ]
)

items_df = load_items()
extra_columns = get_extra_columns()

# =========================================================
# 재고현황
# =========================================================
if menu == "재고현황":
    st.subheader("📋 재고현황")

    col1, col2, col3 = st.columns(3)

    with col1:
        keyword = st.text_input("품목명 검색")

    with col2:
        warehouse_filter = st.selectbox("창고 선택", ["전체"] + WAREHOUSES)

    with col3:
        account_filter = st.selectbox("구매계정 선택", ["전체"] + PURCHASE_ACCOUNTS)

    df = items_df.copy()

    if not df.empty:
        if keyword:
            df = df[df["item_name"].astype(str).str.contains(keyword, case=False, na=False)]

        if warehouse_filter != "전체":
            df = df[df["warehouse"] == warehouse_filter]

        if account_filter != "전체":
            df = df[df["purchase_account"] == account_filter]

    if df.empty:
        st.info("등록된 품목이 없습니다.")
    else:
        display_df = make_display_df(df, extra_columns)

        st.dataframe(display_df, use_container_width=True, hide_index=True)

        total_amount = (df["stock_qty"] * df["unit_price"]).sum()
        need_count = len(df[df["stock_qty"] < df["optimal_stock"]])

        m1, m2, m3 = st.columns(3)
        m1.metric("전체 품목 수", f"{len(df):,}개")
        m2.metric("구매필요 품목 수", f"{need_count:,}개")
        m3.metric("현재 재고 총금액", format_won(total_amount))

# =========================================================
# 입고/출고
# =========================================================
elif menu == "입고/출고":
    st.subheader("🔄 입고 / 출고 처리")

    if items_df.empty:
        st.info("등록된 품목이 없습니다.")
    else:
        item_options = {
            f"{row['warehouse']} / {row['item_name']} / 현재재고: {row['stock_qty']} {row['unit']}": row
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
                warehouse = st.selectbox("창고", WAREHOUSES)
                item_name = st.text_input("품목명")
                unit = st.text_input("단위", value="EA")
                location = st.text_input("보관위치")

            with col2:
                stock_qty = st.number_input("현재재고", min_value=0, step=1)
                optimal_stock = st.number_input("적정재고", min_value=0, step=1)
                unit_price = st.number_input("단가", min_value=0, step=100)
                purchase_account = st.selectbox("구매계정", PURCHASE_ACCOUNTS)

            st.markdown("### 추가 컬럼 입력")

            extra_fields = {}

            if extra_columns:
                for col in extra_columns:
                    extra_fields[col] = st.text_input(col, key=f"add_extra_{col}")
            else:
                st.info("추가 컬럼이 없습니다. 컬럼관리 메뉴에서 추가할 수 있습니다.")

            submitted = st.form_submit_button("등록")

            if submitted:
                if not item_name.strip():
                    st.warning("품목명을 입력해주세요.")
                else:
                    if add_item(
                        warehouse,
                        item_name,
                        unit,
                        location,
                        stock_qty,
                        optimal_stock,
                        unit_price,
                        purchase_account,
                        extra_fields
                    ):
                        st.success("품목이 등록되었습니다.")
                        st.rerun()

    with tab2:
        st.markdown("### 기존 품목 수정 / 삭제")

        if items_df.empty:
            st.info("등록된 품목이 없습니다.")
        else:
            item_options = {
                f"{row['id']} - {row['warehouse']} - {row['item_name']}": row
                for _, row in items_df.iterrows()
            }

            selected_label = st.selectbox("수정할 품목 선택", list(item_options.keys()))
            selected_item = item_options[selected_label]

            with st.form("edit_item_form"):
                col1, col2 = st.columns(2)

                with col1:
                    current_warehouse = normalize_warehouse(selected_item.get("warehouse", "1창고"))

                    edit_warehouse = st.selectbox(
                        "창고",
                        WAREHOUSES,
                        index=WAREHOUSES.index(current_warehouse)
                    )

                    edit_item_name = st.text_input("품목명", value=str(selected_item.get("item_name", "")))
                    edit_unit = st.text_input("단위", value=str(selected_item.get("unit", "EA")))
                    edit_location = st.text_input("보관위치", value=str(selected_item.get("location", "")))

                with col2:
                    edit_stock_qty = st.number_input(
                        "현재재고",
                        min_value=0,
                        step=1,
                        value=safe_int(selected_item.get("stock_qty", 0))
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

                    current_account = normalize_account(selected_item.get("purchase_account", "일반수선비"))

                    edit_purchase_account = st.selectbox(
                        "구매계정",
                        PURCHASE_ACCOUNTS,
                        index=PURCHASE_ACCOUNTS.index(current_account)
                    )

                st.markdown("### 추가 컬럼 수정")

                selected_extra = safe_json(selected_item.get("extra_fields", {}))
                edit_extra_fields = {}

                if extra_columns:
                    for col in extra_columns:
                        edit_extra_fields[col] = st.text_input(
                            col,
                            value=str(selected_extra.get(col, "")),
                            key=f"edit_extra_{selected_item['id']}_{col}"
                        )
                else:
                    st.info("추가 컬럼이 없습니다.")

                col_save, col_delete = st.columns(2)

                save_clicked = col_save.form_submit_button("수정 저장")
                delete_clicked = col_delete.form_submit_button("삭제")

                if save_clicked:
                    if update_item(
                        selected_item["id"],
                        edit_warehouse,
                        edit_item_name,
                        edit_unit,
                        edit_location,
                        edit_stock_qty,
                        edit_optimal_stock,
                        edit_unit_price,
                        edit_purchase_account,
                        edit_extra_fields
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

        purchase_df = purchase_df[purchase_df["구매필요수량"] > 0]

        if purchase_df.empty:
            st.success("현재 구매가 필요한 품목이 없습니다.")
        else:
            total_purchase_amount = purchase_df["구매금액"].sum()
            st.metric("전체 구매금액", format_won(total_purchase_amount))

            st.markdown("### 구매계정별 합계")

            summary_df = purchase_df.groupby("purchase_account", as_index=False)["구매금액"].sum()
            summary_df = summary_df.rename(columns={
                "purchase_account": "구매계정",
                "구매금액": "구매금액"
            })
            summary_df["구매금액"] = summary_df["구매금액"].apply(format_won)

            st.dataframe(summary_df, use_container_width=True, hide_index=True)

            st.markdown("### 구매계정별 구매필요목록")

            for account in PURCHASE_ACCOUNTS:
                account_df = purchase_df[purchase_df["purchase_account"] == account].copy()

                if account_df.empty:
                    continue

                account_total = account_df["구매금액"].sum()

                st.markdown(f"#### {account} / 합계: {format_won(account_total)}")

                for col in extra_columns:
                    account_df[col] = account_df["extra_fields"].apply(lambda x: safe_json(x).get(col, ""))

                show_cols = [
                    "warehouse",
                    "item_name",
                    "unit",
                    "location",
                    "stock_qty",
                    "optimal_stock",
                    "구매필요수량",
                    "unit_price",
                    "구매금액",
                    "purchase_account"
                ] + extra_columns

                show_df = account_df[show_cols].rename(columns={
                    "warehouse": "창고",
                    "item_name": "품목명",
                    "unit": "단위",
                    "location": "보관위치",
                    "stock_qty": "현재재고",
                    "optimal_stock": "적정재고",
                    "unit_price": "단가",
                    "purchase_account": "구매계정"
                })

                st.dataframe(show_df, use_container_width=True, hide_index=True)

            csv_df = purchase_df.copy()

            for col in extra_columns:
                csv_df[col] = csv_df["extra_fields"].apply(lambda x: safe_json(x).get(col, ""))

            csv_cols = [
                "warehouse",
                "item_name",
                "unit",
                "location",
                "stock_qty",
                "optimal_stock",
                "구매필요수량",
                "unit_price",
                "구매금액",
                "purchase_account"
            ] + extra_columns

            csv_df = csv_df[csv_cols].rename(columns={
                "warehouse": "창고",
                "item_name": "품목명",
                "unit": "단위",
                "location": "보관위치",
                "stock_qty": "현재재고",
                "optimal_stock": "적정재고",
                "unit_price": "단가",
                "purchase_account": "구매계정"
            })

            csv = csv_df.to_csv(index=False).encode("utf-8-sig")

            st.download_button(
                label="구매필요목록 CSV 다운로드",
                data=csv,
                file_name="purchase_required_list_v5_3_1.csv",
                mime="text/csv"
            )

# =========================================================
# 컬럼관리
# =========================================================
elif menu == "컬럼관리":
    st.subheader("⚙️ 컬럼관리")

    st.info("기본 컬럼은 삭제할 수 없습니다. 이 메뉴에서는 사용자 추가 컬럼만 추가, 수정, 삭제할 수 있습니다.")

    st.markdown("### 현재 추가 컬럼")

    if extra_columns:
        st.dataframe(pd.DataFrame({"추가 컬럼명": extra_columns}), use_container_width=True, hide_index=True)
    else:
        st.write("현재 추가 컬럼이 없습니다.")

    st.divider()

    st.markdown("### 컬럼 추가")

    new_col = st.text_input("새 컬럼명")

    if st.button("컬럼 추가"):
        if not new_col.strip():
            st.warning("컬럼명을 입력해주세요.")
        elif new_col.strip() in extra_columns:
            st.warning("이미 존재하는 컬럼입니다.")
        else:
            extra_columns.append(new_col.strip())
            if save_extra_columns(extra_columns):
                st.success("컬럼이 추가되었습니다.")
                st.rerun()

    st.divider()

    st.markdown("### 컬럼명 수정")

    if extra_columns:
        old_col = st.selectbox("수정할 컬럼 선택", extra_columns)
        renamed_col = st.text_input("새 컬럼명", value=old_col)

        if st.button("컬럼명 수정"):
            if rename_extra_column(old_col, renamed_col):
                st.success("컬럼명이 수정되었습니다.")
                st.rerun()
    else:
        st.info("수정할 추가 컬럼이 없습니다.")

    st.divider()

    st.markdown("### 컬럼 삭제")

    if extra_columns:
        delete_col = st.selectbox("삭제할 컬럼 선택", extra_columns, key="delete_col")

        if st.button("컬럼 삭제"):
            if delete_extra_column(delete_col):
                st.success("컬럼이 삭제되었습니다.")
                st.rerun()
    else:
        st.info("삭제할 추가 컬럼이 없습니다.")

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
            warehouse_map = dict(zip(items_df["id"], items_df["warehouse"]))

            history_df["품목명"] = history_df["item_id"].map(item_map)
            history_df["창고"] = history_df["item_id"].map(warehouse_map)

        show_cols = [
            "created_at",
            "창고",
            "품목명",
            "change_type",
            "change_qty",
            "before_qty",
            "after_qty",
            "memo"
        ]

        for col in show_cols:
            if col not in history_df.columns:
                history_df[col] = ""

        show_df = history_df[show_cols].rename(columns={
            "created_at": "일시",
            "change_type": "구분",
            "change_qty": "수량",
            "before_qty": "이전재고",
            "after_qty": "처리후재고",
            "memo": "비고"
        })

        st.dataframe(show_df, use_container_width=True, hide_index=True)