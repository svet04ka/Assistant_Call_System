import click
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from sqlalchemy import func
from sqlalchemy.orm import joinedload

from models import Station, Employee, Request, SessionLocal
from datetime import datetime, date, timedelta
import threading
from function import (assign_employees,
                      run_scheduler)
import logging

app = Flask(__name__)
app.secret_key = 'pass'

# Инициализация фонового планировщика
scheduler_thread = threading.Thread(target=run_scheduler)
scheduler_thread.daemon = True
scheduler_thread.start()

@app.route('/')
def index():
    return render_template('index.html')


@app.route('/add_request', methods=['GET', 'POST'])
def add_request_page():
    db = SessionLocal()
    try:
        if request.method == 'POST':
            # Создание новой заявки
            new_request = Request(
                тип_пассажира=request.form.get('passenger_type'),
                станция_отправления_id=request.form.get('start_station'),
                станция_назначения_id=request.form.get('end_station'),
                требуемые_сотрудники=int(request.form.get('required_workers')),
                багаж='baggage' in request.form,
                запрошенное_время=datetime.strptime(request.form.get('request_time'), '%Y-%m-%dT%H:%M'),
                статус='новая'
            )
            db.add(new_request)
            db.commit()

            if assign_employees(db, new_request):
                flash('Заявка создана и сотрудники назначены', 'success')
            else:
                flash('Заявка создана, но не удалось назначить сотрудников', 'warning')

            return redirect(url_for('requests_list'))

        stations = db.query(Station).all()
        return render_template('add_request.html', stations=stations)
    except Exception as e:
        db.rollback()
        flash(f'Ошибка: {str(e)}', 'error')
        return redirect(url_for('add_request_page'))
    finally:
        db.close()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@app.route('/auto_assign', methods=['POST'])
def auto_assign():
    db = SessionLocal()
    try:
        logger.info("=== НАЧАЛО АВТОНАЗНАЧЕНИЯ ===")

        # 1. Сброс текущих назначений
        reset_result = db.query(Request).filter(
            Request.статус.in_(['назначена', 'в_процессе'])
        ).update({
            'статус': 'новая',
            'назначенные_сотрудники': []
        }, synchronize_session=False)

        db.query(Employee).filter(
            Employee.статус == 'назначен'
        ).update({
            'статус': 'доступен'
        }, synchronize_session=False)
        db.commit()

        # 2. Получаем новые заявки
        new_requests = db.query(Request).filter(
            Request.статус == 'новая',
            Request.запрошенное_время >= datetime.now()
        ).order_by(Request.запрошенное_время).all()

        if not new_requests:
            return jsonify({'status': 'success', 'message': 'Нет новых заявок для назначения'})

        # 3. Получаем доступных сотрудников
        all_employees = db.query(Employee).filter(
            Employee.статус == 'доступен'
        ).options(joinedload(Employee.текущая_станция)).all()

        assigned_count = 0
        weekday_map = {
            'Monday': 'пн',
            'Tuesday': 'вт',
            'Wednesday': 'ср',
            'Thursday': 'чт',
            'Friday': 'пт',
            'Saturday': 'сб',
            'Sunday': 'вс'
        }

        for req in new_requests:
            suitable_employees = []
            required = req.требуемые_сотрудники
            current_weekday = weekday_map[req.запрошенное_время.strftime('%A')]

            for emp in all_employees:
                # Проверяем станцию
                if emp.текущая_станция_id != req.станция_отправления_id:
                    continue

                # Проверяем график (новый формат)
                work_days = emp.график.get('рабочие_дни', [])
                if current_weekday not in work_days:
                    continue

                # Проверяем навыки
                if req.тип_пассажира == 'колясочник' and not emp.навыки.get('работает_с_колясками', False):
                    continue

                # Проверяем текущую загрузку
                current_assignments = db.query(Request).filter(
                    Request.назначенные_сотрудники.contains([emp.id]),
                    Request.статус.in_(['назначена', 'в_процессе'])
                ).count()

                if current_assignments < 3:
                    suitable_employees.append(emp)

            if len(suitable_employees) >= required:
                assigned = suitable_employees[:required]
                req.назначенные_сотрудники = [emp.id for emp in assigned]
                req.статус = 'назначена'

                for emp in assigned:
                    emp.статус = 'назначен'

                db.commit()
                assigned_count += 1

        return jsonify({
            'status': 'success',
            'message': f'Успешно назначено {assigned_count} из {len(new_requests)} заявок',
            'assigned': assigned_count,
            'total': len(new_requests)
        })
    except Exception as e:
        db.rollback()
        logger.error(f"Ошибка при автоназначении: {str(e)}", exc_info=True)
        return jsonify({
            'status': 'error',
            'message': f'Ошибка при автоназначении: {str(e)}'
        }), 500
    finally:
        db.close()

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

        db.query(Employee).filter(
            Employee.статус == 'назначен'
        ).update({
            'статус': 'доступен'
        }, synchronize_session=False)

        db.commit()

        # Получение и распределение заявок
        today = date.today()
        current_weekday = today.strftime('%A').lower()

        # Получаем заявки, отсортированные по приоритету
        requests = db.query(Request).filter(
            Request.статус == 'новая',
            Request.запрошенное_время >= datetime.now()
        ).order_by(
            Request.запрошенное_время.asc()
        ).all()

        # Получаем всех доступных сотрудников
        all_employees = db.query(Employee).filter(
            Employee.статус == 'доступен'
        ).options(joinedload(Employee.текущая_станция)).all()

        for req in requests:
            suitable_employees = []
            required = req.требуемые_сотрудники

            # Фильтруем сотрудников по станции, графику и навыкам
            for emp in all_employees:
                # Проверка станции
                if emp.текущая_станция_id != req.станция_отправления_id:
                    continue

                # Проверка графика (рабочий день)
                work_days = emp.график.get('рабочие_дни', [])
                if current_weekday not in work_days:
                    continue

                # Проверка навыков для колясочников
                if req.тип_пассажира == 'колясочник' and not emp.навыки.get('работает_с_колясками', False):
                    continue

                # Проверка текущей загрузки сотрудника
                current_assignments = db.query(Request).filter(
                    Request.назначенные_сотрудники.contains([emp.id]),
                    Request.статус.in_(['назначена', 'в_процессе'])
                ).count()

                if current_assignments < 3:  # Максимум 3 заявки на сотрудника
                    suitable_employees.append(emp)

            # Назначаем сотрудников
            if suitable_employees:
                assigned = suitable_employees[:required]
                req.назначенные_сотрудники = [emp.id for emp in assigned]
                req.статус = 'назначена'

                for emp in assigned:
                    emp.статус = 'назначен'

                db.commit()

        return True
    except Exception as e:
        db.rollback()
        print(f"Ошибка при пересчете расписания: {str(e)}")
        return False

