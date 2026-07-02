import os
import sqlite3
from datetime import datetime
from io import BytesIO

import pandas as pd
import streamlit as st


APP_TITLE = "📦 안전창고 재고관리 V4.0"
DB_PATH = "database/inventory_v4.db"


st.set_page_config(
    page_title="안전창고 재고관리 V4.0",
    page_icon="📦",
    layout="wide"
)


# =========================
# 기본 함수
# =========================
def make_dirs():
    os.makedirs("database", exist_ok=True)
    os.makedirs("excel", exist_ok=True)


def conn():
    make_dirs()
    return sqlite3.connect(DB_PATH, check_same_thread=False)


def now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def init_db():
    db = conn()
    cur = db.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS items (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        warehouse TEXT NOT NULL,
        item_name TEXT NOT NULL,
        min_stock INTEGER NOT NULL,
        target_stock INTEGER NOT NULL,
        is_active INTEGER DEFAULT 1,
        created_at TEXT,
        updated_at TEXT
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS records (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        check_time TEXT NOT NULL,
        checker TEXT NOT NULL,
        warehouse TEXT NOT NULL,
        item_id INTEGER NOT NULL,
        item_name TEXT NOT NULL,
        current_stock INTEGER NOT NULL,
        min_stock INTEGER NOT NULL,
        target_stock INTEGER NOT NULL,
        purchase_qty INTEGER NOT NULL
    )
    """)

    db.commit()
    db.close()


def get_items(active_only=True):
    db = conn()
    query = "SELECT * FROM items"
    if active_only:
        query += " WHERE is_active = 1"
    query += " ORDER BY warehouse, item_name, id"
    df = pd.read_sql(query, db)
    db.close()
    return df


def get_records():
    db = conn()
    df = pd.read_sql("SELECT * FROM records ORDER BY check_time DESC", db)
    db.close()
    return df


def calc_purchase_qty(current_stock, target_stock):
    return max(int(target_stock) - int(current_stock), 0)


def get_latest_stock():
    items = get_items(active_only=True)
    records = get_records()

    if items.empty:
        return pd.DataFrame()

    result = []

    for _, item in items.iterrows():
        item_id = int(item["id"])

        if records.empty:
            latest_record = pd.DataFrame()
        else:
            latest_record = records[records["item_id"] == item_id]

        if latest_record.empty:
            current_stock = 0
            check_time = ""
            checker = ""
        else:
            last = latest_record.sort_values("check_time").tail(1).iloc[0]
            current_stock = int(last["current_stock"])
            check_time = last["check_time"]
            checker = last["checker"]

        purchase_qty = calc_purchase_qty(current_stock, int(item["target_stock"]))

        result.append({
            "최종수정일": check_time,
            "입력자": checker,
            "창고": item["warehouse"],
            "품목ID": item_id,
            "품목명": item["item_name"],
            "현재재고": current_stock,
            "최소재고": int(item["min_stock"]),
            "적정재고": int(item["target_stock"]),
            "구매 필요량": purchase_qty
        })

    return pd.DataFrame(result).sort_values(["창고", "품목명"])


def to_excel(df):
    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Sheet1")
    return output.getvalue()


def add_item(warehouse, item_name, min_stock, target_stock):
    db = conn()
    cur = db.cursor()
    cur.execute("""
    INSERT INTO items
    (warehouse, item_name, min_stock, target_stock, is_active, created_at, updated_at)
    VALUES (?, ?, ?, ?, 1, ?, ?)
    """, (
        warehouse,
        item_name,
        int(min_stock),
        int(target_stock),
        now(),
        now()
    ))
    db.commit()
    db.close()


def update_item(item_id, warehouse, item_name, min_stock, target_stock, is_active):
    db = conn()
    cur = db.cursor()
    cur.execute("""
    UPDATE items
    SET warehouse = ?,
        item_name = ?,
        min_stock = ?,
        target_stock = ?,
        is_active = ?,
        updated_at = ?
    WHERE id = ?
    """, (
        warehouse,
        item_name,
        int(min_stock),
        int(target_stock),
        1 if is_active else 0,
        now(),
        int(item_id)
    ))
    db.commit()
    db.close()


def delete_item(item_id):
    db = conn()
    cur = db.cursor()
    cur.execute("DELETE FROM records WHERE item_id = ?", (int(item_id),))
    cur.execute("DELETE FROM items WHERE id = ?", (int(item_id),))
    db.commit()
    db.close()


def save_stock(checker, warehouse, rows):
    db = conn()
    cur = db.cursor()
    check_time = now()

    for r in rows:
        cur.execute("""
        INSERT INTO records
        (check_time, checker, warehouse, item_id, item_name,
         current_stock, min_stock, target_stock, purchase_qty)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            check_time,
            checker,
            warehouse,
            int(r["item_id"]),
            r["item_name"],
            int(r["current_stock"]),
            int(r["min_stock"]),
            int(r["target_stock"]),
            int(r["purchase_qty"])
        ))

    db.commit()
    db.close()


# =========================
# 실행 시작
# =========================
init_db()

st.title(APP_TITLE)
st.caption("1창고, 2창고 안전창고 재고 확인 및 구매 필요량 관리용")

menu = st.sidebar.radio(
    "메뉴 선택",
    ["📦 재고조사", "📋 재고현황", "🛒 구매필요목록", "⚙ 품목관리", "🕒 조사이력"]
)

checker = st.sidebar.text_input("입력자 이름", placeholder="예: 홍길동")

st.divider()


# =========================
# 재고조사
# =========================
if menu == "📦 재고조사":
    st.header("📦 재고조사")

    if not checker.strip():
        st.warning("왼쪽 사이드바에 입력자 이름을 입력하세요.")
        st.stop()

    warehouse = st.selectbox("창고 선택", ["1창고", "2창고"])

    items = get_items(active_only=True)
    items = items[items["warehouse"] == warehouse]

    if items.empty:
        st.info("등록된 품목이 없습니다. 품목관리에서 품목을 추가하세요.")
        st.stop()

    latest = get_latest_stock()

    st.info("현재재고를 입력하면 구매 필요량이 자동 계산됩니다. 저장 후 다음 접속 시 마지막 재고가 그대로 표시됩니다.")

    save_rows = []

    with st.form("stock_form"):
        for _, item in items.iterrows():
            item_id = int(item["id"])

            matched = latest[latest["품목ID"] == item_id] if not latest.empty else pd.DataFrame()

            if matched.empty:
                default_stock = 0
            else:
                default_stock = int(matched.iloc[0]["현재재고"])

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

            purchase_qty = calc_purchase_qty(current_stock, int(item["target_stock"]))
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


# =========================
# 재고현황
# =========================
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


# =========================
# 구매필요목록
# =========================
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


# =========================
# 품목관리
# =========================
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
                duplicated = items[
                    (items["warehouse"] == warehouse) &
                    (items["item_name"] == item_name)
                ]

                if not duplicated.empty:
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


# =========================
# 조사이력
# =========================
elif menu == "🕒 조사이력":
    st.header("🕒 조사이력")

    records = get_records()

    if records.empty:
        st.info("조사 이력이 없습니다.")
        st.stop()

    items = get_items(active_only=True)

    if not items.empty:
        active_ids = items["id"].tolist()
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