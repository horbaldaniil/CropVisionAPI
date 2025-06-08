from sqlalchemy import Column, Integer, String, Text, DateTime, func
from .database import Base


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    full_name = Column(String(100), nullable=False)
    email = Column(String(100), unique=True, nullable=False, index=True)
    password_hash = Column(Text)
    created_at = Column(DateTime, nullable=False, server_default=func.now())


class CropDescription(Base):
    __tablename__ = "crop_description"
    id = Column(Integer, primary_key=True, index=True)
    class_name = Column(String(100), unique=True, index=True)
    crop_name = Column(String(100), index=True)
    crop_description = Column(Text)
    disease_name = Column(String(100), nullable=True)
    disease_description = Column(Text, nullable=True)
    care_description = Column(Text)

    def __repr__(self):
        return f"<CropDisease(class_name='{self.class_name}', crop_name='{self.crop_name}', disease_name='{self.disease_name}')>"
