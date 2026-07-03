# Main.py
# 안전창고 재고관리 시스템 V5.3.2
# 고정 재고 컬럼: 1창고, 2창고, 기자재실
# 재고현황에서만 현재재고 직접 수정 가능

import streamlit as st
import pandas as pd
from datetime import datetime
from supabase import create_client, Client

st.set_page_config(
    page_title="안전창고 재고관리 시스템 V5.3.2",
    page_icon="📦",
    layout="wide"
)

APP_VERSION = "V5.3.2"
PURCHASE_ACCOUNTS = ["일반수선비", "안전보호구"]
WAREHOUSE_COLUMNS = {
    "1창고": "warehouse_1_qty",
    "2창고": "warehouse_2_qty",
    "기자재실": "material_room_qty"
}

@st.cache_resource
def init_supabase() -> Client:
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_KEY"]
    return create_client(url, key)

supabase = init_supabase()

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

def load_items():
    try:
        result = supabase.table("items").select("*").order("id").execute()
        df = pd.DataFrame(result.data or [])

        required_cols = {
            "id": 0,
            "item_name": "",
            "unit": "EA",
            "location": "",
            "warehouse_1_qty": 0,
            "warehouse_2_qty": 0,
            "material_room_qty": 0,
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

        number_cols = [
            "warehouse_1_qty",
            "warehouse_2_qty",
            "material_room_qty",
            "optimal_stock",
            "unit_price"
        ]

        for col in number_cols:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0).astype(int)

        df["purchase_account"] = df["purchase_account"].apply(normalize_account)

        return df

    except Exception as e:
        st.error(f"품목 데이터 조회 오류: {e}")
        return pd.DataFrame()

def load_history():
    try:
        result = supabase.table("stock_history").select("*").order("id", desc=True).execute()
        return pd.DataFrame(result.data or [])
    except:
        return pd.DataFrame()

def add_item(item_name, unit, location, optimal_stock, unit_price, purchase_account):
    data = {
        "item_name": item_name,
        "unit": unit,
        "location": location,
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

def update_item(item_id, item_name, unit, location, optimal_stock, unit_price, purchase_account):
    data = {
        "item_name": item_name,
        "unit": unit,
        "location": location,
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

def update_stock_direct(item_id, warehouse_1_qty, warehouse_2_qty, material_room_qty):
    try:
        supabase.table("items").update({
            "warehouse_1_qty": safe_int(warehouse_1_qty),
            "warehouse_2_qty": safe_int(warehouse_2_qty),
            "material_room_qty": safe_int(material_room_qty),
            "updated_at": now_text()
        }).eq("id", item_id).execute()
        return True
    except Exception as e:
        st.error(f"재고 수정 오류: {e}")
        return False

def update_stock_inout(item_id, warehouse_col, current_qty, change_qty, change_type, memo):
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
            warehouse_col: new_qty,
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

        try:
            supabase.table("stock_history").insert(history_data).execute()
        except:
            pass

        return True

    except Exception as e:
        st.error(f"입출고 처리 오류: {e}")
        return False

def make_display_df(df):
    view_df = df.copy()

    view_df["현재재고"] = (
        view_df["warehouse_1_qty"]
        + view_df["warehouse_2_qty"]
        + view_df["material_room_qty"]
    )
    view_df["총금액"] = view_df["현재재고"] * view_df["unit_price"]
    view_df["재고상태"] = view_df.apply(
        lambda row: "구매필요" if safe_int(row["현재재고"]) < safe_int(row["optimal_stock"]) else "정상",
        axis=1
    )

    view_df = view_df.rename(columns={
        "id": "ID",
        "item_name": "품목명",
        "unit": "단위",
        "location": "보관위치",
        "warehouse_1_qty": "1창고",
        "warehouse_2_qty": "2창고",
        "material_room_qty": "기자재실",
        "optimal_stock": "적정재고",
        "unit_price": "단가",
        "purchase_account": "구매계정"
    })

    return view_df[[
        "ID",
        "품목명",
        "단위",
        "보관위치",
        "1창고",
        "2창고",
        "기자재실",
        "현재재고",
        "적정재고",
        "단가",
        "구매계정",
        "총금액",
        "재고상태"
    ]]

st.title(f"📦 안전창고 재고관리 시스템 {APP_VERSION}")

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

if menu == "재고현황":
    st.subheader("📋 재고현황")

    col1, col2 = st.columns(2)

    with col1:
        keyword = st.text_input("품목명 검색")

    with col2:
        account_filter = st.selectbox("구매계정 선택", ["전체"] + PURCHASE_ACCOUNTS)

    df = items_df.copy()

    if not df.empty:
        if keyword:
            df = df[df["item_name"].astype(str).str.contains(keyword, case=False, na=False)]

        if account_filter != "전체":
            df = df[df["purchase_account"] == account_filter]

    if df.empty:
        st.info("등록된 품목이 없습니다.")
    else:
        display_df = make_display_df(df)

        st.info("재고현황 화면에서만 1창고, 2창고, 기자재실 재고를 직접 수정할 수 있습니다.")

        edited_df = st.data_editor(
            display_df,
            use_container_width=True,
            hide_index=True,
            disabled=[
                "ID",
                "품목명",
                "단위",
                "보관위치",
                "현재재고",
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

        if st.button("현재재고 저장", type="primary"):
            success_count = 0

            for _, row in edited_df.iterrows():
                if update_stock_direct(
                    row["ID"],
                    row["1창고"],
                    row["2창고"],
                    row["기자재실"]
                ):
                    success_count += 1

            st.success(f"현재재고가 저장되었습니다. 저장 품목 수: {success_count}개")
            st.rerun()

        total_stock_amount = display_df["총금액"].sum()
        purchase_need_count = len(display_df[display_df["재고상태"] == "구매필요"])

        m1, m2, m3 = st.columns(3)
        m1.metric("전체 품목 수", f"{len(display_df):,}개")
        m2.metric("구매필요 품목 수", f"{purchase_need_count:,}개")
        m3.metric("현재 재고 총금액", format_won(total_stock_amount))

elif menu == "입고/출고":
    st.subheader("🔄 입고 / 출고 처리")

    if items_df.empty:
        st.info("등록된 품목이 없습니다.")
    else:
        item_options = {
            f"{row['id']} - {row['item_name']}": row
            for _, row in items_df.iterrows()
        }

        selected_label = st.selectbox("품목 선택", list(item_options.keys()))
        selected_item = item_options[selected_label]

        warehouse_name = st.selectbox("창고 선택", list(WAREHOUSE_COLUMNS.keys()))
        warehouse_col = WAREHOUSE_COLUMNS[warehouse_name]
        current_qty = safe_int(selected_item.get(warehouse_col, 0))

        st.write(f"선택 창고 현재재고: **{current_qty:,} {selected_item.get('unit', '')}**")

        col1, col2 = st.columns(2)

        with col1:
            change_type = st.radio("구분", ["입고", "출고"], horizontal=True)

        with col2:
            change_qty = st.number_input("수량", min_value=1, step=1)

        memo = st.text_input("비고")

        if st.button("처리하기", type="primary"):
            if update_stock_inout(
                selected_item["id"],
                warehouse_col,
                current_qty,
                change_qty,
                change_type,
                memo
            ):
                st.success(f"{warehouse_name} {change_type} 처리가 완료되었습니다.")
                st.rerun()

elif menu == "품목관리":
    st.subheader("🛠 품목관리")

    tab1, tab2 = st.tabs(["품목 등록", "품목 수정/삭제"])

    with tab1:
        st.markdown("### 신규 품목 등록")

        with st.form("add_item_form"):
            col1, col2 = st.columns(2)

            with col1:
                item_name = st.text_input("품목명")
                unit = st.text_input("단위", value="EA")
                location = st.text_input("보관위치")

            with col2:
                optimal_stock = st.number_input("적정재고", min_value=0, step=1)
                unit_price = st.number_input("단가", min_value=0, step=100)
                purchase_account = st.selectbox("구매계정", PURCHASE_ACCOUNTS)

            st.info("현재재고는 재고현황 메뉴에서만 입력 및 수정할 수 있습니다.")

            submitted = st.form_submit_button("등록")

            if submitted:
                if not item_name.strip():
                    st.warning("품목명을 입력해주세요.")
                else:
                    if add_item(
                        item_name,
                        unit,
                        location,
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
                    edit_unit = st.text_input("단위", value=str(selected_item.get("unit", "EA")))
                    edit_location = st.text_input("보관위치", value=str(selected_item.get("location", "")))

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

                    current_account = normalize_account(selected_item.get("purchase_account", "일반수선비"))

                    edit_purchase_account = st.selectbox(
                        "구매계정",
                        PURCHASE_ACCOUNTS,
                        index=PURCHASE_ACCOUNTS.index(current_account)
                    )

                st.info("현재재고는 재고현황 메뉴에서만 수정할 수 있습니다.")

                col_save, col_delete = st.columns(2)

                save_clicked = col_save.form_submit_button("수정 저장")
                delete_clicked = col_delete.form_submit_button("삭제")

                if save_clicked:
                    if update_item(
                        selected_item["id"],
                        edit_item_name,
                        edit_unit,
                        edit_location,
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

elif menu == "구매필요목록":
    st.subheader("🛒 구매필요목록")

    if items_df.empty:
        st.info("등록된 품목이 없습니다.")
    else:
        purchase_df = items_df.copy()

        purchase_df["현재재고"] = (
            purchase_df["warehouse_1_qty"]
            + purchase_df["warehouse_2_qty"]
            + purchase_df["material_room_qty"]
        )
        purchase_df["구매필요수량"] = purchase_df["optimal_stock"] - purchase_df["현재재고"]
        purchase_df["구매필요수량"] = purchase_df["구매필요수량"].apply(lambda x: x if x > 0 else 0)
        purchase_df["구매금액"] = purchase_df["구매필요수량"] * purchase_df["unit_price"]

        purchase_df = purchase_df[purchase_df["구매필요수량"] > 0]

        if purchase_df.empty:
            st.success("현재 구매가 필요한 품목이 없습니다.")
        else:
            st.metric("전체 구매금액", format_won(purchase_df["구매금액"].sum()))

            st.markdown("### 구매계정별 합계")

            summary_df = purchase_df.groupby("purchase_account", as_index=False)["구매금액"].sum()
            summary_df = summary_df.rename(columns={
                "purchase_account": "구매계정"
            })
            summary_df["구매금액"] = summary_df["구매금액"].apply(format_won)

            st.dataframe(summary_df, use_container_width=True, hide_index=True)

            st.markdown("### 구매계정별 구매필요목록")

            for account in PURCHASE_ACCOUNTS:
                account_df = purchase_df[purchase_df["purchase_account"] == account].copy()

                if account_df.empty:
                    continue

                st.markdown(f"#### {account} / 합계: {format_won(account_df['구매금액'].sum())}")

                show_df = account_df.rename(columns={
                    "item_name": "품목명",
                    "unit": "단위",
                    "location": "보관위치",
                    "warehouse_1_qty": "1창고",
                    "warehouse_2_qty": "2창고",
                    "material_room_qty": "기자재실",
                    "optimal_stock": "적정재고",
                    "unit_price": "단가",
                    "purchase_account": "구매계정"
                })

                show_df = show_df[[
                    "품목명",
                    "단위",
                    "보관위치",
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

                st.dataframe(show_df, use_container_width=True, hide_index=True)

            csv = purchase_df.to_csv(index=False).encode("utf-8-sig")

            st.download_button(
                label="구매필요목록 CSV 다운로드",
                data=csv,
                file_name="purchase_required_list_v5_3_2.csv",
                mime="text/csv"
            )

elif menu == "입출고 이력":
    st.subheader("📑 입출고 이력")

    history_df = load_history()

    if history_df.empty:
        st.info("입출고 이력이 없습니다.")
    else:
        item_map = dict(zip(items_df["id"], items_df["item_name"])) if not items_df.empty else {}
        history_df["품목명"] = history_df["item_id"].map(item_map)

        show_cols = [
            "created_at",
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