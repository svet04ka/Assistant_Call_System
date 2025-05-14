from datetime import datetime, date, timedelta
from sqlalchemy import func, Boolean
from models import Employee, Request, SessionLocal
import time as time_module


def assign_employees(db, request):
    """Автоматическое назначение сотрудников на заявку"""
    suitable_employees = find_suitable_employees(db, request)

    if suitable_employees:
        request.назначенные_сотрудники = [emp.id for emp in suitable_employees[:request.требуемые_сотрудники]]
        request.статус = 'назначена'
        request.расчетное_время_выполнения = calculate_estimated_time(db, request)
        db.commit()
        return True
    return False


def calculate_estimated_time(db, request):
    """Расчет времени выполнения заявки"""
    base_time = 15
    if request.тип_пассажира == 'колясочник':
        base_time += 10
    elif request.тип_пассажира == 'слабовидящий':
        base_time += 5
    if request.багаж:
        base_time += 5
    if request.требуемые_сотрудники > 1:
        base_time -= 2 * (request.требуемые_сотрудники - 1)
    return max(base_time, 5)


def find_suitable_employees(db, request):
    """Поиск подходящих сотрудников для заявки"""
    query = db.query(Employee).filter(
        Employee.текущая_станция_id == request.станция_отправления_id,
        Employee.статус == 'доступен'
    )

    if request.тип_пассажира == 'колясочник':
        query = query.filter(Employee.навыки['работает_с_колясками'].astext.cast(Boolean) == True)

    busy_employees = db.query(Request.назначенные_сотрудники).filter(
        Request.статус == 'назначена',
        Request.запрошенное_время >= datetime.combine(request.запрошенное_время.date(), datetime.min.time()),
        Request.запрошенное_время < datetime.combine(request.запрошенное_время.date() + timedelta(days=1),
                                                     datetime.min.time())
    ).all()

    busy_ids = [emp_id for sublist in busy_employees for emp_id in (sublist[0] or [])]

    if busy_ids:
        query = query.filter(Employee.id.notin_(busy_ids))

    return query.order_by(func.array_length(Employee.назначенные_заявки, 1).asc()).all()


def reschedule_all(db):
    """Полное перераспределение всех заявок"""
    try:
        # Сброс текущих назначений
        db.query(Request).filter(
            Request.статус.in_(['новая', 'назначена', 'в_процессе'])
        ).update({
            'статус': 'новая',
            'назначенные_сотрудники': []
        }, synchronize_session=False)
        db.commit()

        # Получение и распределение заявок
        employees = db.query(Employee).filter(Employee.статус == 'доступен').all()
        requests = db.query(Request).filter(Request.статус == 'новая').order_by(Request.запрошенное_время.asc()).all()

        for req in requests:
            assign_employees(db, req)

        return True
    except Exception as e:
        db.rollback()
        raise e


def run_scheduler():
    """Фоновая задача для автоматического распределения"""
    while True:
        db = SessionLocal()
        try:
            time_module.sleep(300)
            schedule_requests(db)
        except Exception as e:
            print(f"Scheduler error: {str(e)}")
        finally:
            db.close()

def schedule_requests(db):
    today = date.today()

    # 1. Получаем все незавершенные заявки на сегодня
    requests = db.query(Request).filter(
        Request.запрошенное_время >= datetime.combine(today, datetime.min.time()),
        Request.запрошенное_время < datetime.combine(today + timedelta(days=1), datetime.min.time()),
        Request.статус.in_(['новая', 'назначена'])
    ).order_by(Request.запрошенное_время).all()

    # 2. Получаем всех доступных сотрудников один раз
    employees = db.query(Employee).filter(
        Employee.статус == 'доступен'
    ).all()

    # 3. Алгоритм распределения
    for req in requests:
        # Передаем всех сотрудников в функцию
        suitable_employees = find_suitable_employees(db, req, employees)

        if suitable_employees:
            req.назначенные_сотрудники = [emp.id for emp in suitable_employees[:req.требуемые_сотрудники]]
            req.статус = 'назначена'
            db.commit()
