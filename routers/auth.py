from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from db.database import get_db
from db.models import User
from schemas.users import UserCreate, UserLogin, GoogleAuth, UserRead, Token
from core import security
import jwt
from jwt import PyJWTError
from fastapi import Response

from db.database import get_db
from db.models import User
from core.config import settings
from core.security import oauth2_scheme

router = APIRouter()

async def get_current_user(token: str = Depends(oauth2_scheme), db: AsyncSession = Depends(get_db)):
    """
        Витягує поточного аутентифікованого користувача з JWT‑токену.

        Parameters
        ----------
        token : str
            JWT access token, що передається в заголовку `Authorization: Bearer <token>`.
        db : AsyncSession
            Асинхронна сесія SQLAlchemy для запитів до бази даних.

        Returns
        -------
        User
            ORM‑екземпляр користувача, що відповідає полю `sub` у токені.

        Raises
        ------
        HTTPException
            401 UNAUTHORIZED — якщо токен недійсний, протермінований або користувача не знайдено.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Не вдалося верифікувати креденшіали",
        headers={"WWW-Authenticate": "Bearer"}
    )
    try:
        # Розшифрування та перевірка підпису токена
        payload = jwt.decode(token, settings.secret_key, algorithms=[settings.jwt_algorithm])
        user_email: str = payload.get("sub")
        if user_email is None:
            raise credentials_exception
    except jwt.ExpiredSignatureError:  # Термін дії токена минув
        raise HTTPException(status_code=401, detail="Токен протух (expired)", headers={"WWW-Authenticate": "Bearer"})
    except PyJWTError: # Інші помилки декодування/верифікації
        raise credentials_exception

    # Шукаємо користувача в БД
    result = await db.execute(
        User.__table__.select().where(User.email == user_email)
    )
    user_record = result.fetchone()
    if user_record is None:
        raise credentials_exception
    return user_record

@router.delete("/delete", status_code=204)
async def delete_user(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
        Видаляє профіль поточного користувача та всі пов'язані записи.

        Ідентифікація користувача відбувається через JWT‑токен.
        Повертає HTTP 204 No Content у разі успішного видалення.
    """
    await db.execute(
        User.__table__.delete().where(User.email == current_user.email)
    )
    await db.commit()
    return Response(status_code=204)

@router.post("/register", response_model=Token)
async def register_user(user_data: UserCreate, db: AsyncSession = Depends(get_db)):
    """
        Реєструє нового користувача та повертає access‑токен.

        - Перевіряє унікальність email.
        - Хешує пароль за допомогою `bcrypt`.
        - Створює запис у БД та повертає JWT разом з метаданими користувача.
    """

    # Перевірка дублю email
    result = await db.execute(User.__table__.select().where(User.email == user_data.email))
    existing = result.first()
    if existing:
        raise HTTPException(status_code=400, detail="Користувач з таким email вже існує")

    password_hash = security.hash_password(user_data.password)

    new_user = User(full_name=user_data.full_name, email=user_data.email, password_hash=password_hash)
    db.add(new_user)
    await db.commit()
    await db.refresh(new_user)

    access_token = security.create_access_token({"sub": new_user.email})
    return {
    "access_token": access_token,
    "token_type": "bearer",
    "user": {
        "id": new_user.id,
        "full_name": new_user.full_name,
        "email": new_user.email,
        "created_at": new_user.created_at
        }
    }


@router.post("/login", response_model=Token)
async def login_user(login_data: UserLogin, db: AsyncSession = Depends(get_db)):
    """
        Логін користувача через email/пароль.

        - Перевіряє чи існує користувач у БД.
        - Валідує пароль за допомогою `security.verify_password`.
        - Генерує та повертає новий access‑токен.
    """
    result = await db.execute(User.__table__.select().where(User.email == login_data.email))
    user_row = result.first()
    if not user_row or not security.verify_password(login_data.password, user_row.password_hash):
        raise HTTPException(status_code=401, detail="Невірний email або пароль")

    user = user_row._mapping
    access_token = security.create_access_token({"sub": user["email"]})
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user": {
            "full_name": user["full_name"],
            "email": user["email"],
            "id": user["id"],
            "created_at": user["created_at"]
        }
    }
