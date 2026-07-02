from datetime import datetime
from io import BytesIO

import pandas as pd
import streamlit as st
from supabase import create_client


APP_TITLE = "📦 안전창고 재고관리 V5.0"


st.set_page_config(
    page_title="안전창고 재고관리 V5.0",
    page_icon="📦",
    layout="wide"
)


@st.cache_resource
def get_supabase():
    url = st.secrets.get("SUPABASE_URL", "")
    key = st.secrets.get("SUPABASE_KEY", "")

    if not url or not key:
        st.error("Supabase 설정값이 없습니다. Streamlit Secrets를 확인하세요.")
        st.stop()

    return create_client(url, key)


supabase = get_supabase()


def now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def to_excel(df):
    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Sheet1")
    return output.getvalue()


def calc_purchase_qty(current_stock, target_stock):
    return max(int(target_stock) - int(current_stock), 0)


def get_items(active_only=True):
    query = supabase.table("items").select("*")

    if active_only:
        query = query.eq("is_active", 1)

    data = query.order("warehouse").order("item_name").execute().data
    return pd.DataFrame(data)


def get_records():
    data = (
        supabase.table("records")
        .select("*")
        .order("check_time", desc=True)
        .execute()
        .data
    )
    return pd.DataFrame(data)


def get_latest_stock():
    items = get_items(active_only=True)
    records = get_records()

    if items.empty:
        return pd.DataFrame()

    result = []

    for _, item in items.iterrows():
        item_id = int(item["id"])

        if records.empty:
            matched = pd.DataFrame()
        else:
            matched = records[records["item_id"] == item_id]

        if matched.empty:
            current_stock = 0
            check_time = ""
            checker = ""
        else:
            latest = matched.sort_values("check_time").tail(1).iloc[0]
            current_stock = int(latest["current_stock"])
            check_time = latest["check_time"]
            checker = latest["checker"]

        result.append({
            "최종수정일": check_time,
            "입력자": checker,
            "창고": item["warehouse"],
            "품목ID": item_id,
            "품목명": item["item_name"],
            "현재재고": current_stock,
            "최소재고": int(item["min_stock"]),
            "적정재고": int(item["target_stock"]),
            "구매 필요량": calc_purchase_qty(current_stock, item["target_stock"])
        })

    return pd.DataFrame(result).sort_values(["창고", "품목명"])


def add_item(warehouse, item_name, min_stock, target_stock):
    supabase.table("items").insert({
        "warehouse": warehouse,
        "item_name": item_name,
        "min_stock": int(min_stock),
        "target_stock": int(target_stock),
        "is_active": 1,
        "created_at": now(),
        "updated_at": now()
    }).execute()


def update_item(item_id, warehouse, item_name, min_stock, target_stock, is_active):
    supabase.table("items").update({
        "warehouse": warehouse,
        "item_name": item_name,
        "min_stock": int(min_stock),
        "target_stock": int(target_stock),
        "is_active": 1 if is_active else 0,
        "updated_at": now()
    }).eq("id", int(item_id)).execute()


def delete_item(item_id):
    supabase.table("records").delete().eq("item_id", int(item_id)).execute()
    supabase.table("items").delete().eq("id", int(item_id)).execute()


def save_stock(checker, warehouse, rows):
    check_time = now()

    insert_rows = []

    for r in rows:
        insert_rows.append({
            "check_time": check_time,
            "checker": checker,
            "warehouse": warehouse,
            "item_id": int(r["item_id"]),
            "item_name": r["item_name"],
            "current_stock": int(r["current_stock"]),
            "min_stock": int(r["min_stock"]),
            "target_stock": int(r["target_stock"]),
            "purchase_qty": int(r["purchase_qty"])
        })

    if insert_rows:
        supabase.table("records").insert(insert_rows).execute()


st.title(APP_TITLE)
st.caption("Supabase 연동 버전 / PC·휴대폰 실시간 데이터 공유")

menu = st.sidebar.radio(
    "메뉴 선택",
    ["📦 재고조사", "📋 재고현황", "🛒 구매필요목록", "⚙ 품목관리", "🕒 조사이력"]
)

checker = st.sidebar.text_input("입력자 이름", placeholder="예: 홍길동")

st.divider()


