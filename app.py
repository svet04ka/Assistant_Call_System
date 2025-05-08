from flask import Flask, render_template, request, redirect, url_for, flash
from models import Station, Employee, Request, SessionLocal
from datetime import datetime

app = Flask(__name__)
app.secret_key = 'pass'

@app.route('/')
def index():
    return render_template('index.html')


@app.route('/add_request', methods=['GET', 'POST'])
def add_request_page():
    db = SessionLocal()
    try:
        if request.method == 'POST':
            # Обработка POST-запроса
            passenger_type = request.form.get('passenger_type')
            start_station_id = request.form.get('start_station')
            end_station_id = request.form.get('end_station')
            required_workers = request.form.get('required_workers')
            baggage = 'baggage' in request.form
            request_time_str = request.form.get('request_time')

            try:
                request_time = datetime.strptime(request_time_str, '%Y-%m-%dT%H:%M')
            except ValueError:
                request_time = datetime.now()

            new_request = Request(
                тип_пассажира=passenger_type,
                станция_отправления_id=start_station_id,
                станция_назначения_id=end_station_id,
                требуемые_сотрудники=int(required_workers),
                багаж=baggage,
                запрошенное_время=request_time,
                статус="новая"
            )

            db.add(new_request)
            db.commit()
            flash('Заявка успешно добавлена', 'success')
            return redirect(url_for('requests_list'))

        # GET-запрос - отображаем форму
        stations = db.query(Station).all()
        return render_template('add_request.html', stations=stations)
    except Exception as e:
        db.rollback()
        flash(f'Ошибка при добавлении заявки: {str(e)}', 'error')
        return redirect(url_for('add_request_page'))
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

@app.route('/requests', methods=['GET'])
def requests_list():
    db = SessionLocal()
    try:
        requests = db.query(Request).all()
        return render_template('requests_list.html', requests=requests)
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

if __name__ == '__main__':
    app.run(debug=True)