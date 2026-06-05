from sqlalchemy import Column, Integer, String, Date, ForeignKey, Boolean, Text, DateTime, func
from sqlalchemy.orm import relationship, declarative_base

Base = declarative_base()

class Parent(Base):
    __tablename__ = 'parents'
    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(String, index=True, nullable=False)
    email = Column(String, unique=True, index=True)
    hashed_password = Column(String, nullable=False)
    first_name = Column(String)
    last_name = Column(String)
    created_at = Column(DateTime, server_default=func.now())
    children = relationship("Child", back_populates="parent", cascade="all, delete-orphan")

class Child(Base):
    __tablename__ = 'children'
    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(String, index=True, nullable=False)
    first_name = Column(String)
    last_name = Column(String)
    birthdate = Column(Date, nullable=True)
    email = Column(String, nullable=True)
    parent_id = Column(Integer, ForeignKey('parents.id'))
    access_level = Column(String, default="full")  # full, limited, research-only
    created_at = Column(DateTime, server_default=func.now())
    parent = relationship("Parent", back_populates="children")
    grades = relationship("GradeSync", back_populates="child", cascade="all, delete-orphan")
    chores = relationship("Chore", back_populates="child", cascade="all, delete-orphan")
    precommitments = relationship("Precommitment", back_populates="child", cascade="all, delete-orphan")

class Device(Base):
    __tablename__ = 'devices'
    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(String, index=True, nullable=False)
    name = Column(String)
    device_type = Column(String, default="laptop")
    ip_address = Column(String, nullable=True)
    mac_address = Column(String, nullable=True)
    wg_public_key = Column(String, nullable=True)
    is_active = Column(Boolean, default=True)
    child_id = Column(Integer, ForeignKey('children.id'), nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    child = relationship("Child", backref="device", uselist=False)

class GradeSync(Base):
    __tablename__ = 'grades'
    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(String, index=True, nullable=False)
    child_id = Column(Integer, ForeignKey('children.id'))
    subject = Column(String)
    grade = Column(String)
    grade_date = Column(Date, nullable=True)
    synced_at = Column(DateTime, server_default=func.now())
    child = relationship("Child", back_populates="grades")

class Chore(Base):
    __tablename__ = 'chores'
    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(String, index=True, nullable=False)
    child_id = Column(Integer, ForeignKey('children.id'))
    name = Column(String)
    description = Column(Text, nullable=True)
    due_date = Column(Date, nullable=True)
    is_completed = Column(Boolean, default=False)
    completed_at = Column(DateTime, nullable=True)
    verified_by_parent = Column(Boolean, default=False)
    reward_points = Column(Integer, default=0)
    created_at = Column(DateTime, server_default=func.now())
    child = relationship("Child", back_populates="chores")

class Precommitment(Base):
    __tablename__ = 'precommitments'
    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(String, index=True, nullable=False)
    child_id = Column(Integer, ForeignKey('children.id'))
    cooling_off_hours = Column(Integer, default=24)
    strict_mode_enabled = Column(Boolean, default=False)
    strict_mode_locked_until = Column(DateTime, nullable=True)
    accountability_partner_email = Column(String, nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    child = relationship("Child", back_populates="precommitments")

class AccessTier(Base):
    __tablename__ = 'access_tiers'
    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(String, index=True, nullable=False)
    name = Column(String)
    description = Column(Text, nullable=True)
    features = Column(Text, nullable=True)
    created_at = Column(DateTime, server_default=func.now())

class EdsbyConfig(Base):
    __tablename__ = 'edsby_configs'
    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(String, index=True, nullable=False)
    parent_id = Column(Integer, ForeignKey('parents.id'))
    base_url = Column(String, nullable=True)
    username = Column(String, nullable=True)
    password_encrypted = Column(String, nullable=True)
    is_active = Column(Boolean, default=False)
    last_synced_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, server_default=func.now())

class Counselor(Base):
    __tablename__ = 'counselors'
    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(String, index=True, nullable=False, default='default')
    name = Column(String, nullable=False)
    specialty = Column(String, nullable=True)
    location = Column(String, nullable=True)
    accepts_ohip = Column(Boolean, default=False)
    accepts_insurance = Column(Boolean, default=False)
    phone = Column(String, nullable=True)
    email = Column(String, nullable=True)
    is_verified = Column(Boolean, default=False)
    created_at = Column(DateTime, server_default=func.now())