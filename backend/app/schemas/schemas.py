from pydantic import BaseModel, EmailStr, field_validator
from datetime import date, datetime
from typing import Optional, List

# Parent Schemas
class ParentBase(BaseModel):
    first_name: str
    last_name: str
    email: EmailStr

class ParentCreate(ParentBase):
    password: str

class ParentRead(ParentBase):
    id: int
    tenant_id: str
    created_at: Optional[datetime] = None
    class Config:
        from_attributes = True

class Parent(ParentBase):
    id: int
    tenant_id: str
    class Config:
        from_attributes = True

# Child Schemas
class ChildBase(BaseModel):
    first_name: str
    last_name: str
    birthdate: Optional[date] = None
    email: Optional[EmailStr] = None
    pin: Optional[str] = None

class ChildCreate(ChildBase):
    pass

class ChildRead(ChildBase):
    id: int
    tenant_id: str
    parent_id: int
    device_id: Optional[int] = None
    access_level: str = "full"
    banked_hours: int = 0
    previous_grade_average: Optional[str] = None
    created_at: Optional[datetime] = None
    class Config:
        from_attributes = True

class Child(ChildBase):
    id: int
    tenant_id: str
    parent_id: int
    device_id: Optional[int] = None
    access_level: str = "full"
    banked_hours: int = 0
    previous_grade_average: Optional[str] = None
    class Config:
        from_attributes = True

# Device Schemas
class DeviceBase(BaseModel):
    name: str
    device_type: str = "laptop"
    ip_address: Optional[str] = None
    mac_address: Optional[str] = None

class DeviceCreate(DeviceBase):
    pass

class DeviceRead(DeviceBase):
    id: int
    tenant_id: str
    child_id: Optional[int] = None
    wg_public_key: Optional[str] = None
    is_active: bool = True
    created_at: Optional[datetime] = None
    class Config:
        from_attributes = True

class Device(DeviceBase):
    id: int
    tenant_id: str
    child_id: Optional[int] = None
    class Config:
        from_attributes = True

# GradeSync Schemas
class GradeSyncBase(BaseModel):
    child_id: int
    subject: str
    grade: str
    grade_date: Optional[date] = None

class GradeSyncCreate(GradeSyncBase):
    pass

class GradeSyncRead(GradeSyncBase):
    id: int
    tenant_id: str
    synced_at: Optional[datetime] = None
    class Config:
        from_attributes = True

class GradeSync(GradeSyncBase):
    id: int
    tenant_id: str
    class Config:
        from_attributes = True

# Chore Schemas
class ChoreBase(BaseModel):
    child_id: int
    name: str
    description: Optional[str] = None
    due_date: Optional[date] = None
    reward_points: int = 0

class ChoreCreate(ChoreBase):
    pass

class ChoreRead(ChoreBase):
    id: int
    tenant_id: str
    is_completed: bool = False
    completed_at: Optional[datetime] = None
    verified_by_parent: bool = False
    created_at: Optional[datetime] = None
    class Config:
        from_attributes = True

class Chore(ChoreBase):
    id: int
    tenant_id: str
    is_completed: bool = False
    class Config:
        from_attributes = True

# Precommitment Schemas
class PrecommitmentBase(BaseModel):
    child_id: int
    cooling_off_hours: int = 24
    strict_mode_enabled: bool = False
    accountability_partner_email: Optional[str] = None

class PrecommitmentCreate(PrecommitmentBase):
    pass

class PrecommitmentRead(PrecommitmentBase):
    id: int
    tenant_id: str
    created_at: Optional[datetime] = None
    class Config:
        from_attributes = True

class Precommitment(PrecommitmentBase):
    id: int
    tenant_id: str
    class Config:
        from_attributes = True

# AccessTier schemas
class AccessTierBase(BaseModel):
    name: str
    description: Optional[str] = None
    features: Optional[str] = None

class AccessTierCreate(AccessTierBase):
    pass

class AccessTierRead(AccessTierBase):
    id: int
    tenant_id: str
    created_at: Optional[datetime] = None
    class Config:
        from_attributes = True

class AccessTier(AccessTierBase):
    id: int
    tenant_id: str
    class Config:
        from_attributes = True

# Auth schemas
class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"

class LoginRequest(BaseModel):
    email: EmailStr
    password: str