@app.route('/assign_status')
def assign_status():
    db = SessionLocal()
    try:
        requests = db.query(Request).filter(
            Request.статус.in_(['назначена', 'в_процессе'])
        ).options(
            joinedload(Request.станция_отправления),
            joinedload(Request.станция_назначения)
        ).order_by(Request.запрошенное_время).limit(10).all()

        result = []
        for req in requests:
            result.append({
                'id': req.id,
                'route': f"{req.станция_отправления.название} → {req.станция_назначения.название}",
                'time': req.запрошенное_время.strftime('%H:%M'),
                'status': req.статус,
                'employees': req.назначенные_сотрудники
            })

        return jsonify(result)
    finally:
        db.close()

@app.route('/requests', methods=['GET'])
def requests_list():
    db = SessionLocal()
    try:
        query = db.query(Request)

        # Применяем фильтры
        status_filter = request.args.get('status')
        date_filter = request.args.get('date')

        if status_filter:
            query = query.filter(Request.статус == status_filter)

        if date_filter:
            filter_date = datetime.strptime(date_filter, '%Y-%m-%d').date()
            query = query.filter(
                Request.запрошенное_в_time >= datetime.combine(filter_date, datetime.min.time()),
                Request.запрошенное_в_time < datetime.combine(filter_date + timedelta(days=1), datetime.min.time())
            )

        requests = query.all()

        # Получаем статистику для отображения
        new_requests_count = db.query(Request).filter(Request.статус == 'новая').count()
        in_progress_count = db.query(Request).filter(Request.статус.in_(['назначена', 'в_процессе'])).count()
        total_requests = db.query(Request).count()

        return render_template('requests_list.html',
                               requests=requests,
                               new_requests_count=new_requests_count,
                               in_progress_count=in_progress_count,
                               total_requests=total_requests,
                               latest_requests=requests[:10000])
    finally:
        db.close()

@app.route('/add_employee', methods=['GET', 'POST'])
def add_employee_page():
    db = SessionLocal()
    try:
        if request.method == 'POST':
            # Обработка POST-запроса
            full_name = request.form.get('full_name')
            station_id = request.form.get('station_id')
            languages = request.form.getlist('languages')
            works_with_wheelchairs = 'works_with_wheelchairs' in request.form
            work_days = request.form.getlist('work_days')
            shift = request.form.get('shift')

            # Создаем JSON для навыков и графика
            skills = {
                "языки": languages if languages else ["рус"],
                "работает_с_колясками": works_with_wheelchairs
            }

            schedule = {
                "смена": shift if shift else "",
                "рабочие_дни": work_days if work_days else []
            }

            new_employee = Employee(
                фио=full_name,
                текущая_станция_id=station_id if station_id else None,
                статус="доступен",
                навыки=skills,
                график=schedule
            )

            db.add(new_employee)
            db.commit()
            flash('Сотрудник успешно добавлен', 'success')
            return redirect(url_for('employees_list'))

        # GET-запрос - отображаем форму
        stations = db.query(Station).all()
        return render_template('add_employee.html', stations=stations)
    except Exception as e:
        db.rollback()
        flash(f'Ошибка при добавлении сотрудника: {str(e)}', 'error')
        return redirect(url_for('add_employee_page'))
    finally:
        db.close()

@app.route('/reschedule', methods=['POST'])
def reschedule():
    db = SessionLocal()
    try:
        # 1. Сбрасываем статусы всех невыполненных заявок
        db.query(Request).filter(
            Request.статус.in_(['новая', 'назначена', 'в_процессе'])
        ).update({
            'статус': 'новая',
            'назначенные_сотрудники': []
        }, synchronize_session=False)

        db.commit()

        # 2. Получаем всех сотрудников
        employees = db.query(Employee).filter(
            Employee.статус == 'доступен'
        ).all()

        # 3. Получаем заявки, отсортированные по приоритету
        requests = db.query(Request).filter(
            Request.статус == 'новая'
        ).order_by(
            Request.запрошенное_время.asc()
        ).all()

        # 4. Перераспределяем заявки
        for req in requests:
            suitable_employees = []

            for emp in employees:
                # Проверка навыков
                if req.тип_пассажира == 'колясочник' and not emp.навыки.get('работает_с_колясками', False):
                    continue

                # Проверка текущей загрузки
                current_assignments = db.query(Request).filter(
                    Request.назначенные_сотрудники.contains([emp.id]),
                    Request.статус == 'назначена'
                ).count()

                if current_assignments < 3:
                    suitable_employees.append(emp)

            # Назначаем сотрудников
            if suitable_employees:
                req.назначенные_сотрудники = [emp.id for emp in suitable_employees[:req.требуемые_сотрудники]]
                req.статус = 'назначена'
                db.commit()

        flash('Расписание успешно пересчитано', 'success')
    except Exception as e:
        db.rollback()
        flash(f'Ошибка при пересчете расписания: {str(e)}', 'error')
    finally:
        db.close()

    return redirect(url_for('requests_list'))

@app.route('/employees', methods=['GET'])
def employees_list():
    db = SessionLocal()
    try:
        employees = db.query(Employee).all()
        return render_template('employees_list.html', employees=employees)
    finally:
        db.close()


scheduler_thread = None

@app.cli.command("start-scheduler")
def start_scheduler_command():
    """Start the background scheduler"""
    global scheduler_thread
    if scheduler_thread is None:
        scheduler_thread = threading.Thread(target=run_scheduler)
        scheduler_thread.daemon = True
        scheduler_thread.start()
        click.echo("Scheduler started")

@app.route('/monitor')
def monitor_requests():
    db = SessionLocal()
    try:
        today = date.today()
        requests = db.query(Request).filter(
            Request.запрошенное_время >= datetime.combine(today, datetime.min.time()),
            Request.запрошенное_время < datetime.combine(today + timedelta(days=1), datetime.min.time()),
            Request.статус != 'выполнена'
        ).all()
        return render_template('monitor.html', requests=requests, today=today)
    except Exception as e:
        flash(f'Ошибка при получении заявок: {str(e)}', 'error')
        return redirect(url_for('index'))
    finally:
        db.close()

if __name__ == '__main__':
    app.run(debug=True)