if menu == "📦 재고조사":
    st.header("📦 재고조사")

    if not checker.strip():
        st.warning("왼쪽 사이드바에 입력자 이름을 입력하세요.")
        st.stop()

    warehouse = st.selectbox("창고 선택", ["1창고", "2창고"])

    items = get_items(active_only=True)

    if items.empty:
        st.info("등록된 품목이 없습니다. 품목관리에서 품목을 추가하세요.")
        st.stop()

    items = items[items["warehouse"] == warehouse]

    if items.empty:
        st.info(f"{warehouse}에 등록된 품목이 없습니다.")
        st.stop()

    latest = get_latest_stock()

    st.info("현재재고를 입력하면 구매 필요량이 자동 계산됩니다.")

    save_rows = []

    with st.form("stock_form"):
        for _, item in items.iterrows():
            item_id = int(item["id"])

            matched = latest[latest["품목ID"] == item_id] if not latest.empty else pd.DataFrame()
            default_stock = 0 if matched.empty else int(matched.iloc[0]["현재재고"])

            col1, col2, col3, col4 = st.columns([3, 1, 1, 2])

            with col1:
                st.markdown(f"### {item['item_name']}")

            with col2:
                st.write(f"최소: {int(item['min_stock'])}")

            with col3:
                st.write(f"적정: {int(item['target_stock'])}")

            with col4:
                current_stock = st.number_input(
                    "현재재고",
                    min_value=0,
                    step=1,
                    value=default_stock,
                    key=f"stock_{item_id}",
                    label_visibility="collapsed"
                )

            purchase_qty = calc_purchase_qty(current_stock, item["target_stock"])
            st.caption(f"구매 필요량: {purchase_qty}")
            st.divider()

            save_rows.append({
                "item_id": item_id,
                "item_name": item["item_name"],
                "current_stock": current_stock,
                "min_stock": int(item["min_stock"]),
                "target_stock": int(item["target_stock"]),
                "purchase_qty": purchase_qty
            })

        submitted = st.form_submit_button("✅ 재고조사 저장")

    if submitted:
        save_stock(checker.strip(), warehouse, save_rows)
        st.success("재고조사가 저장되었습니다.")
        st.rerun()


