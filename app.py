from flask import Flask, render_template, request, redirect, url_for, flash, session
from sqlalchemy import func
from sqlalchemy.orm import joinedload

from models import Station, Employee, Request, SessionLocal
from datetime import datetime, timedelta
import logging

app = Flask(__name__)
app.secret_key = 'pass'

ADMIN_PASSWORD = 'pass'  # Пароль для доступа к админке

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


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
                требуемые_сотрудники=int(request.form.get('required_workers', 1)),
                багаж='baggage' in request.form,
                запрошенное_время=datetime.strptime(request.form.get('request_time'), '%Y-%m-%dT%H:%M'),
                статус='новая'
            )

            db.add(new_request)
            db.commit()

            flash('Заявка успешно создана', 'success')
            return redirect(url_for('requests_list'))

        stations = db.query(Station).order_by(Station.название).all()
        return render_template('add_request.html',
                               stations=stations,
                               min_date=datetime.now().strftime('%Y-%m-%d'),
                               min_time=datetime.now().strftime('%H:%M'))

    except ValueError as e:
        db.rollback()
        flash('Некорректный формат данных', 'error')
        return redirect(url_for('add_request_page'))

    except Exception as e:
        db.rollback()
        logger.error(f"Ошибка при создании заявки: {str(e)}")
        flash('Произошла ошибка при создании заявки', 'error')
        return redirect(url_for('add_request_page'))

    finally:
        db.close()


@app.route('/requests', methods=['GET'])
def requests_list():
    db = SessionLocal()
    try:
        requests = db.query(Request).order_by(Request.запрошенное_время.desc()).all()
        return render_template('requests_list.html', requests=requests)
    finally:
        db.close()


@app.route('/add_employee', methods=['GET', 'POST'])
def add_employee_page():
    db = SessionLocal()
    try:
        if request.method == 'POST':
            full_name = request.form.get('full_name')
            station_id = request.form.get('station_id')
            languages = request.form.getlist('languages')
            works_with_wheelchairs = 'works_with_wheelchairs' in request.form
            work_days = request.form.getlist('work_days')
            shift = request.form.get('shift')

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

        stations = db.query(Station).all()
        return render_template('add_employee.html', stations=stations)
    except Exception as e:
        db.rollback()
        flash(f'Ошибка при добавлении сотрудника: {str(e)}', 'error')
        return redirect(url_for('add_employee_page'))
    finally:
        db.close()


@app.route('/employees', methods=['GET'])
def employees_list():
    db = SessionLocal()
    try:
        employees = db.query(Employee).all()
        return render_template('employees_list.html', employees=employees)
    finally:
        db.close()


@app.route('/manual_assignment', methods=['GET', 'POST'])
def manual_assignment():
    db = SessionLocal()
    try:
        today = datetime.now().date()

        if request.method == 'POST':
            # Обработка назначения сотрудника
            if 'assign' in request.form:
                request_id = request.form.get('request_id')
                employee_id = request.form.get('employee_id')

                req = db.query(Request).get(request_id)
                emp = db.query(Employee).get(employee_id)

                if req and emp:
                    if req.назначенные_сотрудники is None:
                        req.назначенные_сотрудники = []

                    if str(employee_id) not in req.назначенные_сотрудники:
                        req.назначенные_сотрудники.append(str(employee_id))
                        emp.статус = 'назначен'
                        db.commit()
                        flash('Сотрудник успешно назначен', 'success')
                    else:
                        flash('Этот сотрудник уже назначен на эту заявку', 'warning')

            # Обработка изменения статуса
            elif 'change_status' in request.form:
                request_id = request.form.get('request_id')
                new_status = request.form.get('new_status')

                req = db.query(Request).get(request_id)
                if req:
                    req.статус = new_status
                    db.commit()
                    flash('Статус заявки обновлен', 'success')

        # Получаем заявки для сегодня
        start_datetime = datetime.combine(today, datetime.min.time())
        end_datetime = datetime.combine(today + timedelta(days=1), datetime.min.time())

        requests = db.query(Request).filter(
            Request.запрошенное_время >= start_datetime,
            Request.запрошенное_время < end_datetime
        ).options(
            joinedload(Request.станция_отправления),
            joinedload(Request.станция_назначения)
        ).order_by(Request.запрошенное_время).all()

        # Получаем доступных сотрудников
        current_weekday = today.strftime('%A').lower()
        employees = db.query(Employee).filter(
            Employee.статус == 'доступен'
        ).options(joinedload(Employee.текущая_станция)).all()

        # Фильтруем сотрудников по графику работы (если график указан)
        filtered_employees = []
        for emp in employees:
            if emp.график and 'рабочие_дни' in emp.график and current_weekday in emp.график['рабочие_дни']:
                filtered_employees.append(emp)
            elif not emp.график:
                filtered_employees.append(emp)

        return render_template('manual_assignment.html',
                               requests=requests,
                               employees=filtered_employees,
                               today=today.strftime('%d.%m.%Y'))

    except Exception as e:
        db.rollback()
        flash(f'Ошибка: {str(e)}', 'error')
        logger.error(f"Ошибка в manual_assignment: {str(e)}", exc_info=True)
        return render_template('manual_assignment.html',
                               requests=[],
                               employees=[],
                               today=datetime.now().strftime('%d.%m.%Y'))

    finally:
        db.close()


