from sqlalchemy import create_engine, Column, Integer, String, Boolean, JSON, DateTime, ForeignKey, Text, \
    CheckConstraint
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from datetime import datetime
import os
from dotenv import load_dotenv
from typing import List, Optional

load_dotenv()

DATABASE_URL = f"postgresql://{os.getenv('DB_USER')}:{os.getenv('DB_PASSWORD')}@{os.getenv('DB_HOST')}:{os.getenv('DB_PORT')}/{os.getenv('DB_NAME')}"

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


class Station(Base):
    __tablename__ = 'stations'

    id = Column(Integer, primary_key=True, index=True)
    название = Column(String(255), nullable=False)
    линия = Column(String(100), nullable=False)
    информация_о_пересадках = Column(
        JSON,
        nullable=False,
        server_default='{"связанные_станции": [], "время_пересадки": 0}'
    )

    # Связи
    сотрудники = relationship("Employee", back_populates="текущая_станция")
    заявки_отправления = relationship("Request", foreign_keys="Request.станция_отправления_id",
                                      back_populates="станция_отправления")
    заявки_назначения = relationship("Request", foreign_keys="Request.станция_назначения_id",
                                     back_populates="станция_назначения")
    связи_отправления = relationship("StationConnection", foreign_keys="StationConnection.станция_отправления_id",
                                     back_populates="станция_отправления")
    связи_назначения = relationship("StationConnection", foreign_keys="StationConnection.станция_назначения_id",
                                    back_populates="станция_назначения")


class Employee(Base):
    __tablename__ = 'employees'

    id = Column(Integer, primary_key=True, index=True)
    фио = Column(String(255), nullable=False)
    текущая_станция_id = Column(Integer, ForeignKey('stations.id'))
    статус = Column(
        String(50),
        nullable=False,
        server_default='доступен'
    )
    навыки = Column(
        JSON,
        nullable=False,
        server_default='{"языки": ["рус"], "работает_с_колясками": false}'
    )
    график = Column(
        JSON,
        nullable=False,
        server_default='{"смена": "", "рабочие_дни": []}'
    )
    создано = Column(DateTime(timezone=True), server_default='now()')
    обновлено = Column(DateTime(timezone=True), server_default='now()', onupdate=datetime.now)

    # Связи
    текущая_станция = relationship("Station", back_populates="сотрудники")
    заявки = relationship("EmployeeRequest", back_populates="сотрудник")

    __table_args__ = (
        CheckConstraint(
            "статус IN ('доступен', 'назначен', 'не на смене')",
            name='check_employee_status'
        ),
    )


class Request(Base):
    __tablename__ = 'requests'

    id = Column(Integer, primary_key=True, index=True)
    тип_пассажира = Column(String(50), nullable=False)
    станция_отправления_id = Column(Integer, ForeignKey('stations.id'), nullable=False)
    станция_назначения_id = Column(Integer, ForeignKey('stations.id'), nullable=False)
    требуемые_сотрудники = Column(Integer, nullable=False)
    статус = Column(String(50), nullable=False, server_default='новая')
    багаж = Column(Boolean, nullable=False, server_default='false')
    запрошенное_время = Column(DateTime(timezone=True), nullable=False)
    расчетное_время_выполнения = Column(Integer)
    создано = Column(DateTime(timezone=True), server_default='now()')
    обновлено = Column(DateTime(timezone=True), server_default='now()', onupdate=datetime.now)

    # Связи
    станция_отправления = relationship(
        "Station",
        foreign_keys=[станция_отправления_id],
        back_populates="заявки_отправления"
    )
    станция_назначения = relationship(
        "Station",
        foreign_keys=[станция_назначения_id],
        back_populates="заявки_назначения"
    )
    сотрудники = relationship("EmployeeRequest", back_populates="заявка")

    __table_args__ = (
        CheckConstraint(
            "тип_пассажира IN ('слабовидящий', 'колясочник')",
            name='check_passenger_type'
        ),
        CheckConstraint(
            "статус IN ('новая', 'назначена', 'в процессе', 'завершена', 'отменена')",
            name='check_request_status'
        ),
        CheckConstraint(
            "требуемые_сотрудники > 0",
            name='check_required_workers'
        ),
        CheckConstraint(
            "станция_отправления_id != станция_назначения_id",
            name='check_different_stations'
        ),
    )


class Incident(Base):
    __tablename__ = 'incidents'

    id = Column(Integer, primary_key=True, index=True)
    тип = Column(String(100), nullable=False)
    затронутые_станции = Column(JSON, nullable=False, server_default='[]')
    серьезность = Column(Integer, nullable=False)
    время_начала = Column(DateTime(timezone=True), nullable=False)
    время_окончания = Column(DateTime(timezone=True))
    описание = Column(Text)
    создано = Column(DateTime(timezone=True), server_default='now()')
    обновлено = Column(DateTime(timezone=True), server_default='now()', onupdate=datetime.now)

    __table_args__ = (
        CheckConstraint(
            "тип IN ('задержка', 'отмена', 'изменение маршрута')",
            name='check_incident_type'
        ),
        CheckConstraint(
            "серьезность BETWEEN 1 AND 5",
            name='check_severity_range'
        ),
    )


class StationConnection(Base):
    __tablename__ = 'station_connections'

    id = Column(Integer, primary_key=True, index=True)
    станция_отправления_id = Column(Integer, ForeignKey('stations.id'), nullable=False)
    станция_назначения_id = Column(Integer, ForeignKey('stations.id'), nullable=False)
    время_в_пути = Column(Integer, nullable=False)
    создано = Column(DateTime(timezone=True), server_default='now()')
    обновлено = Column(DateTime(timezone=True), server_default='now()', onupdate=datetime.now)

    # Связи
    станция_отправления = relationship(
        "Station",
        foreign_keys=[станция_отправления_id],
        back_populates="связи_отправления"
    )
    станция_назначения = relationship(
        "Station",
        foreign_keys=[станция_назначения_id],
        back_populates="связи_назначения"
    )

    __table_args__ = (
        CheckConstraint(
            "время_в_пути > 0",
            name='check_travel_time_positive'
        ),
        CheckConstraint(
            "станция_отправления_id != станция_назначения_id",
            name='check_different_connection_stations'
        ),
    )


class EmployeeRequest(Base):
    __tablename__ = 'employee_requests'

    сотрудник_id = Column(Integer, ForeignKey('employees.id'), primary_key=True)
    заявка_id = Column(Integer, ForeignKey('requests.id'), primary_key=True)
    создано = Column(DateTime(timezone=True), server_default='now()')

    # Связи
    сотрудник = relationship("Employee", back_populates="заявки")
    заявка = relationship("Request", back_populates="сотрудники")


Base.metadata.create_all(bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)