elif menu == "📋 재고현황":
    st.header("📋 재고현황")

    df = get_latest_stock()

    if df.empty:
        st.info("등록된 품목이 없습니다.")
        st.stop()

    warehouse_filter = st.selectbox("창고 선택", ["전체", "1창고", "2창고"])

    if warehouse_filter != "전체":
        df = df[df["창고"] == warehouse_filter]

    view = df[[
        "최종수정일",
        "입력자",
        "창고",
        "품목명",
        "현재재고",
        "적정재고",
        "구매 필요량"
    ]]

    st.dataframe(view, use_container_width=True, hide_index=True)

    col1, col2, col3 = st.columns(3)
    col1.metric("전체 품목 수", len(view))
    col2.metric("구매 필요 품목", int((view["구매 필요량"] > 0).sum()))
    col3.metric("구매 불필요 품목", int((view["구매 필요량"] == 0).sum()))

    st.download_button(
        "📥 재고현황 엑셀 다운로드",
        data=to_excel(view),
        file_name="안전창고_재고현황.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )


elif menu == "🛒 구매필요목록":
    st.header("🛒 구매필요목록")

    df = get_latest_stock()

    if df.empty:
        st.info("등록된 품목이 없습니다.")
        st.stop()

    df = df[df["구매 필요량"] > 0]

    warehouse_filter = st.selectbox("창고 선택", ["전체", "1창고", "2창고"])

    if warehouse_filter != "전체":
        df = df[df["창고"] == warehouse_filter]

    if df.empty:
        st.success("구매가 필요한 품목이 없습니다.")
    else:
        view = df[[
            "창고",
            "품목명",
            "현재재고",
            "적정재고",
            "구매 필요량"
        ]]

        st.dataframe(view, use_container_width=True, hide_index=True)

        st.download_button(
            "📥 구매필요목록 엑셀 다운로드",
            data=to_excel(view),
            file_name="안전창고_구매필요목록.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )


elif menu == "⚙ 품목관리":
    st.header("⚙ 품목관리")

    tab1, tab2, tab3 = st.tabs(["➕ 품목 추가", "✏️ 품목 수정 / 미사용", "🗑️ 품목 삭제"])

    with tab1:
        st.subheader("품목 추가")

        with st.form("add_item"):
            warehouse = st.selectbox("창고", ["1창고", "2창고"])
            item_name = st.text_input("품목명")
            min_stock = st.number_input("최소재고", min_value=0, step=1)
            target_stock = st.number_input("적정재고", min_value=0, step=1)

            submitted = st.form_submit_button("➕ 품목 추가")

        if submitted:
            item_name = item_name.strip()

            if not item_name:
                st.warning("품목명을 입력하세요.")
            elif target_stock < min_stock:
                st.warning("적정재고는 최소재고보다 크거나 같아야 합니다.")
            else:
                items = get_items(active_only=False)
                duplicate = pd.DataFrame()

                if not items.empty:
                    duplicate = items[
                        (items["warehouse"] == warehouse) &
                        (items["item_name"] == item_name)
                    ]

                if not duplicate.empty:
                    st.warning("같은 창고에 동일한 품목명이 있습니다.")
                else:
                    add_item(warehouse, item_name, min_stock, target_stock)
                    st.success("품목이 추가되었습니다.")
                    st.rerun()

    with tab2:
        st.subheader("품목 수정 / 미사용 처리")

        items = get_items(active_only=False)

        if items.empty:
            st.info("등록된 품목이 없습니다.")
        else:
            view = items.copy()
            view["사용여부"] = view["is_active"].map({1: "사용", 0: "미사용"})

            st.dataframe(
                view[["id", "warehouse", "item_name", "min_stock", "target_stock", "사용여부"]].rename(columns={
                    "id": "ID",
                    "warehouse": "창고",
                    "item_name": "품목명",
                    "min_stock": "최소재고",
                    "target_stock": "적정재고"
                }),
                use_container_width=True,
                hide_index=True
            )

            options = items["id"].astype(str) + " | " + items["warehouse"] + " | " + items["item_name"]
            selected = st.selectbox("수정할 품목 선택", options)

            selected_id = int(selected.split(" | ")[0])
            selected_item = items[items["id"] == selected_id].iloc[0]

            with st.form("edit_item"):
                edit_warehouse = st.selectbox(
                    "창고",
                    ["1창고", "2창고"],
                    index=0 if selected_item["warehouse"] == "1창고" else 1
                )

                edit_name = st.text_input("품목명", value=selected_item["item_name"])
                edit_min = st.number_input("최소재고", min_value=0, step=1, value=int(selected_item["min_stock"]))
                edit_target = st.number_input("적정재고", min_value=0, step=1, value=int(selected_item["target_stock"]))
                edit_active = st.checkbox("사용 중", value=bool(selected_item["is_active"]))

                edit_submit = st.form_submit_button("💾 수정 저장")

            if edit_submit:
                if not edit_name.strip():
                    st.warning("품목명을 입력하세요.")
                elif edit_target < edit_min:
                    st.warning("적정재고는 최소재고보다 크거나 같아야 합니다.")
                else:
                    update_item(
                        selected_id,
                        edit_warehouse,
                        edit_name.strip(),
                        edit_min,
                        edit_target,
                        edit_active
                    )
                    st.success("품목 정보가 수정되었습니다.")
                    st.rerun()

    with tab3:
        st.subheader("품목 삭제")
        st.warning("삭제하면 해당 품목과 재고조사 이력이 함께 삭제됩니다.")

        items = get_items(active_only=False)

        if items.empty:
            st.info("등록된 품목이 없습니다.")
        else:
            view = items.copy()
            view["사용여부"] = view["is_active"].map({1: "사용", 0: "미사용"})

            st.dataframe(
                view[["id", "warehouse", "item_name", "min_stock", "target_stock", "사용여부"]].rename(columns={
                    "id": "ID",
                    "warehouse": "창고",
                    "item_name": "품목명",
                    "min_stock": "최소재고",
                    "target_stock": "적정재고"
                }),
                use_container_width=True,
                hide_index=True
            )

            options = items["id"].astype(str) + " | " + items["warehouse"] + " | " + items["item_name"]
            selected = st.selectbox("삭제할 품목 선택", options)

            selected_id = int(selected.split(" | ")[0])
            selected_item = items[items["id"] == selected_id].iloc[0]

            st.write(f"삭제 대상: **{selected_item['warehouse']} / {selected_item['item_name']}**")

            confirm = st.checkbox("위 품목과 조사이력을 모두 삭제하는 것에 동의합니다.")

            if st.button("🗑️ 선택 품목 삭제", type="primary"):
                if not confirm:
                    st.warning("삭제 동의 체크 후 다시 눌러주세요.")
                else:
                    delete_item(selected_id)
                    st.success("품목과 조사이력이 삭제되었습니다.")
                    st.rerun()


elif menu == "🕒 조사이력":
    st.header("🕒 조사이력")

    records = get_records()

    if records.empty:
        st.info("조사 이력이 없습니다.")
        st.stop()

    active_items = get_items(active_only=True)

    if not active_items.empty:
        active_ids = active_items["id"].tolist()
        records = records[records["item_id"].isin(active_ids)]

    warehouse_filter = st.selectbox("창고 선택", ["전체", "1창고", "2창고"])

    if warehouse_filter != "전체":
        records = records[records["warehouse"] == warehouse_filter]

    if records.empty:
        st.info("표시할 조사 이력이 없습니다.")
        st.stop()

    view = records[[
        "check_time",
        "checker",
        "warehouse",
        "item_name",
        "current_stock",
        "min_stock",
        "target_stock",
        "purchase_qty"
    ]].rename(columns={
        "check_time": "조사일시",
        "checker": "입력자",
        "warehouse": "창고",
        "item_name": "품목명",
        "current_stock": "현재재고",
        "min_stock": "최소재고",
        "target_stock": "적정재고",
        "purchase_qty": "구매 필요량"
    })

    st.dataframe(view, use_container_width=True, hide_index=True)

    st.download_button(
        "📥 조사이력 엑셀 다운로드",
        data=to_excel(view),
        file_name="안전창고_조사이력.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )