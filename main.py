from fastapi import FastAPI, Depends
from sqlalchemy.orm import Session
from models import Station, get_db, Employee

app = FastAPI()

@app.get("/stations/")
def read_stations(db: Session = Depends(get_db)):
    return db.query(Station).all()

@app.post("/employees/")
def create_employee(фио: str, db: Session = Depends(get_db)):
    new_employee = Employee(фио=фио, статус="доступен")
    db.add(new_employee)
    db.commit()
    db.refresh(new_employee)
    return new_employee