@app.route('/admin/assign', methods=['GET', 'POST'])
def admin_assign():
    db = SessionLocal()
    try:
        # Получаем выбранную дату из GET-параметра или POST-данных
        selected_date_str = request.args.get('selected_date') or request.form.get('selected_date')
        try:
            selected_date = datetime.strptime(selected_date_str,
                                              '%Y-%m-%d').date() if selected_date_str else datetime.now().date()
        except ValueError:
            selected_date = datetime.now().date()

        # Вычисляем минимальную и максимальную доступные даты
        min_date = datetime.now().date()
        max_date = min_date + timedelta(days=30)

        if request.method == 'POST':
            # Обработка назначения сотрудника
            if 'assign_employee' in request.form:
                request_id = request.form.get('request_id')
                employee_id = request.form.get('employee_id')

                req = db.query(Request).get(request_id)
                emp = db.query(Employee).get(employee_id)

                if req and emp:
                    if not req.назначенные_сотрудники:
                        req.назначенные_сотрудники = []

                    if str(emp.id) not in req.назначенные_сотрудники:
                        req.назначенные_сотрудники.append(str(emp.id))
                        emp.статус = 'назначен'
                        db.commit()
                        flash(f'Сотрудник {emp.фио} назначен на заявку #{req.id}', 'success')
                    else:
                        flash('Этот сотрудник уже назначен на эту заявку', 'warning')

                return redirect(url_for('admin_assign', selected_date=selected_date.strftime('%Y-%m-%d')))

            # Обработка изменения статуса
            elif 'change_status' in request.form:
                request_id = request.form.get('request_id')
                new_status = request.form.get('new_status')

                req = db.query(Request).get(request_id)
                if req:
                    req.статус = new_status
                    db.commit()
                    flash(f'Статус заявки #{req.id} изменен на "{new_status}"', 'success')

                return redirect(url_for('admin_assign', selected_date=selected_date.strftime('%Y-%m-%d')))

        # Получаем заявки на выбранную дату + 2 дня вперед
        start_date = selected_date
        end_date = selected_date + timedelta(days=2)

        requests = db.query(Request).filter(
            Request.запрошенное_время >= datetime.combine(start_date, datetime.min.time()),
            Request.запрошенное_время <= datetime.combine(end_date, datetime.max.time())
        ).options(
            joinedload(Request.станция_отправления),
            joinedload(Request.станция_назначения)
        ).order_by(Request.запрошенное_время).all()

        # Получаем доступных сотрудников
        current_weekday = selected_date.strftime('%A').lower()
        employees = db.query(Employee).filter(
            Employee.статус == 'доступен'
        ).options(joinedload(Employee.текущая_станция)).all()

        return render_template('admin_assign.html',
                               requests=requests,
                               employees=employees,
                               selected_date=selected_date,
                               min_date=min_date,
                               max_date=max_date,
                               statuses=['новая', 'назначена', 'в процессе', 'завершена', 'отменена'])

    except Exception as e:
        db.rollback()
        flash(f'Ошибка: {str(e)}', 'danger')
        logger.error(f"Error in admin_assign: {str(e)}", exc_info=True)
        return redirect(url_for('admin_assign', selected_date=selected_date.strftime('%Y-%m-%d')))

    finally:
        db.close()

@app.route('/admin/assign_employee', methods=['POST'])
def assign_employee():
    db = SessionLocal()
    try:
        request_id = request.form.get('request_id')
        employee_id = request.form.get('employee_id')

        req = db.query(Request).get(request_id)
        emp = db.query(Employee).get(employee_id)

        if not req or not emp:
            flash('Заявка или сотрудник не найдены', 'danger')
            return redirect(url_for('admin_assign'))

        if not req.назначенные_сотрудники:
            req.назначенные_сотрудники = []

        if str(emp.id) in req.назначенные_сотрудники:
            flash('Этот сотрудник уже назначен на эту заявку', 'warning')
        else:
            req.назначенные_сотрудники.append(str(emp.id))
            emp.статус = 'назначен'
            db.commit()
            flash(f'Сотрудник {emp.фио} успешно назначен на заявку #{req.id}', 'success')

    except Exception as e:
        db.rollback()
        flash(f'Ошибка при назначении: {str(e)}', 'danger')
        logger.error(f"Assignment error: {str(e)}", exc_info=True)
    finally:
        db.close()

    return redirect(url_for('admin_assign'))

@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        password = request.form.get('password')
        if password == ADMIN_PASSWORD:
            session['admin_logged'] = True
            return redirect(url_for('admin_dashboard'))
        else:
            flash('Неверный пароль', 'danger')
    return render_template('admin_login.html')

@app.route('/admin/logout')
def admin_logout():
    session.pop('admin_logged', None)
    return redirect(url_for('index'))

@app.route('/admin')
def admin_dashboard():
    if not session.get('admin_logged'):
        return redirect(url_for('admin_login'))
    return render_template('admin_dashboard.html')

if __name__ == '__main__':
    app.run(debug=True)