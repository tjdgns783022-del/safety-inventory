import streamlit as st
import pandas as pd
import sqlite3
from datetime import datetime
from io import BytesIO

DB_PATH = "database/inventory.db"

st.set_page_config(
    page_title="빙그레 남양주공장 안전창고 재고관리 시스템",
    page_icon="📦",
    layout="wide"
)

def db():
    return sqlite3.connect(DB_PATH, check_same_thread=False)

def init_db():
    conn = db()
    cur = conn.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS items (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        warehouse TEXT NOT NULL,
        item_name TEXT NOT NULL,
        min_stock INTEGER NOT NULL,
        target_stock INTEGER NOT NULL,
        is_active INTEGER DEFAULT 1
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS records (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        check_time TEXT,
        checker TEXT,
        warehouse TEXT,
        item_name TEXT,
        current_stock INTEGER,
        min_stock INTEGER,
        target_stock INTEGER,
        purchase_qty INTEGER,
        status TEXT
    )
    """)

    cur.execute("SELECT COUNT(*) FROM items")
    if cur.fetchone()[0] == 0:
        sample = [
            ("1창고", "안전장갑", 20, 50),
            ("1창고", "보안경", 10, 30),
            ("1창고", "귀마개", 50, 100),
            ("2창고", "안전모", 5, 15),
            ("2창고", "안전화", 5, 20),
            ("2창고", "보호복", 20, 50),
        ]
        cur.executemany("""
        INSERT INTO items (warehouse, item_name, min_stock, target_stock)
        VALUES (?, ?, ?, ?)
        """, sample)

    conn.commit()
    conn.close()

def get_items(active_only=True):
    conn = db()
    query = "SELECT * FROM items"
    if active_only:
        query += " WHERE is_active = 1"
    query += " ORDER BY warehouse, item_name"
    df = pd.read_sql(query, conn)
    conn.close()
    return df

def calc_status(current, min_stock, target_stock):
    if current < min_stock:
        qty = target_stock - current
        return qty, f"{qty}개 구매 필요"
    return 0, "구매 불필요"

def excel_download(df):
    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Sheet1")
    return output.getvalue()

init_db()

st.title("📦 빙그레 남양주공장 안전창고 재고관리 시스템")

menu = st.sidebar.radio(
    "메뉴",
    ["재고조사", "재고조회", "구매필요목록", "품목관리", "조사이력"]
)

checker = st.sidebar.text_input("입력자 이름")

# ===================== 재고조사 =====================
if menu == "재고조사":
    st.header("📋 재고조사")

    if not checker:
        st.warning("왼쪽에 입력자 이름을 입력하세요.")
        st.stop()

    warehouse = st.selectbox("창고 선택", ["1창고", "2창고"])
    items = get_items()
    items = items[items["warehouse"] == warehouse]

    if items.empty:
        st.info("등록된 품목이 없습니다.")
        st.stop()

    records = []

    with st.form("stock_form"):
        for _, row in items.iterrows():
            st.subheader(row["item_name"])

            col1, col2, col3 = st.columns(3)

            with col1:
                st.write(f"최소재고: {row['min_stock']}")

            with col2:
                st.write(f"적정재고: {row['target_stock']}")

            with col3:
                current = st.number_input(
                    "현재재고",
                    min_value=0,
                    step=1,
                    key=f"stock_{row['id']}"
                )

            purchase_qty, status = calc_status(
                current,
                row["min_stock"],
                row["target_stock"]
            )

            st.write(f"상태: **{status}**")
            st.divider()

            records.append((
                checker,
                warehouse,
                row["item_name"],
                current,
                row["min_stock"],
                row["target_stock"],
                purchase_qty,
                status
            ))

        save = st.form_submit_button("재고조사 저장")

    if save:
        conn = db()
        cur = conn.cursor()
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        for r in records:
            cur.execute("""
            INSERT INTO records
            (check_time, checker, warehouse, item_name, current_stock,
             min_stock, target_stock, purchase_qty, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (now, *r))

        conn.commit()
        conn.close()
        st.success("재고조사가 저장되었습니다.")

# ===================== 재고조회 =====================
elif menu == "재고조회":
    st.header("📊 재고조회")

    conn = db()
    df = pd.read_sql("SELECT * FROM records ORDER BY check_time DESC", conn)
    conn.close()

    if df.empty:
        st.info("저장된 재고조사 이력이 없습니다.")
    else:
        latest = df.sort_values("check_time").groupby(
            ["warehouse", "item_name"], as_index=False
        ).tail(1)

        warehouse = st.selectbox("창고 필터", ["전체", "1창고", "2창고"])
        if warehouse != "전체":
            latest = latest[latest["warehouse"] == warehouse]

        view = latest[[
            "check_time", "checker", "warehouse", "item_name",
            "current_stock", "min_stock", "target_stock", "status"
        ]]

        st.dataframe(view, use_container_width=True)

        st.download_button(
            "엑셀 다운로드",
            data=excel_download(view),
            file_name="안전창고_재고조회.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

# ===================== 구매필요목록 =====================
elif menu == "구매필요목록":
    st.header("🛒 구매필요목록")

    conn = db()
    df = pd.read_sql("SELECT * FROM records ORDER BY check_time DESC", conn)
    conn.close()

    if df.empty:
        st.info("저장된 재고조사 이력이 없습니다.")
    else:
        latest = df.sort_values("check_time").groupby(
            ["warehouse", "item_name"], as_index=False
        ).tail(1)

        need = latest[latest["purchase_qty"] > 0]

        if need.empty:
            st.success("구매가 필요한 품목이 없습니다.")
        else:
            view = need[[
                "warehouse", "item_name", "current_stock",
                "target_stock", "purchase_qty", "status"
            ]]

            st.dataframe(view, use_container_width=True)

            st.download_button(
                "구매필요목록 엑셀 다운로드",
                data=excel_download(view),
                file_name="안전창고_구매필요목록.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )

# ===================== 품목관리 =====================
elif menu == "품목관리":
    st.header("⚙ 품목관리")

    st.subheader("품목 추가")

    with st.form("add_item"):
        warehouse = st.selectbox("창고", ["1창고", "2창고"])
        item_name = st.text_input("품목명")
        min_stock = st.number_input("최소재고", min_value=0, step=1)
        target_stock = st.number_input("적정재고", min_value=0, step=1)

        add = st.form_submit_button("품목 추가")

    if add:
        if item_name.strip() == "":
            st.warning("품목명을 입력하세요.")
        else:
            conn = db()
            cur = conn.cursor()
            cur.execute("""
            INSERT INTO items (warehouse, item_name, min_stock, target_stock)
            VALUES (?, ?, ?, ?)
            """, (warehouse, item_name, min_stock, target_stock))
            conn.commit()
            conn.close()
            st.success("품목이 추가되었습니다.")

    st.divider()
    st.subheader("품목 수정 / 미사용 처리")

    items = get_items(active_only=False)

    if items.empty:
        st.info("등록된 품목이 없습니다.")
    else:
        selected = st.selectbox(
            "수정할 품목 선택",
            items["id"].astype(str) + " | " + items["warehouse"] + " | " + items["item_name"]
        )

        item_id = int(selected.split(" | ")[0])
        item = items[items["id"] == item_id].iloc[0]

        with st.form("edit_item"):
            edit_warehouse = st.selectbox(
                "창고 수정",
                ["1창고", "2창고"],
                index=0 if item["warehouse"] == "1창고" else 1
            )
            edit_name = st.text_input("품목명 수정", value=item["item_name"])
            edit_min = st.number_input("최소재고 수정", min_value=0, step=1, value=int(item["min_stock"]))
            edit_target = st.number_input("적정재고 수정", min_value=0, step=1, value=int(item["target_stock"]))
            active = st.checkbox("사용 중", value=bool(item["is_active"]))

            edit = st.form_submit_button("수정 저장")

        if edit:
            conn = db()
            cur = conn.cursor()
            cur.execute("""
            UPDATE items
            SET warehouse=?, item_name=?, min_stock=?, target_stock=?, is_active=?
            WHERE id=?
            """, (
                edit_warehouse,
                edit_name,
                edit_min,
                edit_target,
                1 if active else 0,
                item_id
            ))
            conn.commit()
            conn.close()
            st.success("품목 정보가 수정되었습니다.")

        st.divider()
        st.dataframe(items, use_container_width=True)

# ===================== 조사이력 =====================
elif menu == "조사이력":
    st.header("🕒 조사이력")

    conn = db()
    df = pd.read_sql("SELECT * FROM records ORDER BY check_time DESC", conn)
    conn.close()

    if df.empty:
        st.info("조사 이력이 없습니다.")
    else:
        st.dataframe(df, use_container_width=True)

        st.download_button(
            "조사이력 엑셀 다운로드",
            data=excel_download(df),
            file_name="안전창고_조사이력.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )