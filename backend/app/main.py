from fastapi import FastAPI, HTTPException, Depends, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
from datetime import datetime
import json, os

app = FastAPI(title="Dental Lab API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Простая авторизация по PIN ---
TECHNICIANS = {
    "1111": {"id": "T001", "name": "Петров Михаил", "city": "Москва"},
    "2222": {"id": "T002", "name": "Иванов Сергей",  "city": "Москва"},
    "3333": {"id": "T003", "name": "Козлова Татьяна", "city": "Москва"},
    "0000": {"id": "ADMIN", "name": "Руководитель",   "city": "Москва", "role": "admin"},
}

# --- Моковые данные заказов (до подключения 1С) ---
ORDERS = [
    {
        "id": "ЗЛ-000101",
        "patient_name": "Захаров В.Н.",
        "clinic_name": "Дентал Плюс",
        "doctor_name": "Соколов К.Д.",
        "work_type": "Металлокерамика",
        "units": 4,
        "teeth": "14, 15, 16, 17",
        "description": "Цвет A2, ориентир на соседние зубы",
        "technician_id": "T001",
        "technician_name": "Петров Михаил",
        "status": "в_работе",
        "priority": "высокий",
        "created_at": "2026-05-18T10:00:00",
        "deadline": "2026-05-20T18:00:00",
        "appointment_at": "2026-05-20T19:30:00",
        "comments": [],
        "messages": [
            {
                "id": "m1",
                "from": "Соколов К.Д.",
                "text": "Цвет уточнил — ориентируйтесь на зуб 13, не на шкалу",
                "time": "2026-05-19T09:14:00",
                "has_photo": True
            }
        ]
    },
    {
        "id": "ЗЛ-000102",
        "patient_name": "Смирнова А.К.",
        "clinic_name": "Улыбка",
        "doctor_name": "Попов Д.А.",
        "work_type": "Циркониевая коронка",
        "units": 1,
        "teeth": "36",
        "description": "Стандартный цвет B1",
        "technician_id": "T001",
        "technician_name": "Петров Михаил",
        "status": "новый",
        "priority": "высокий",
        "created_at": "2026-05-17T09:00:00",
        "deadline": "2026-05-19T18:00:00",
        "appointment_at": "2026-05-21T10:00:00",
        "comments": [],
        "messages": []
    },
    {
        "id": "ЗЛ-000103",
        "patient_name": "Новикова Е.П.",
        "clinic_name": "Дентал Плюс",
        "doctor_name": "Соколов К.Д.",
        "work_type": "Металлокерамика",
        "units": 3,
        "teeth": "24, 25, 26",
        "description": "Цвет A2, особое внимание к окклюзии",
        "technician_id": "T001",
        "technician_name": "Петров Михаил",
        "status": "в_работе",
        "priority": "средний",
        "created_at": "2026-05-18T11:00:00",
        "deadline": "2026-05-21T14:00:00",
        "appointment_at": "2026-05-22T11:00:00",
        "comments": [],
        "messages": [
            {
                "id": "m2",
                "from": "Соколов К.Д.",
                "text": "Прикус изменился после слепка, учтите при окклюзии",
                "time": "2026-05-19T17:42:00",
                "has_photo": False
            }
        ]
    },
    {
        "id": "ЗЛ-000104",
        "patient_name": "Козлов И.В.",
        "clinic_name": "МедСтом",
        "doctor_name": "Кузнецов А.П.",
        "work_type": "Имплант-коронка циркониевая",
        "units": 1,
        "teeth": "46",
        "description": "Цвет C2",
        "technician_id": "T001",
        "technician_name": "Петров Михаил",
        "status": "новый",
        "priority": "низкий",
        "created_at": "2026-05-19T08:00:00",
        "deadline": "2026-05-23T18:00:00",
        "appointment_at": "2026-05-25T12:00:00",
        "comments": [],
        "messages": []
    },
    {
        "id": "ЗЛ-000105",
        "patient_name": "Морозов Д.С.",
        "clinic_name": "Улыбка",
        "doctor_name": "Попов Д.А.",
        "work_type": "Съёмный протез",
        "units": 1,
        "teeth": "Верхняя челюсть",
        "description": "Полный съёмный, акрил розовый",
        "technician_id": "T002",
        "technician_name": "Иванов Сергей",
        "status": "в_работе",
        "priority": "средний",
        "created_at": "2026-05-17T14:00:00",
        "deadline": "2026-05-21T12:00:00",
        "appointment_at": "2026-05-22T14:00:00",
        "comments": [],
        "messages": []
    },
]

# --- Модели ---
class PinLogin(BaseModel):
    pin: str

class StatusUpdate(BaseModel):
    status: str

class CommentAdd(BaseModel):
    text: str

# --- Хелпер: получить техника по PIN ---
def get_technician(x_pin: str = Header(...)):
    tech = TECHNICIANS.get(x_pin)
    if not tech:
        raise HTTPException(status_code=401, detail="Неверный PIN")
    return tech

# --- ENDPOINTS ---

@app.get("/")
def root():
    return {"status": "Dental Lab API работает", "version": "1.0"}

@app.post("/auth/login")
def login(data: PinLogin):
    tech = TECHNICIANS.get(data.pin)
    if not tech:
        raise HTTPException(status_code=401, detail="Неверный PIN")
    return {"success": True, "technician": tech}

@app.get("/orders")
def get_orders(technician_id: Optional[str] = None, tech=Depends(get_technician)):
    if tech.get("role") == "admin" or technician_id is None:
        orders = ORDERS if tech.get("role") == "admin" else [
            o for o in ORDERS if o["technician_id"] == tech["id"]
        ]
    else:
        orders = [o for o in ORDERS if o["technician_id"] == technician_id]
    return {"orders": orders, "total": len(orders)}

@app.get("/orders/{order_id}")
def get_order(order_id: str, tech=Depends(get_technician)):
    order = next((o for o in ORDERS if o["id"] == order_id), None)
    if not order:
        raise HTTPException(status_code=404, detail="Заказ не найден")
    return order

@app.patch("/orders/{order_id}/status")
def update_status(order_id: str, data: StatusUpdate, tech=Depends(get_technician)):
    order = next((o for o in ORDERS if o["id"] == order_id), None)
    if not order:
        raise HTTPException(status_code=404, detail="Заказ не найден")
    order["status"] = data.status
    return {"success": True, "order_id": order_id, "status": data.status}

@app.post("/orders/{order_id}/comments")
def add_comment(order_id: str, data: CommentAdd, tech=Depends(get_technician)):
    order = next((o for o in ORDERS if o["id"] == order_id), None)
    if not order:
        raise HTTPException(status_code=404, detail="Заказ не найден")
    comment = {
        "id": str(len(order["comments"]) + 1),
        "author": tech["name"],
        "text": data.text,
        "created_at": datetime.now().isoformat()
    }
    order["comments"].append(comment)
    return {"success": True, "comment": comment}

@app.get("/technicians")
def get_technicians(tech=Depends(get_technician)):
    if tech.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Только для руководителя")
    return {"technicians": [
        {"id": v["id"], "name": v["name"], "city": v["city"]}
        for v in TECHNICIANS.values() if v.get("role") != "admin"
    ]}

@app.get("/metrics")
def get_metrics(tech=Depends(get_technician)):
    if tech.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Только для руководителя")
    return {
        "total_orders": len(ORDERS),
        "in_progress": len([o for o in ORDERS if o["status"] == "в_работе"]),
        "completed": len([o for o in ORDERS if o["status"] == "готово"]),
        "overdue": 2,
        "on_time_percent": 78
    }
