# Main.py
# 안전창고 재고관리 시스템 V5.6
# 개선사항:
# - 품목관리에서 보관위치 복수선택 가능
# - 보관위치에 선택한 창고 모두 표시
# - 재고현황에서 선택한 창고에 해당 품목이 조회됨
# - 예: A품목 보관위치가 1창고, 2창고이면 1창고/2창고 재고현황에 모두 표시

import streamlit as st
import pandas as pd
from datetime import datetime
from io import BytesIO
from supabase import create_client, Client

st.set_page_config(
    page_title="안전창고 재고관리 시스템 V5.6",
    page_icon="📦",
    layout="wide"
)

APP_VERSION = "V5.6"

PURCHASE_ACCOUNTS = ["일반수선비", "안전보호구"]
WAREHOUSE_NAMES = ["1창고", "2창고", "기자재실"]

WAREHOUSE_MAP = {
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
    except Exception:
        return default


def safe_str(value, default=""):
    if value is None:
        return default
    return str(value).strip()


def format_won(value):
    return f"{safe_int(value):,}원"


def normalize_account(value):
    value = safe_str(value)
    if value in PURCHASE_ACCOUNTS:
        return value
    return "일반수선비"


def parse_locations(value):
    if value is None:
        return ["1창고"]

    if isinstance(value, list):
        result = [v for v in value if v in WAREHOUSE_NAMES]
        return result if result else ["1창고"]

    text = str(value).strip()

    if not text:
        return ["1창고"]

    result = []
    for part in text.replace("/", ",").split(","):
        part = part.strip()
        if part in WAREHOUSE_NAMES and part not in result:
            result.append(part)

    return result if result else ["1창고"]


def locations_to_text(value):
    locations = parse_locations(value)
    return ", ".join(locations)


def has_location(value, location):
    return location in parse_locations(value)


def to_excel_bytes(df_dict):
    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        for sheet_name, df in df_dict.items():
            df.to_excel(writer, index=False, sheet_name=str(sheet_name)[:31])
    output.seek(0)
    return output.getvalue()


def load_items():
    required_cols = {
        "id": 0,
        "item_name": "",
        "unit": "EA",
        "storage_location": "1창고",
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

        for col in [
            "warehouse_1_qty",
            "warehouse_2_qty",
            "material_room_qty",
            "optimal_stock",
            "unit_price"
        ]:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0).astype(int)

        df["item_name"] = df["item_name"].fillna("").astype(str).str.strip()
        df["unit"] = df["unit"].fillna("EA").astype(str).str.strip()
        df["storage_location"] = df["storage_location"].apply(locations_to_text)
        df["purchase_account"] = df["purchase_account"].apply(normalize_account)

        return df[list(required_cols.keys())]

    except Exception as e:
        st.error(f"품목 데이터 조회 오류: {e}")
        return pd.DataFrame(columns=list(required_cols.keys()))


def insert_item(row):
    data = {
        "item_name": safe_str(row["품목명"]),
        "unit": safe_str(row["단위"], "EA"),
        "storage_location": locations_to_text(row["보관위치"]),
        "warehouse_1_qty": 0,
        "warehouse_2_qty": 0,
        "material_room_qty": 0,
        "optimal_stock": safe_int(row["적정재고"]),
        "unit_price": safe_int(row["단가"]),
        "purchase_account": normalize_account(row["구매계정"]),
        "created_at": now_text(),
        "updated_at": now_text()
    }

    try:
        supabase.table("items").insert(data).execute()
        return True
    except Exception as e:
        st.error(f"품목 등록 오류: {e}")
        return False


def update_item(row):
    data = {
        "item_name": safe_str(row["품목명"]),
        "unit": safe_str(row["단위"], "EA"),
        "storage_location": locations_to_text(row["보관위치"]),
        "optimal_stock": safe_int(row["적정재고"]),
        "unit_price": safe_int(row["단가"]),
        "purchase_account": normalize_account(row["구매계정"]),
        "updated_at": now_text()
    }

    try:
        supabase.table("items").update(data).eq("id", safe_int(row["ID"])).execute()
        return True
    except Exception as e:
        st.error(f"품목 수정 오류: {e}")
        return False


def delete_item(item_id):
    try:
        supabase.table("items").delete().eq("id", safe_int(item_id)).execute()
        return True
    except Exception as e:
        st.error(f"품목 삭제 오류: {e}")
        return False


def update_stock(item_id, warehouse_col, qty):
    try:
        supabase.table("items").update({
            warehouse_col: safe_int(qty),
            "updated_at": now_text()
        }).eq("id", safe_int(item_id)).execute()
        return True
    except Exception as e:
        st.error(f"재고 저장 오류: {e}")
        return False


def make_inventory_df(df, selected_warehouse):
    warehouse_col = WAREHOUSE_MAP[selected_warehouse]
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
        "storage_location": "보관위치",
        "optimal_stock": "적정재고",
        "unit_price": "단가",
        "purchase_account": "구매계정"
    })

    return result[[
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
    ]]


