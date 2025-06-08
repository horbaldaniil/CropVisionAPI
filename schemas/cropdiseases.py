from pydantic import BaseModel, ConfigDict
from typing import Optional, List

class CropDescriptionBase(BaseModel):
    crop_name: str
    crop_description: str
    disease_name: Optional[str] = None
    disease_description: Optional[str] = None  # Може бути None, якщо хвороби немає
    care_description: str

    confidence: float

    model_config = ConfigDict(from_attributes=True)

# Схема вихідних даних (для клієнта, мобільного додатку)
class DetectionResult(CropDescriptionBase):
    pass

# Схема для створення нового запису в БД
class CropDiseaseCreate(CropDescriptionBase):
    class_name: str  # Додаємо поле class_name для створення запису
