from typing import List, Dict

import numpy as np
import cv2
import torch
from fastapi import APIRouter, UploadFile, File, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from db.database import get_db
from db.models import CropDescription
from schemas.cropdiseases import DetectionResult

router = APIRouter()

# Спроба №1: офіційна бібліотека ultralytics
try:
    from ultralytics import YOLO
    model = YOLO('best.pt')
    class_names = model.names if hasattr(model, 'names') else model.model.names

# Спроба №2: fallback через torch.hub
except ImportError:
    try:
        model = torch.hub.load(
            "ultralytics/ultralytics",
            "custom",
            path="best.pt",
            force_reload=False
        )
        class_names = model.names
    except Exception as e:
        raise RuntimeError(f"Не вдалося завантажити модель через torch.hub: {e}")
except Exception as e:
    raise RuntimeError(f"Не вдалося завантажити модель: {e}")


# ----------------------------------------------------------------------------
# Допоміжні функції
# ----------------------------------------------------------------------------

def predict_image(image_bytes: bytes) -> List[Dict]:
    """Виконує інференс моделі **YOLO** для одного зображення.

        Пайплайн:
        1. ``bytes → np.ndarray`` через ``np.frombuffer`` (zero‑copy).
        2. Декодування JPEG/PNG у BGR‑тензор OpenCV (`cv2.imdecode`).
        3. Конвертація ``BGR → RGB`` — Ultralytics очікує RGB‑вхід.
        4. Виклик ``model()`` → отримання результатів першого батчу.
        5. Уніфікація формату результуючих боксових класифікацій
           (Ultralytics v8 / v9 мають різні API).

        Parameters
        ----------
        image_bytes : bytes
            Сирі байти зображення (отримуємо з FastAPI ``UploadFile``).

        Returns
        -------
        list[dict]
            Перелік детекцій у форматі ``{"class": str, "confidence": float}``.

        Raises
        ------
        ValueError
            Якщо файл не вдалося декодувати або формат виводу моделі
            невідомий.
    """
    # --- 1–2. bytes → ndarray, перевірка декодування ------------------------
    nparr = np.frombuffer(image_bytes, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError("Не вдалося декодувати зображення")

    # --- 3. BGR → RGB -------------------------------------------------------
    img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)

    # --- 4. Інференс --------------------------------------------------------
    results = model(img_rgb)
    res0 = results[0] if isinstance(results, (list, tuple)) else results

    # --- 5. Парсинг результатів --------------------------------------------
    detections: List[Dict] = []
    if hasattr(res0, 'boxes'):
        try:
            cls_tensor = res0.boxes.cls.cpu().numpy().astype(int)
            conf_tensor = res0.boxes.conf.cpu().numpy()
            for cls_id, conf in zip(cls_tensor, conf_tensor):
                label = class_names.get(cls_id, str(cls_id))
                detections.append({'class': label, 'confidence': float(conf)})
        except Exception:
            if hasattr(res0.boxes, 'data'):
                data = res0.boxes.data.cpu().numpy().tolist()
                for *_, conf, cls in data:
                    cls_id = int(cls)
                    label = class_names.get(cls_id, str(cls_id))
                    detections.append({'class': label, 'confidence': float(conf)})
    elif hasattr(results, 'xyxy'):
        for *_, conf, cls in results.xyxy[0].tolist():
            cls_id = int(cls)
            label = class_names.get(cls_id, str(cls_id))
            detections.append({'class': label, 'confidence': float(conf)})
    else:
        raise ValueError("Невідомий формат результатів моделі")
    return detections


# ----------------------------------------------------------------------------
# REST‑ендпоінти
# ----------------------------------------------------------------------------

@router.post("/predict", response_model=DetectionResult)
async def predict_route(
    file: UploadFile = File(..., description="Зображення рослини для аналізу"),
    db: AsyncSession = Depends(get_db)
):
    """HTTP‑ендпоінт для аналізу зображення та збагачення детекції метаданими.

        Workflow
        --------
        1. **Валідація вхідного файлу** — читаємо байти та перевіряємо, що вони не
           порожні.
        2. **Інференс YOLO** — викликаємо :pyfunc:`predict_image`.
        3. **Пост‑процесинг** — вибираємо найвпевненіший клас, отримуємо детальну
           інформацію про культуру та хворобу з PostgreSQL.
        4. **Формування відповіді** — повертаємо схему :class:`DetectionResult`.

        Raises
        ------
        HTTPException
            400 — некоректне зображення чи неможливо декодувати;
            404 — модель не виявила об’єкт або відсутні метадані для класу;
            500 — внутрішня помилка інференсу.
    """
    image_bytes = await file.read()
    if not image_bytes:
        raise HTTPException(status_code=400, detail="Не вдалося прочитати зображення")

    # Інференс
    try:
        preds = predict_image(image_bytes)
        print("preds", preds)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Помилка inference: {e}")

    if not preds:
        raise HTTPException(status_code=404, detail="Об'єкт не виявлено")

    top = max(preds, key=lambda x: x['confidence'])
    class_name = top['class']
    confidence = top['confidence']
    print(confidence)

    result = await db.execute(select(CropDescription).where(CropDescription.class_name == class_name))
    record = result.scalar_one_or_none()
    if not record:
        raise HTTPException(status_code=404, detail="Дані для класу не знайдено")

    print(record.disease_name)
    return DetectionResult(
        crop_name=record.crop_name,
        crop_description=record.crop_description,
        disease_name=record.disease_name,
        disease_description=record.disease_description,
        care_description=record.care_description,
        confidence=confidence
    )
