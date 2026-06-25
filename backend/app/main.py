from fastapi import FastAPI, HTTPException, Depends, Header, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel
from typing import Optional
from datetime import datetime, timedelta
import os
import sqlite3
import secrets
from urllib.parse import urlencode

try:
    import httpx
    _HTTPX = True
except ImportError:
    _HTTPX = False

DB_PATH  = os.path.join(os.path.dirname(__file__), "../../dental_lab.db")
FRONTEND = os.path.join(os.path.dirname(__file__), "../../frontend/index.html")

# ── Alfa Bank config ──────────────────────────────────────────────────────────
ALFA_CERT_PEM     = os.environ.get("ALFA_CERT_PEM", "")
ALFA_CERT_KEY     = os.environ.get("ALFA_CERT_KEY", "")
ALFA_API_BASE     = "https://sandbox.alfabank.ru/api"

app = FastAPI(title="Dental Lab API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS technicians (
        id   TEXT PRIMARY KEY,
        pin  TEXT NOT NULL,
        name TEXT NOT NULL,
        city TEXT NOT NULL,
        role TEXT DEFAULT 'technician'
    );
    CREATE TABLE IF NOT EXISTS orders (
        id                   TEXT PRIMARY KEY,
        patient_name         TEXT NOT NULL,
        clinic_name          TEXT NOT NULL,
        doctor_name          TEXT NOT NULL,
        work_type            TEXT NOT NULL,
        units                INTEGER NOT NULL DEFAULT 1,
        teeth                TEXT NOT NULL,
        description          TEXT DEFAULT '',
        technician_id        TEXT,
        technician_name      TEXT,
        status               TEXT DEFAULT 'новый',
        priority             TEXT DEFAULT 'средний',
        created_at           TEXT NOT NULL,
        deadline             TEXT NOT NULL,
        appointment_at       TEXT,
        tooth_color          TEXT DEFAULT '',
        preferred_technician TEXT DEFAULT '',
        total                REAL DEFAULT 0,
        payment_status       TEXT DEFAULT ''
    );
    CREATE TABLE IF NOT EXISTS order_items (
        id           INTEGER PRIMARY KEY AUTOINCREMENT,
        order_id     TEXT NOT NULL,
        article      TEXT DEFAULT '',
        name         TEXT NOT NULL,
        qty          INTEGER DEFAULT 1,
        price        REAL DEFAULT 0,
        total        REAL DEFAULT 0,
        is_delivered INTEGER DEFAULT 0,
        act_issued   INTEGER DEFAULT 0
    );
    CREATE TABLE IF NOT EXISTS order_stages (
        id             INTEGER PRIMARY KEY AUTOINCREMENT,
        order_id       TEXT NOT NULL,
        n              INTEGER NOT NULL,
        article        TEXT DEFAULT '',
        operation      TEXT NOT NULL,
        qty            INTEGER DEFAULT 1,
        technician     TEXT NOT NULL,
        transferred_at TEXT,
        accepted_at    TEXT,
        planned_date   TEXT,
        actual_date    TEXT,
        defect_comment TEXT DEFAULT '',
        amount         REAL DEFAULT 0,
        stage_type     TEXT DEFAULT ''
    );
    CREATE TABLE IF NOT EXISTS technician_rates (
        id            INTEGER PRIMARY KEY AUTOINCREMENT,
        technician_id TEXT NOT NULL,
        stage_type    TEXT NOT NULL,
        rate          REAL DEFAULT 0,
        UNIQUE(technician_id, stage_type)
    );
    CREATE TABLE IF NOT EXISTS comments (
        id         INTEGER PRIMARY KEY AUTOINCREMENT,
        order_id   TEXT NOT NULL,
        author     TEXT NOT NULL,
        text       TEXT NOT NULL,
        created_at TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS messages (
        id        TEXT PRIMARY KEY,
        order_id  TEXT NOT NULL,
        from_name TEXT NOT NULL,
        text      TEXT NOT NULL,
        time      TEXT NOT NULL,
        has_photo INTEGER DEFAULT 0
    );
    CREATE TABLE IF NOT EXISTS nomenclature (
        id      INTEGER PRIMARY KEY AUTOINCREMENT,
        article TEXT NOT NULL,
        name    TEXT NOT NULL,
        price   REAL DEFAULT 0,
        unit    TEXT DEFAULT 'шт'
    );
    CREATE TABLE IF NOT EXISTS clinic_prices (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        clinic_id       TEXT NOT NULL,
        nomenclature_id INTEGER NOT NULL,
        price           REAL DEFAULT 0,
        UNIQUE(clinic_id, nomenclature_id)
    );
    CREATE TABLE IF NOT EXISTS acts (
        id           INTEGER PRIMARY KEY AUTOINCREMENT,
        act_number   TEXT NOT NULL UNIQUE,
        order_id     TEXT NOT NULL,
        clinic_name  TEXT NOT NULL,
        doctor_name  TEXT NOT NULL,
        patient_name TEXT NOT NULL,
        created_at   TEXT NOT NULL,
        created_by   TEXT NOT NULL,
        total        REAL DEFAULT 0,
        discount     REAL DEFAULT 0,
        final_total  REAL DEFAULT 0
    );
    CREATE TABLE IF NOT EXISTS act_items (
        id      INTEGER PRIMARY KEY AUTOINCREMENT,
        act_id  INTEGER NOT NULL,
        article TEXT DEFAULT '',
        name    TEXT NOT NULL,
        qty     INTEGER DEFAULT 1,
        price   REAL DEFAULT 0,
        total   REAL DEFAULT 0
    );
    CREATE TABLE IF NOT EXISTS alfa_tokens (
        id            INTEGER PRIMARY KEY CHECK (id = 1),
        access_token  TEXT,
        refresh_token TEXT,
        expires_at    TEXT,
        updated_at    TEXT
    );
    CREATE TABLE IF NOT EXISTS alfa_webhooks (
        id            INTEGER PRIMARY KEY AUTOINCREMENT,
        received_at   TEXT DEFAULT (datetime('now')),
        event_type    TEXT DEFAULT '',
        amount        REAL DEFAULT 0,
        currency      TEXT DEFAULT 'RUB',
        operation_date TEXT DEFAULT '',
        counterparty  TEXT DEFAULT '',
        inn           TEXT DEFAULT '',
        purpose       TEXT DEFAULT '',
        account       TEXT DEFAULT '',
        raw_json      TEXT DEFAULT ''
    );
    CREATE TABLE IF NOT EXISTS clinics (
        id           TEXT PRIMARY KEY,
        name         TEXT NOT NULL UNIQUE,
        phone        TEXT DEFAULT '',
        contact_name TEXT DEFAULT '',
        city         TEXT DEFAULT '',
        notes        TEXT DEFAULT ''
    );
    """)

    # Migration: add new columns to existing orders table if absent
    c = conn.cursor()
    for col_sql in [
        "ALTER TABLE orders ADD COLUMN tooth_color TEXT DEFAULT ''",
        "ALTER TABLE orders ADD COLUMN preferred_technician TEXT DEFAULT ''",
        "ALTER TABLE orders ADD COLUMN total REAL DEFAULT 0",
        "ALTER TABLE orders ADD COLUMN payment_status TEXT DEFAULT ''",
        "ALTER TABLE orders ADD COLUMN discount REAL DEFAULT 0",
        "ALTER TABLE orders ADD COLUMN ceramist TEXT DEFAULT ''",
        "ALTER TABLE orders ADD COLUMN modeler TEXT DEFAULT ''",
        "ALTER TABLE orders ADD COLUMN implant_system TEXT DEFAULT ''",
        "ALTER TABLE technicians ADD COLUMN specialization TEXT DEFAULT ''",
        "ALTER TABLE technicians ADD COLUMN load_percent REAL DEFAULT 0",
        "ALTER TABLE order_stages ADD COLUMN stage_type TEXT DEFAULT ''",
        "ALTER TABLE order_items ADD COLUMN act_issued INTEGER DEFAULT 0",
    ]:
        try:
            c.execute(col_sql)
            if col_sql.startswith("ALTER TABLE technicians ADD COLUMN specialization"):
                # Первичная расстановка направлений — только при первом создании
                # колонки, чтобы не затирать ручные правки из экрана «Техники»
                # при каждом перезапуске сервера.
                c.execute("UPDATE technicians SET specialization='technician' WHERE name IN ('Мурад','Ильяс')")
                c.execute("UPDATE technicians SET specialization='modeler' WHERE name IN ('Магомед','Асадуллах')")
        except Exception:
            pass

    # Если % нагрузки внутри направления ещё не выставлен вручную — распределить поровну
    for spec in ('technician', 'modeler'):
        rows = c.execute(
            "SELECT id FROM technicians WHERE specialization=? AND role != 'admin'", (spec,)
        ).fetchall()
        already_set = c.execute(
            "SELECT 1 FROM technicians WHERE specialization=? AND role != 'admin' AND load_percent>0", (spec,)
        ).fetchone()
        if rows and not already_set:
            even_share = round(100 / len(rows), 2)
            for row in rows:
                c.execute("UPDATE technicians SET load_percent=? WHERE id=?", (even_share, row[0]))

    if not c.execute("SELECT COUNT(*) FROM technicians").fetchone()[0]:
        c.executemany("INSERT INTO technicians VALUES (?,?,?,?,?)", [
            ("T001", "1111", "Петров Михаил",   "Москва", "technician"),
            ("T002", "2222", "Иванов Сергей",    "Москва", "technician"),
            ("T003", "3333", "Козлова Татьяна",  "Москва", "technician"),
            ("ADMIN","0000", "Руководитель",      "Москва", "admin"),
        ])

    # Добавить Ильяс и Али если ещё нет
    for t_id, pin, name in [("T004","4444","Ильяс"), ("T005","5555","Али")]:
        if not c.execute("SELECT 1 FROM technicians WHERE id=?", (t_id,)).fetchone():
            c.execute("INSERT INTO technicians VALUES (?,?,?,?,?)", (t_id, pin, name, "Москва", "technician"))

    if not c.execute("SELECT COUNT(*) FROM orders").fetchone()[0]:
        c.executemany(
            "INSERT INTO orders VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            [
                ("ЗЛ-000101","Захаров В.Н.","Дентал Плюс","Соколов К.Д.","Металлокерамика",4,"14, 15, 16, 17","Цвет A2, ориентир на соседние зубы","T001","Петров Михаил","в_работе","высокий","2026-05-18T10:00:00","2026-07-01T18:00:00","2026-07-01T19:30:00","A2","Петров Михаил",0,""),
                ("ЗЛ-000102","Смирнова А.К.","Улыбка","Попов Д.А.","Циркониевая коронка",1,"36","Стандартный цвет B1","T001","Петров Михаил","новый","высокий","2026-05-17T09:00:00","2026-06-10T18:00:00","2026-06-12T10:00:00","B1","Петров Михаил",0,""),
                ("ЗЛ-000103","Новикова Е.П.","Дентал Плюс","Соколов К.Д.","Металлокерамика",3,"24, 25, 26","Цвет A2, особое внимание к окклюзии","T001","Петров Михаил","в_работе","средний","2026-05-18T11:00:00","2026-06-15T14:00:00","2026-06-16T11:00:00","A2","Петров Михаил",0,""),
                ("ЗЛ-000104","Козлов И.В.","МедСтом","Кузнецов А.П.","Имплант-коронка циркониевая",1,"46","Цвет C2","T001","Петров Михаил","новый","низкий","2026-05-19T08:00:00","2026-06-20T18:00:00","2026-06-22T12:00:00","C2","Петров Михаил",0,""),
                ("ЗЛ-000105","Морозов Д.С.","Улыбка","Попов Д.А.","Съёмный протез",1,"Верхняя челюсть","Полный съёмный, акрил розовый","T002","Иванов Сергей","в_работе","средний","2026-05-17T14:00:00","2026-06-12T12:00:00","2026-06-13T14:00:00","","Иванов Сергей",0,""),
            ]
        )
        c.executemany("INSERT INTO messages VALUES (?,?,?,?,?,?)", [
            ("m1","ЗЛ-000101","Соколов К.Д.","Цвет уточнил — ориентируйтесь на зуб 13, не на шкалу","2026-05-19T09:14:00",1),
            ("m2","ЗЛ-000103","Соколов К.Д.","Прикус изменился после слепка, учтите при окклюзии","2026-05-19T17:42:00",0),
        ])

    # Добавить заказ Курбановой если ещё нет
    if not c.execute("SELECT 1 FROM orders WHERE id='ЗЛ-000107'").fetchone():
        c.execute(
            "INSERT INTO orders VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            ("ЗЛ-000107","Курбанова Г","Доктор-Сен","Курбанов С",
             "Имплант-коронка + модель диагностическая",1,"36",
             "Цвет A2. Прайс: Доктор-Сен (2025). Скидка не предоставляется.",
             "T004","Ильяс","в_работе","высокий",
             "2026-06-03T20:12:56","2026-06-10T00:00:00","2026-06-10T00:00:00",
             "A2","Ильяс",10500.0,"Не выставлено")
        )
        c.executemany(
            "INSERT INTO order_items (order_id,article,name,qty,price,total,is_delivered) VALUES (?,?,?,?,?,?,?)",
            [
                ("ЗЛ-000107","2016","Модель диагностическая (3D)",2,1000.0,2000.0,1),
                ("ЗЛ-000107","0056","ЦК ПА на имп. винт/ф.",1,8500.0,8500.0,0),
            ]
        )
        c.executemany(
            "INSERT INTO order_stages (order_id,n,article,operation,qty,technician,transferred_at,accepted_at,planned_date,actual_date) VALUES (?,?,?,?,?,?,?,?,?,?)",
            [
                ("ЗЛ-000107",1,"0000000014","Моделирование — 3D модель диагностическая",2,"Ильяс",
                 "2026-06-08T13:22:13","2026-06-08T13:22:13","2026-06-08T18:00:00","2026-06-08T16:40:00"),
                ("ЗЛ-000107",2,"0000000001","Гипсовка",1,"Али",
                 "2026-06-08T13:22:13","2026-06-08T13:22:13","2026-06-09T12:00:00",None),
                ("ЗЛ-000107",3,"0000000002","Гравировка",1,"Ильяс",
                 None,None,"2026-06-09T18:00:00",None),
            ]
        )

    # Seed номенклатура
    if not c.execute("SELECT COUNT(*) FROM nomenclature").fetchone()[0]:
        c.executemany(
            "INSERT INTO nomenclature (article,name,price,unit) VALUES (?,?,?,?)",
            [
                ("0001","Металлокерамическая коронка",5000.0,"шт"),
                ("0002","Циркониевая коронка (безметалловая)",8000.0,"шт"),
                ("0003","Акриловая коронка временная",1500.0,"шт"),
                ("0004","Металлическая коронка",2500.0,"шт"),
                ("0005","Имплант-коронка циркониевая",10000.0,"шт"),
                ("0006","Имплант-коронка металлокерамика",7500.0,"шт"),
                ("0007","Виниры керамические",9000.0,"шт"),
                ("0008","Съёмный протез полный (акрил)",15000.0,"шт"),
                ("0009","Съёмный протез частичный (нейлон)",12000.0,"шт"),
                ("0010","Бюгельный протез",18000.0,"шт"),
                ("0011","Вкладка керамическая",6000.0,"шт"),
                ("0012","Штифтовая конструкция",3000.0,"шт"),
                ("0013","Каппа ночная",3500.0,"шт"),
                ("0014","Каппа для отбеливания",2000.0,"шт"),
                ("0015","Ретейнер",2500.0,"шт"),
                ("0016","Диагностическая модель (гипс)",800.0,"шт"),
                ("0017","Восковая репродукция",1200.0,"шт"),
                ("0018","Временная коронка (пластмасса)",1000.0,"шт"),
                ("0019","Абатмент индивидуальный (CAD/CAM)",12000.0,"шт"),
                ("0020","Телескопическая коронка",15000.0,"шт"),
                ("2016","Модель диагностическая (3D)",1000.0,"шт"),
                ("0056","ЦК ПА на имп. винт/ф.",8500.0,"шт"),
            ]
        )

    # Seed clinics from existing orders if table is empty
    if not c.execute("SELECT COUNT(*) FROM clinics").fetchone()[0]:
        existing = c.execute("SELECT DISTINCT clinic_name FROM orders WHERE clinic_name != ''").fetchall()
        for row in existing:
            c.execute(
                "INSERT OR IGNORE INTO clinics (id, name) VALUES (?, ?)",
                (secrets.token_hex(6), row[0])
            )

    conn.commit()
    conn.close()


init_db()


def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


def _fetch_order(conn, order_id):
    row = conn.execute("SELECT * FROM orders WHERE id=?", (order_id,)).fetchone()
    if not row:
        return None
    comments = [dict(r) for r in conn.execute(
        "SELECT * FROM comments WHERE order_id=? ORDER BY id", (order_id,)).fetchall()]
    messages = [
        {"id": r["id"], "from": r["from_name"], "text": r["text"],
         "time": r["time"], "has_photo": bool(r["has_photo"])}
        for r in conn.execute(
            "SELECT * FROM messages WHERE order_id=? ORDER BY time", (order_id,)).fetchall()
    ]
    items = [dict(r) for r in conn.execute(
        "SELECT id,article,name,qty,price,total,is_delivered,act_issued FROM order_items WHERE order_id=? ORDER BY id",
        (order_id,)).fetchall()]
    for it in items:
        it["is_delivered"] = bool(it["is_delivered"])
        it["act_issued"] = bool(it["act_issued"])
    stages = [dict(r) for r in conn.execute(
        "SELECT id,n,article,operation,qty,technician,transferred_at,accepted_at,planned_date,actual_date,defect_comment,amount "
        "FROM order_stages WHERE order_id=? ORDER BY n",
        (order_id,)).fetchall()]
    d = dict(row)
    d["comments"] = comments
    d["messages"] = messages
    d["items"]    = items
    d["stages"]   = stages
    return d


def _fetch_orders(conn, technician_id=None):
    if technician_id:
        rows = conn.execute(
            "SELECT * FROM orders WHERE technician_id=? ORDER BY deadline", (technician_id,)).fetchall()
    else:
        rows = conn.execute("SELECT * FROM orders ORDER BY deadline").fetchall()
    return [_fetch_order(conn, r["id"]) for r in rows]


def get_tech(x_pin: str = Header(...)):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT * FROM technicians WHERE pin=?", (x_pin,)).fetchone()
    conn.close()
    if not row:
        raise HTTPException(status_code=401, detail="Неверный PIN")
    return dict(row)


# ── Models ──────────────────────────────────────────────────────────────────

class PinLogin(BaseModel):
    pin: str

class StatusUpdate(BaseModel):
    status: str

class DiscountUpdate(BaseModel):
    discount: float

class OrderItemAdd(BaseModel):
    nomenclature_id: int
    qty: int = 1

class OrderItemQty(BaseModel):
    qty: int

class StageAdd(BaseModel):
    operation:    str
    stage_type:   str
    technician_id: str
    qty:          int = 1
    planned_date: Optional[str] = None
    article:      str = ""

class TechnicianRateUpdate(BaseModel):
    technician_id: str
    stage_type: str
    rate: float

class CommentAdd(BaseModel):
    text: str

class ActCreate(BaseModel):
    order_id: str

class NomUpdate(BaseModel):
    price: float

class ClinicPriceUpdate(BaseModel):
    clinic_name: str
    nomenclature_id: int
    price: Optional[float] = None

class OrderCreate(BaseModel):
    patient_name:  str
    clinic_name:   str
    doctor_name:   str
    work_type:     str
    units:         int = 1
    teeth:         str
    description:   str = ""
    technician_id: str
    priority:      str = "средний"
    deadline:      str
    appointment_at: Optional[str] = None
    discount:      float = 0
    total:         float = 0
    tooth_color:    str = ""
    implant_system: str = ""

class AlfaKeySet(BaseModel):
    api_key: str

class ClinicCreate(BaseModel):
    name: str
    phone: str = ''
    contact_name: str = ''
    city: str = ''
    notes: str = ''

class OrderFieldUpdate(BaseModel):
    field: str
    value: str

class TechnicianUpdate(BaseModel):
    specialization: Optional[str] = None
    load_percent: Optional[float] = None


# ── Endpoints ────────────────────────────────────────────────────────────────

@app.get("/api")
def root():
    return {"status": "Dental Lab API работает", "version": "2.0"}

@app.get("/")
def serve_frontend():
    return FileResponse(FRONTEND)

@app.post("/auth/login")
def login(data: PinLogin):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    row = conn.execute("SELECT * FROM technicians WHERE pin=?", (data.pin,)).fetchone()
    conn.close()
    if not row:
        raise HTTPException(status_code=401, detail="Неверный PIN")
    return {"success": True, "technician": dict(row)}

@app.get("/orders")
def get_orders(technician_id: Optional[str] = None, tech=Depends(get_tech), conn=Depends(db)):
    if tech.get("role") == "admin":
        orders = _fetch_orders(conn, technician_id)
    else:
        orders = _fetch_orders(conn, tech["id"])
    return {"orders": orders, "total": len(orders)}

@app.get("/orders/{order_id}")
def get_order(order_id: str, tech=Depends(get_tech), conn=Depends(db)):
    order = _fetch_order(conn, order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Заказ не найден")
    return order

@app.post("/orders")
def create_order(data: OrderCreate, tech=Depends(get_tech), conn=Depends(db)):
    if tech.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Только для руководителя")
    tech_row = conn.execute("SELECT name FROM technicians WHERE id=?", (data.technician_id,)).fetchone()
    if not tech_row:
        raise HTTPException(status_code=400, detail="Техник не найден")
    count = conn.execute("SELECT COUNT(*) FROM orders").fetchone()[0]
    order_id = f"ЗЛ-{count + 101:06d}"
    now = datetime.now().isoformat()
    conn.execute(
        "INSERT INTO orders (id,patient_name,clinic_name,doctor_name,work_type,units,teeth,description,"
        "technician_id,technician_name,status,priority,created_at,deadline,appointment_at,"
        "tooth_color,preferred_technician,total,payment_status,discount,implant_system) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (order_id, data.patient_name, data.clinic_name, data.doctor_name,
         data.work_type, data.units, data.teeth, data.description,
         data.technician_id, tech_row["name"], "новый", data.priority,
         now, data.deadline, data.appointment_at,
         data.tooth_color, tech_row["name"], data.total, "", data.discount, data.implant_system)
    )
    modeler_name  = _pick_least_loaded(conn, 'technician', 'modeler',  order_id)
    ceramist_name = _pick_least_loaded(conn, 'modeler',    'ceramist', order_id)
    if modeler_name:
        conn.execute("UPDATE orders SET modeler=? WHERE id=?", (modeler_name, order_id))
    if ceramist_name:
        conn.execute("UPDATE orders SET ceramist=? WHERE id=?", (ceramist_name, order_id))
    conn.commit()
    return {"success": True, "order": _fetch_order(conn, order_id)}

EDITABLE_ORDER_FIELDS = {
    'patient_name', 'clinic_name', 'doctor_name', 'tooth_color',
    'ceramist', 'modeler', 'implant_system', 'appointment_at',
    'deadline', 'technician_name', 'work_type', 'teeth', 'description'
}

STAGE_TYPES = ['Гипсовка', 'Гравировка', 'Моделирование', 'Фрезировка', 'Покраска']

@app.patch("/orders/{order_id}/field")
def update_order_field(order_id: str, data: OrderFieldUpdate, tech=Depends(get_tech), conn=Depends(db)):
    if tech.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Только для руководителя")
    if data.field not in EDITABLE_ORDER_FIELDS:
        raise HTTPException(status_code=400, detail=f"Поле '{data.field}' нельзя редактировать")
    if not conn.execute("SELECT id FROM orders WHERE id=?", (order_id,)).fetchone():
        raise HTTPException(status_code=404, detail="Заказ не найден")
    conn.execute(f"UPDATE orders SET {data.field}=? WHERE id=?", (data.value, order_id))
    conn.commit()
    return {"success": True, "order": _fetch_order(conn, order_id)}

def _pick_least_loaded(conn, specialization, order_field, exclude_order_id):
    """Выбрать техника направления, чья текущая загрузка (Σ units заказов в статусе
    'в_работе') сильнее всего отстаёт от его целевой доли — заданной % нагрузки."""
    techs = conn.execute(
        "SELECT id, name, load_percent FROM technicians WHERE specialization=? AND role != 'admin'",
        (specialization,)
    ).fetchall()
    if not techs:
        return None
    loads = {}
    for t in techs:
        loads[t["name"]] = conn.execute(
            f"SELECT COALESCE(SUM(units),0) FROM orders WHERE status='в_работе' AND {order_field}=? AND id!=?",
            (t["name"], exclude_order_id)
        ).fetchone()[0]
    total_load = sum(loads.values())

    def deficit(t):
        target = total_load * (t["load_percent"] / 100) if total_load > 0 else t["load_percent"]
        return target - loads[t["name"]]

    best = max(techs, key=lambda t: (deficit(t), t["load_percent"]))
    return best["name"]

@app.post("/orders/{order_id}/auto-distribute")
def auto_distribute(order_id: str, tech=Depends(get_tech), conn=Depends(db)):
    if tech.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Только для руководителя")
    order = conn.execute("SELECT * FROM orders WHERE id=?", (order_id,)).fetchone()
    if not order:
        raise HTTPException(status_code=404, detail="Заказ не найден")
    modeler_name  = _pick_least_loaded(conn, 'technician', 'modeler',  order_id)
    ceramist_name = _pick_least_loaded(conn, 'modeler',    'ceramist', order_id)
    if modeler_name:
        conn.execute("UPDATE orders SET modeler=? WHERE id=?", (modeler_name, order_id))
    if ceramist_name:
        conn.execute("UPDATE orders SET ceramist=? WHERE id=?", (ceramist_name, order_id))
    conn.commit()
    return {"success": True, "order": _fetch_order(conn, order_id)}

@app.patch("/orders/{order_id}/status")
def update_status(order_id: str, data: StatusUpdate, tech=Depends(get_tech), conn=Depends(db)):
    if not conn.execute("SELECT id FROM orders WHERE id=?", (order_id,)).fetchone():
        raise HTTPException(status_code=404, detail="Заказ не найден")
    conn.execute("UPDATE orders SET status=? WHERE id=?", (data.status, order_id))
    conn.commit()
    return {"success": True, "order_id": order_id, "status": data.status}

@app.patch("/orders/{order_id}/discount")
def update_discount(order_id: str, data: DiscountUpdate, tech=Depends(get_tech), conn=Depends(db)):
    if tech.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Только для руководителя")
    if not conn.execute("SELECT id FROM orders WHERE id=?", (order_id,)).fetchone():
        raise HTTPException(status_code=404, detail="Заказ не найден")
    if not (0 <= data.discount <= 100):
        raise HTTPException(status_code=400, detail="Скидка должна быть от 0 до 100%")
    conn.execute("UPDATE orders SET discount=? WHERE id=?", (data.discount, order_id))
    conn.commit()
    return {"success": True, "order_id": order_id, "discount": data.discount}

@app.get("/nomenclature")
def get_nomenclature(clinic_name: Optional[str] = None, tech=Depends(get_tech), conn=Depends(db)):
    rows = conn.execute("SELECT * FROM nomenclature ORDER BY article").fetchall()
    items = [dict(r) for r in rows]
    if clinic_name:
        clinic = conn.execute("SELECT id FROM clinics WHERE name=?", (clinic_name,)).fetchone()
        overrides = {}
        if clinic:
            overrides = {
                r["nomenclature_id"]: r["price"] for r in conn.execute(
                    "SELECT nomenclature_id, price FROM clinic_prices WHERE clinic_id=?", (clinic["id"],)
                ).fetchall()
            }
        for it in items:
            if it["id"] in overrides:
                it["price"] = overrides[it["id"]]
                it["is_override"] = True
            else:
                it["is_override"] = False
    return {"items": items}

@app.get("/clinic-prices/clinics")
def get_clinics_with_prices(tech=Depends(get_tech), conn=Depends(db)):
    rows = conn.execute(
        "SELECT DISTINCT c.name FROM clinic_prices cp JOIN clinics c ON c.id = cp.clinic_id ORDER BY c.name"
    ).fetchall()
    return {"clinics": [r["name"] for r in rows]}

@app.get("/technician-rates")
def get_technician_rates(tech=Depends(get_tech), conn=Depends(db)):
    if tech.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Только для руководителя")
    techs = conn.execute("SELECT id, name FROM technicians WHERE role='technician' ORDER BY name").fetchall()
    rates = {
        (r["technician_id"], r["stage_type"]): r["rate"] for r in conn.execute(
            "SELECT technician_id, stage_type, rate FROM technician_rates"
        ).fetchall()
    }
    result = [
        {
            "technician_id": t["id"],
            "technician_name": t["name"],
            "rates": {st: rates.get((t["id"], st), 0) for st in STAGE_TYPES},
        }
        for t in techs
    ]
    return {"technicians": result, "stage_types": STAGE_TYPES}

@app.patch("/technician-rates")
def set_technician_rate(data: TechnicianRateUpdate, tech=Depends(get_tech), conn=Depends(db)):
    if tech.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Только для руководителя")
    if data.stage_type not in STAGE_TYPES:
        raise HTTPException(status_code=400, detail=f"Тип этапа должен быть одним из: {', '.join(STAGE_TYPES)}")
    if data.rate < 0:
        raise HTTPException(status_code=400, detail="Ставка не может быть отрицательной")
    if not conn.execute("SELECT id FROM technicians WHERE id=?", (data.technician_id,)).fetchone():
        raise HTTPException(status_code=404, detail="Техник не найден")
    conn.execute(
        "INSERT INTO technician_rates (technician_id, stage_type, rate) VALUES (?,?,?) "
        "ON CONFLICT(technician_id, stage_type) DO UPDATE SET rate=excluded.rate",
        (data.technician_id, data.stage_type, data.rate)
    )
    conn.commit()
    return {"success": True}

@app.get("/reports/salary")
def get_salary_report(month: str, tech=Depends(get_tech), conn=Depends(db)):
    if tech.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Только для руководителя")
    rows = conn.execute(
        "SELECT technician, stage_type, qty, amount FROM order_stages "
        "WHERE actual_date IS NOT NULL AND substr(actual_date,1,7)=?",
        (month,)
    ).fetchall()
    by_tech = {}
    for r in rows:
        t = by_tech.setdefault(r["technician"], {"technician": r["technician"], "total": 0, "by_stage": {}})
        t["total"] += r["amount"]
        st = r["stage_type"] or "—"
        stage_entry = t["by_stage"].setdefault(st, {"qty": 0, "amount": 0})
        stage_entry["qty"] += r["qty"]
        stage_entry["amount"] += r["amount"]
    result = sorted(by_tech.values(), key=lambda x: -x["total"])
    return {"month": month, "technicians": result}

@app.patch("/clinic-prices")
def set_clinic_price(data: ClinicPriceUpdate, tech=Depends(get_tech), conn=Depends(db)):
    if tech.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Только для руководителя")
    if not conn.execute("SELECT id FROM nomenclature WHERE id=?", (data.nomenclature_id,)).fetchone():
        raise HTTPException(status_code=404, detail="Позиция номенклатуры не найдена")
    clinic = conn.execute("SELECT id FROM clinics WHERE name=?", (data.clinic_name,)).fetchone()
    if not clinic:
        raise HTTPException(status_code=404, detail="Клиника не найдена")
    if data.price is None:
        conn.execute(
            "DELETE FROM clinic_prices WHERE clinic_id=? AND nomenclature_id=?",
            (clinic["id"], data.nomenclature_id)
        )
    else:
        if data.price < 0:
            raise HTTPException(status_code=400, detail="Цена не может быть отрицательной")
        conn.execute(
            "INSERT INTO clinic_prices (clinic_id, nomenclature_id, price) VALUES (?,?,?) "
            "ON CONFLICT(clinic_id, nomenclature_id) DO UPDATE SET price=excluded.price",
            (clinic["id"], data.nomenclature_id, data.price)
        )
    conn.commit()
    return {"success": True}

@app.post("/orders/{order_id}/items")
def add_order_item(order_id: str, data: OrderItemAdd, tech=Depends(get_tech), conn=Depends(db)):
    if tech.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Только для руководителя")
    if not conn.execute("SELECT id FROM orders WHERE id=?", (order_id,)).fetchone():
        raise HTTPException(status_code=404, detail="Заказ не найден")
    nom = conn.execute("SELECT * FROM nomenclature WHERE id=?", (data.nomenclature_id,)).fetchone()
    if not nom:
        raise HTTPException(status_code=404, detail="Позиция номенклатуры не найдена")
    total = nom["price"] * data.qty
    conn.execute(
        "INSERT INTO order_items (order_id,article,name,qty,price,total,is_delivered) VALUES (?,?,?,?,?,?,0)",
        (order_id, nom["article"], nom["name"], data.qty, nom["price"], total)
    )
    new_total = conn.execute(
        "SELECT COALESCE(SUM(total),0) FROM order_items WHERE order_id=?", (order_id,)
    ).fetchone()[0]
    conn.execute("UPDATE orders SET total=? WHERE id=?", (new_total, order_id))
    conn.commit()
    return {"success": True, "order": _fetch_order(conn, order_id)}

@app.delete("/orders/{order_id}/items/{item_id}")
def delete_order_item(order_id: str, item_id: int, tech=Depends(get_tech), conn=Depends(db)):
    if tech.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Только для руководителя")
    conn.execute("DELETE FROM order_items WHERE id=? AND order_id=?", (item_id, order_id))
    new_total = conn.execute(
        "SELECT COALESCE(SUM(total),0) FROM order_items WHERE order_id=?", (order_id,)
    ).fetchone()[0]
    conn.execute("UPDATE orders SET total=? WHERE id=?", (new_total, order_id))
    conn.commit()
    return {"success": True, "order": _fetch_order(conn, order_id)}

@app.patch("/orders/{order_id}/items/{item_id}/qty")
def update_item_qty(order_id: str, item_id: int, data: OrderItemQty, tech=Depends(get_tech), conn=Depends(db)):
    if tech.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Только для руководителя")
    row = conn.execute("SELECT price FROM order_items WHERE id=? AND order_id=?", (item_id, order_id)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Позиция не найдена")
    new_item_total = row["price"] * data.qty
    conn.execute("UPDATE order_items SET qty=?, total=? WHERE id=?", (data.qty, new_item_total, item_id))
    new_total = conn.execute(
        "SELECT COALESCE(SUM(total),0) FROM order_items WHERE order_id=?", (order_id,)
    ).fetchone()[0]
    conn.execute("UPDATE orders SET total=? WHERE id=?", (new_total, order_id))
    conn.commit()
    return {"success": True, "order": _fetch_order(conn, order_id)}

@app.patch("/orders/{order_id}/items/{item_id}/delivered")
def toggle_delivered(order_id: str, item_id: int, tech=Depends(get_tech), conn=Depends(db)):
    row = conn.execute("SELECT is_delivered FROM order_items WHERE id=? AND order_id=?", (item_id, order_id)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Позиция не найдена")
    new_val = 0 if row["is_delivered"] else 1
    conn.execute("UPDATE order_items SET is_delivered=? WHERE id=?", (new_val, item_id))
    conn.commit()
    return {"success": True, "is_delivered": bool(new_val)}

@app.patch("/orders/{order_id}/items/{item_id}/act-issued")
def toggle_act_issued(order_id: str, item_id: int, tech=Depends(get_tech), conn=Depends(db)):
    if tech.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Только для руководителя")
    row = conn.execute("SELECT act_issued FROM order_items WHERE id=? AND order_id=?", (item_id, order_id)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Позиция не найдена")
    new_val = 0 if row["act_issued"] else 1
    conn.execute("UPDATE order_items SET act_issued=? WHERE id=?", (new_val, item_id))
    conn.commit()
    return {"success": True, "act_issued": bool(new_val)}

@app.post("/orders/{order_id}/stages")
def add_stage(order_id: str, data: StageAdd, tech=Depends(get_tech), conn=Depends(db)):
    if tech.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Только для руководителя")
    if not conn.execute("SELECT id FROM orders WHERE id=?", (order_id,)).fetchone():
        raise HTTPException(status_code=404, detail="Заказ не найден")
    if data.stage_type not in STAGE_TYPES:
        raise HTTPException(status_code=400, detail=f"Тип этапа должен быть одним из: {', '.join(STAGE_TYPES)}")
    tech_row = conn.execute("SELECT name FROM technicians WHERE id=?", (data.technician_id,)).fetchone()
    if not tech_row:
        raise HTTPException(status_code=400, detail="Техник не найден")
    rate_row = conn.execute(
        "SELECT rate FROM technician_rates WHERE technician_id=? AND stage_type=?",
        (data.technician_id, data.stage_type)
    ).fetchone()
    amount = (rate_row["rate"] if rate_row else 0) * data.qty
    max_n = conn.execute(
        "SELECT COALESCE(MAX(n),0) FROM order_stages WHERE order_id=?", (order_id,)
    ).fetchone()[0]
    conn.execute(
        "INSERT INTO order_stages (order_id,n,article,operation,stage_type,qty,technician,planned_date,amount) "
        "VALUES (?,?,?,?,?,?,?,?,?)",
        (order_id, max_n + 1, data.article, data.operation, data.stage_type,
         data.qty, tech_row["name"], data.planned_date, amount)
    )
    conn.commit()
    return {"success": True, "order": _fetch_order(conn, order_id)}

@app.delete("/orders/{order_id}/stages/{stage_id}")
def delete_stage(order_id: str, stage_id: int, tech=Depends(get_tech), conn=Depends(db)):
    if tech.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Только для руководителя")
    conn.execute("DELETE FROM order_stages WHERE id=? AND order_id=?", (stage_id, order_id))
    stages = conn.execute(
        "SELECT id FROM order_stages WHERE order_id=? ORDER BY n", (order_id,)
    ).fetchall()
    for i, row in enumerate(stages, 1):
        conn.execute("UPDATE order_stages SET n=? WHERE id=?", (i, row["id"]))
    conn.commit()
    return {"success": True, "order": _fetch_order(conn, order_id)}

@app.patch("/orders/{order_id}/stages/{stage_id}/transfer")
def transfer_stage(order_id: str, stage_id: int, tech=Depends(get_tech), conn=Depends(db)):
    now = datetime.now().isoformat()
    conn.execute(
        "UPDATE order_stages SET transferred_at=?, accepted_at=? WHERE id=? AND order_id=?",
        (now, now, stage_id, order_id)
    )
    conn.commit()
    return {"success": True, "order": _fetch_order(conn, order_id)}

@app.patch("/orders/{order_id}/stages/{stage_id}/complete")
def complete_stage(order_id: str, stage_id: int, tech=Depends(get_tech), conn=Depends(db)):
    now = datetime.now().isoformat()
    conn.execute(
        "UPDATE order_stages SET actual_date=? WHERE id=? AND order_id=?",
        (now, stage_id, order_id)
    )
    conn.commit()
    return {"success": True, "order": _fetch_order(conn, order_id)}

@app.patch("/orders/{order_id}/stages/{stage_id}/revert")
def revert_stage(order_id: str, stage_id: int, tech=Depends(get_tech), conn=Depends(db)):
    row = conn.execute(
        "SELECT actual_date, transferred_at FROM order_stages WHERE id=? AND order_id=?",
        (stage_id, order_id)
    ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Этап не найден")
    if row["actual_date"]:
        conn.execute("UPDATE order_stages SET actual_date=NULL WHERE id=? AND order_id=?", (stage_id, order_id))
    elif row["transferred_at"]:
        conn.execute(
            "UPDATE order_stages SET transferred_at=NULL, accepted_at=NULL WHERE id=? AND order_id=?",
            (stage_id, order_id)
        )
    conn.commit()
    return {"success": True, "order": _fetch_order(conn, order_id)}

@app.post("/orders/{order_id}/comments")
def add_comment(order_id: str, data: CommentAdd, tech=Depends(get_tech), conn=Depends(db)):
    if not conn.execute("SELECT id FROM orders WHERE id=?", (order_id,)).fetchone():
        raise HTTPException(status_code=404, detail="Заказ не найден")
    now = datetime.now().isoformat()
    conn.execute(
        "INSERT INTO comments (order_id, author, text, created_at) VALUES (?,?,?,?)",
        (order_id, tech["name"], data.text, now)
    )
    conn.commit()
    c = conn.execute(
        "SELECT * FROM comments WHERE order_id=? ORDER BY id DESC LIMIT 1", (order_id,)).fetchone()
    return {"success": True, "comment": dict(c)}

@app.get("/technicians")
def get_technicians(specialization: Optional[str] = None, tech=Depends(get_tech), conn=Depends(db)):
    if tech.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Только для руководителя")
    if specialization:
        rows = conn.execute(
            "SELECT id, name, city, specialization, load_percent FROM technicians "
            "WHERE role != 'admin' AND specialization=?", (specialization,)
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT id, name, city, specialization, load_percent FROM technicians WHERE role != 'admin'"
        ).fetchall()
    return {"technicians": [dict(r) for r in rows]}

@app.patch("/technicians/{tech_id}")
def update_technician(tech_id: str, data: TechnicianUpdate, tech=Depends(get_tech), conn=Depends(db)):
    if tech.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Только для руководителя")
    if not conn.execute("SELECT id FROM technicians WHERE id=?", (tech_id,)).fetchone():
        raise HTTPException(status_code=404, detail="Техник не найден")
    if data.specialization is not None:
        if data.specialization not in ('technician', 'modeler', ''):
            raise HTTPException(status_code=400, detail="Направление должно быть 'technician', 'modeler' или ''")
        conn.execute("UPDATE technicians SET specialization=? WHERE id=?", (data.specialization, tech_id))
    if data.load_percent is not None:
        if not (0 <= data.load_percent <= 100):
            raise HTTPException(status_code=400, detail="Процент должен быть от 0 до 100")
        conn.execute("UPDATE technicians SET load_percent=? WHERE id=?", (data.load_percent, tech_id))
    conn.commit()
    return {"success": True, "technician": dict(conn.execute(
        "SELECT id, name, city, specialization, load_percent FROM technicians WHERE id=?", (tech_id,)
    ).fetchone())}

@app.get("/acts")
def get_acts(tech=Depends(get_tech), conn=Depends(db)):
    if tech.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Только для руководителя")
    rows = conn.execute("SELECT * FROM acts ORDER BY id DESC").fetchall()
    result = []
    for row in rows:
        act = dict(row)
        act["items"] = [dict(r) for r in conn.execute(
            "SELECT * FROM act_items WHERE act_id=? ORDER BY id", (act["id"],)).fetchall()]
        result.append(act)
    return {"acts": result}

@app.post("/acts")
def create_act(data: ActCreate, tech=Depends(get_tech), conn=Depends(db)):
    if tech.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Только для руководителя")
    order = _fetch_order(conn, data.order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Заказ не найден")
    count = conn.execute("SELECT COUNT(*) FROM acts").fetchone()[0]
    act_number = f"АКТ-{count + 1:06d}"
    now = datetime.now().isoformat()
    discount = order.get("discount") or 0
    total = order.get("total") or 0
    final_total = round(total * (1 - discount / 100), 2)
    conn.execute(
        "INSERT INTO acts (act_number,order_id,clinic_name,doctor_name,patient_name,"
        "created_at,created_by,total,discount,final_total) VALUES (?,?,?,?,?,?,?,?,?,?)",
        (act_number, data.order_id, order["clinic_name"], order["doctor_name"],
         order["patient_name"], now, tech["name"], total, discount, final_total)
    )
    act_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    for item in order.get("items", []):
        conn.execute(
            "INSERT INTO act_items (act_id,article,name,qty,price,total) VALUES (?,?,?,?,?,?)",
            (act_id, item["article"], item["name"], item["qty"], item["price"], item["total"])
        )
    conn.commit()
    act = dict(conn.execute("SELECT * FROM acts WHERE id=?", (act_id,)).fetchone())
    act["items"] = [dict(r) for r in conn.execute(
        "SELECT * FROM act_items WHERE act_id=? ORDER BY id", (act_id,)).fetchall()]
    return {"success": True, "act": act}

@app.patch("/nomenclature/{item_id}")
def update_nomenclature(item_id: int, data: NomUpdate, tech=Depends(get_tech), conn=Depends(db)):
    if tech.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Только для руководителя")
    if not conn.execute("SELECT id FROM nomenclature WHERE id=?", (item_id,)).fetchone():
        raise HTTPException(status_code=404, detail="Позиция не найдена")
    if data.price < 0:
        raise HTTPException(status_code=400, detail="Цена не может быть отрицательной")
    conn.execute("UPDATE nomenclature SET price=? WHERE id=?", (data.price, item_id))
    conn.commit()
    return {"success": True, "item": dict(conn.execute(
        "SELECT * FROM nomenclature WHERE id=?", (item_id,)).fetchone())}

@app.get("/metrics")
def get_metrics(tech=Depends(get_tech), conn=Depends(db)):
    if tech.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Только для руководителя")
    now = datetime.now().isoformat()
    total      = conn.execute("SELECT COUNT(*) FROM orders").fetchone()[0]
    in_prog    = conn.execute("SELECT COUNT(*) FROM orders WHERE status='в_работе'").fetchone()[0]
    completed  = conn.execute("SELECT COUNT(*) FROM orders WHERE status IN ('готово','сдано')").fetchone()[0]
    overdue    = conn.execute(
        "SELECT COUNT(*) FROM orders WHERE deadline<? AND status NOT IN ('готово','сдано')", (now,)).fetchone()[0]
    on_time    = round(completed / total * 100) if total else 0
    return {"total_orders": total, "in_progress": in_prog, "completed": completed,
            "overdue": overdue, "on_time_percent": on_time}


# ── CLINICS ───────────────────────────────────────────────────────────────────

@app.get("/clinics")
def get_clinics(tech=Depends(get_tech), conn=Depends(db)):
    rows = conn.execute("SELECT * FROM clinics ORDER BY name").fetchall()
    return {"clinics": [dict(r) for r in rows]}

@app.post("/clinics")
def create_clinic(data: ClinicCreate, tech=Depends(get_tech), conn=Depends(db)):
    if tech.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Только для руководителя")
    if not data.name.strip():
        raise HTTPException(status_code=400, detail="Название клиники не может быть пустым")
    clinic_id = secrets.token_hex(6)
    try:
        conn.execute(
            "INSERT INTO clinics (id, name, phone, contact_name, city, notes) VALUES (?,?,?,?,?,?)",
            (clinic_id, data.name.strip(), data.phone, data.contact_name, data.city, data.notes)
        )
        conn.commit()
    except Exception:
        raise HTTPException(status_code=400, detail="Клиника с таким названием уже существует")
    return {"success": True, "clinic": dict(conn.execute("SELECT * FROM clinics WHERE id=?", (clinic_id,)).fetchone())}

@app.patch("/clinics/{clinic_id}")
def update_clinic(clinic_id: str, data: ClinicCreate, tech=Depends(get_tech), conn=Depends(db)):
    if tech.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Только для руководителя")
    if not conn.execute("SELECT id FROM clinics WHERE id=?", (clinic_id,)).fetchone():
        raise HTTPException(status_code=404, detail="Клиника не найдена")
    if not data.name.strip():
        raise HTTPException(status_code=400, detail="Название не может быть пустым")
    conn.execute(
        "UPDATE clinics SET name=?, phone=?, contact_name=?, city=?, notes=? WHERE id=?",
        (data.name.strip(), data.phone, data.contact_name, data.city, data.notes, clinic_id)
    )
    conn.commit()
    return {"success": True, "clinic": dict(conn.execute("SELECT * FROM clinics WHERE id=?", (clinic_id,)).fetchone())}

@app.delete("/clinics/{clinic_id}")
def delete_clinic(clinic_id: str, tech=Depends(get_tech), conn=Depends(db)):
    if tech.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Только для руководителя")
    conn.execute("DELETE FROM clinics WHERE id=?", (clinic_id,))
    conn.commit()
    return {"success": True}


# ── ALFA BANK ──────────────────────────────────────────────────────────────────

@app.get("/alfa/status")
def alfa_status(tech=Depends(get_tech), conn=Depends(db)):
    if tech.get("role") != "admin":
        raise HTTPException(status_code=403)
    row = conn.execute("SELECT access_token, updated_at FROM alfa_tokens WHERE id=1").fetchone()
    if row and row["access_token"]:
        return {"connected": True, "updated_at": row["updated_at"]}
    return {"connected": False}

@app.post("/alfa/connect")
def alfa_connect(data: AlfaKeySet, tech=Depends(get_tech), conn=Depends(db)):
    if tech.get("role") != "admin":
        raise HTTPException(status_code=403)
    if not data.api_key.strip():
        raise HTTPException(status_code=400, detail="API Key не может быть пустым")
    conn.execute(
        "INSERT INTO alfa_tokens (id, access_token, refresh_token, expires_at, updated_at) "
        "VALUES (1,?,NULL,NULL,?) ON CONFLICT(id) DO UPDATE SET "
        "access_token=excluded.access_token, updated_at=excluded.updated_at",
        (data.api_key.strip(), datetime.now().isoformat())
    )
    conn.commit()
    return {"success": True}

@app.get("/alfa/transactions")
async def alfa_transactions(tech=Depends(get_tech), conn=Depends(db)):
    if tech.get("role") != "admin":
        raise HTTPException(status_code=403)
    if not _HTTPX:
        raise HTTPException(status_code=503, detail="httpx не установлен на сервере")

    row = conn.execute("SELECT access_token FROM alfa_tokens WHERE id=1").fetchone()
    if not row or not row["access_token"]:
        raise HTTPException(status_code=400, detail="Банк не подключён")

    cert = (ALFA_CERT_PEM, ALFA_CERT_KEY) if ALFA_CERT_PEM and ALFA_CERT_KEY else None
    async with httpx.AsyncClient(cert=cert, verify=False, timeout=15) as client:
        resp = await client.get(
            f"{ALFA_API_BASE}/v1/accounts",
            headers={"Authorization": f"API_KEY {row['access_token']}"}
        )
    if resp.status_code == 401:
        raise HTTPException(status_code=401, detail="API Key недействителен — проверьте ключ")
    if resp.status_code != 200:
        raise HTTPException(status_code=resp.status_code,
                            detail=f"Ошибка API банка ({resp.status_code}): {resp.text[:300]}")
    return resp.json()

@app.delete("/alfa/disconnect")
def alfa_disconnect(tech=Depends(get_tech), conn=Depends(db)):
    if tech.get("role") != "admin":
        raise HTTPException(status_code=403)
    conn.execute("DELETE FROM alfa_tokens WHERE id=1")
    conn.commit()
    return {"success": True}

@app.post("/alfa/webhook")
async def alfa_webhook(request: Request):
    import json as _json
    try:
        body = await request.json()
    except Exception:
        body = {}
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    raw = _json.dumps(body, ensure_ascii=False)
    conn.execute(
        "INSERT INTO alfa_webhooks (event_type, amount, currency, operation_date, counterparty, inn, purpose, account, raw_json) VALUES (?,?,?,?,?,?,?,?,?)",
        (
            body.get("eventType") or body.get("type", ""),
            float(body.get("amount", {}).get("value", 0) if isinstance(body.get("amount"), dict) else body.get("amount", 0)),
            body.get("amount", {}).get("currency", "RUB") if isinstance(body.get("amount"), dict) else "RUB",
            body.get("operationDate") or body.get("date", ""),
            body.get("counterpartyName") or body.get("payer", {}).get("name", "") if isinstance(body.get("payer"), dict) else body.get("counterpartyName", ""),
            body.get("counterpartyInn") or "",
            body.get("paymentPurpose") or body.get("purpose", ""),
            body.get("accountNumber") or "",
            raw
        )
    )
    conn.commit()
    conn.close()
    return {"status": "ok"}

@app.get("/alfa/webhooks")
def get_webhooks(tech=Depends(get_tech), conn=Depends(db)):
    if tech.get("role") != "admin":
        raise HTTPException(status_code=403)
    rows = conn.execute("SELECT * FROM alfa_webhooks ORDER BY received_at DESC LIMIT 100").fetchall()
    return {"webhooks": [dict(r) for r in rows]}