def make_item_manage_df(df):
    if df.empty:
        return pd.DataFrame(columns=[
            "삭제", "ID", "보관위치", "품목명", "단위", "적정재고", "단가", "구매계정"
        ])

    result = df.copy()

    result = result.rename(columns={
        "id": "ID",
        "storage_location": "보관위치",
        "item_name": "품목명",
        "unit": "단위",
        "optimal_stock": "적정재고",
        "unit_price": "단가",
        "purchase_account": "구매계정"
    })

    result["보관위치"] = result["보관위치"].apply(parse_locations)
    result["삭제"] = False

    return result[[
        "삭제",
        "ID",
        "보관위치",
        "품목명",
        "단위",
        "적정재고",
        "단가",
        "구매계정"
    ]]


def make_purchase_detail_df(df, location_filter, account_filter):
    result = df.copy()

    if location_filter != "전체":
        result = result[result["storage_location"].apply(lambda x: has_location(x, location_filter))].copy()

    if result.empty:
        return pd.DataFrame()

    rows = []

    for _, row in result.iterrows():
        locations = parse_locations(row["storage_location"])

        if location_filter != "전체":
            locations = [location_filter]

        for loc in locations:
            current_qty = safe_int(row[WAREHOUSE_MAP[loc]])
            optimal_stock = safe_int(row["optimal_stock"])
            need_qty = max(optimal_stock - current_qty, 0)
            unit_price = safe_int(row["unit_price"])
            amount = need_qty * unit_price

            if need_qty > 0:
                rows.append({
                    "품목명": row["item_name"],
                    "단위": row["unit"],
                    "보관위치": loc,
                    "현재재고": current_qty,
                    "적정재고": optimal_stock,
                    "구매필요수량": need_qty,
                    "단가": unit_price,
                    "구매금액": amount,
                    "구매계정": row["purchase_account"]
                })

    detail_df = pd.DataFrame(rows)

    if detail_df.empty:
        return pd.DataFrame()

    if account_filter != "전체":
        detail_df = detail_df[detail_df["구매계정"] == account_filter].copy()

    return detail_df


def make_purchase_group_df(detail_df):
    if detail_df.empty:
        return pd.DataFrame()

    group_df = (
        detail_df
        .groupby(["품목명", "단위", "단가", "구매계정"], as_index=False)
        .agg(
            보관위치=("보관위치", lambda x: ", ".join(sorted(set(x), key=lambda y: WAREHOUSE_NAMES.index(y)))),
            현재재고=("현재재고", "sum"),
            적정재고=("적정재고", "sum"),
            구매필요수량=("구매필요수량", "sum"),
            구매금액=("구매금액", "sum")
        )
    )

    return group_df[[
        "품목명",
        "단위",
        "보관위치",
        "현재재고",
        "적정재고",
        "구매필요수량",
        "단가",
        "구매금액",
        "구매계정"
    ]]


def make_summary_df(purchase_df):
    if purchase_df.empty:
        return pd.DataFrame()

    return (
        purchase_df
        .groupby("구매계정", as_index=False)
        .agg(
            구매필요품목수=("품목명", "count"),
            구매필요총수량=("구매필요수량", "sum"),
            구매금액=("구매금액", "sum")
        )
    )


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


if menu == "재고현황":
    st.subheader("📋 재고현황 / 창고별 재고조사")

    col1, col2 = st.columns(2)

    with col1:
        selected_warehouse = st.selectbox("보관위치 선택", WAREHOUSE_NAMES)

    with col2:
        keyword = st.text_input("품목명 검색")

    df = items_df.copy()
    df = df[df["storage_location"].apply(lambda x: has_location(x, selected_warehouse))].copy()

    if keyword:
        df = df[df["item_name"].astype(str).str.contains(keyword, case=False, na=False)]

    if df.empty:
        st.info(f"{selected_warehouse}에 등록된 품목이 없습니다.")
    else:
        st.info(f"{selected_warehouse}에 등록된 품목만 표시됩니다. 현재재고만 수정할 수 있습니다.")

        display_df = make_inventory_df(df, selected_warehouse)

        edited_df = st.data_editor(
            display_df,
            use_container_width=True,
            hide_index=True,
            disabled=[
                "ID",
                "품목명",
                "단위",
                "보관위치",
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
                if update_stock(row["ID"], warehouse_col, row["현재재고"]):
                    success_count += 1

            st.success(f"{selected_warehouse} 재고가 저장되었습니다. 저장 품목 수: {success_count}개")
            st.rerun()

        m1, m2, m3 = st.columns(3)
        m1.metric("표시 품목 수", f"{len(display_df):,}개")
        m2.metric("구매필요 품목 수", f"{len(display_df[display_df['재고상태'] == '구매필요']):,}개")
        m3.metric("표시 재고금액", format_won(display_df["총금액"].sum()))


elif menu == "품목관리":
    st.subheader("🛠 품목관리")

    st.info("보관위치는 복수 선택할 수 있습니다. 재고 수량은 재고현황 메뉴에서 창고별로 입력합니다.")

    col1, col2, col3 = st.columns(3)

    with col1:
        keyword = st.text_input("품목명 검색")

    with col2:
        location_filter = st.selectbox("보관위치 필터", ["전체"] + WAREHOUSE_NAMES)

    with col3:
        account_filter = st.selectbox("구매계정 필터", ["전체"] + PURCHASE_ACCOUNTS)

    df = items_df.copy()

    if keyword:
        df = df[df["item_name"].astype(str).str.contains(keyword, case=False, na=False)]

    if location_filter != "전체":
        df = df[df["storage_location"].apply(lambda x: has_location(x, location_filter))]

    if account_filter != "전체":
        df = df[df["purchase_account"] == account_filter]

    manage_df = make_item_manage_df(df)

    edited_df = st.data_editor(
        manage_df,
        use_container_width=True,
        hide_index=True,
        num_rows="dynamic",
        disabled=["ID"],
        column_config={
            "삭제": st.column_config.CheckboxColumn("삭제"),
            "ID": st.column_config.NumberColumn("ID"),
            "보관위치": st.column_config.MultiselectColumn(
                "보관위치",
                options=WAREHOUSE_NAMES,
                required=True
            ),
            "품목명": st.column_config.TextColumn("품목명", required=True),
            "단위": st.column_config.TextColumn("단위", required=True),
            "적정재고": st.column_config.NumberColumn("적정재고", min_value=0, step=1),
            "단가": st.column_config.NumberColumn("단가", min_value=0, step=100),
            "구매계정": st.column_config.SelectboxColumn(
                "구매계정",
                options=PURCHASE_ACCOUNTS,
                required=True
            )
        }
    )

    col_save, col_delete = st.columns(2)

    with col_save:
        if st.button("저장", type="primary"):
            save_df = edited_df.copy()
            save_df["품목명"] = save_df["품목명"].fillna("").astype(str).str.strip()
            save_df["단위"] = save_df["단위"].fillna("EA").astype(str).str.strip()
            save_df["보관위치"] = save_df["보관위치"].apply(parse_locations)
            save_df["구매계정"] = save_df["구매계정"].apply(normalize_account)

            save_target_df = save_df[save_df["삭제"] != True].copy()

            if save_target_df.empty:
                st.warning("저장할 품목이 없습니다.")
            elif (save_target_df["품목명"] == "").any():
                st.warning("품목명이 비어있는 행이 있습니다.")
            elif save_target_df["보관위치"].apply(lambda x: len(x) == 0).any():
                st.warning("보관위치를 1개 이상 선택해주세요.")
            else:
                success_count = 0

                for _, row in save_target_df.iterrows():
                    row_id = row.get("ID", "")

                    if pd.isna(row_id) or row_id == "" or safe_int(row_id) == 0:
                        if insert_item(row):
                            success_count += 1
                    else:
                        if update_item(row):
                            success_count += 1

                st.success(f"저장되었습니다. 처리 품목 수: {success_count}개")
                st.rerun()

    with col_delete:
        if st.button("선택 삭제"):
            delete_df = edited_df[edited_df["삭제"] == True].copy()

            if delete_df.empty:
                st.warning("삭제할 품목을 선택해주세요.")
            else:
                success_count = 0

                for _, row in delete_df.iterrows():
                    if not pd.isna(row["ID"]) and safe_int(row["ID"]) > 0:
                        if delete_item(row["ID"]):
                            success_count += 1

                st.success(f"삭제되었습니다. 삭제 품목 수: {success_count}개")
                st.rerun()


elif menu == "구매필요목록":
    st.subheader("🛒 구매필요목록")

    if items_df.empty:
        st.info("등록된 품목이 없습니다.")
    else:
        filter_col1, filter_col2, filter_col3 = st.columns(3)

        with filter_col1:
            location_filter = st.selectbox("보관위치", ["전체"] + WAREHOUSE_NAMES)

        with filter_col2:
            account_filter = st.selectbox("구매계정", ["전체"] + PURCHASE_ACCOUNTS)

        with filter_col3:
            sort_option = st.selectbox(
                "정렬",
                ["구매금액 큰순", "구매필요수량 큰순", "품목명순"]
            )

        detail_df = make_purchase_detail_df(items_df, location_filter, account_filter)
        purchase_df = make_purchase_group_df(detail_df)

        if purchase_df.empty:
            st.success("현재 구매가 필요한 품목이 없습니다.")
        else:
            if sort_option == "구매금액 큰순":
                purchase_df = purchase_df.sort_values("구매금액", ascending=False)
            elif sort_option == "구매필요수량 큰순":
                purchase_df = purchase_df.sort_values("구매필요수량", ascending=False)
            else:
                purchase_df = purchase_df.sort_values("품목명", ascending=True)

            summary_df = make_summary_df(purchase_df)

            total_amount = purchase_df["구매금액"].sum()
            total_qty = purchase_df["구매필요수량"].sum()

            m1, m2, m3 = st.columns(3)
            m1.metric("구매필요 품목 수", f"{len(purchase_df):,}개")
            m2.metric("구매필요 총수량", f"{safe_int(total_qty):,}개")
            m3.metric("전체 구매금액", format_won(total_amount))

            st.markdown("### 구매계정별 합계")

            summary_display_df = summary_df.copy()
            summary_display_df["구매필요총수량"] = summary_display_df["구매필요총수량"].apply(lambda x: f"{safe_int(x):,}개")
            summary_display_df["구매금액"] = summary_display_df["구매금액"].apply(format_won)

            st.dataframe(summary_display_df, use_container_width=True, hide_index=True)

            st.markdown("### 구매필요 통합목록")

            display_df = purchase_df.copy()
            display_df["단가"] = display_df["단가"].apply(format_won)
            display_df["구매금액"] = display_df["구매금액"].apply(format_won)

            st.dataframe(display_df, use_container_width=True, hide_index=True)

            excel_data = to_excel_bytes({
                "구매필요통합목록": purchase_df,
                "구매필요상세목록": detail_df,
                "구매계정별합계": summary_df
            })

            st.download_button(
                label="엑셀 다운로드",
                data=excel_data,
                file_name=f"구매필요목록_{APP_VERSION}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )