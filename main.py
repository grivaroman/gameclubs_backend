from fastapi import FastAPI, Request, Form, Depends, HTTPException, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
import models  # Используем твой существующий скрипт

app = FastAPI(title="CyberBooking System")
models.Base.metadata.create_all(bind=models.engine)
templates = Jinja2Templates(directory="templates")

# Подключение к БД
def get_db():
    db = models.SessionLocal()
    try:
        yield db
    finally:
        db.close()

# --- АВТОРИЗАЦИЯ (ИСПРАВЛЕННАЯ) ---

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return RedirectResponse(url="/login")

@app.get("/register", response_class=HTMLResponse)
async def register_page(request: Request):
    return templates.TemplateResponse("register.html", {"request": request})

@app.post("/register")
async def register_action(
    email: str = Form(...), 
    password: str = Form(...), 
    role: str = Form(...),  # Добавили получение роли из формы
    phone: str = Form(None), # Получаем телефон (может быть пустым)
    db: Session = Depends(get_db)
):
    email_clean = email.strip().lower()
    
    # Проверяем, не занята ли почта
    existing = db.query(models.User).filter(models.User.email == email_clean).first()
    if existing:
        return HTMLResponse("Email уже занят", status_code=400)

    # Создаем пользователя с той ролью, которую он ВЫБРАЛ в форме
    new_user = models.User(
        email=email_clean,
        hashed_password=password,
        role=role,   # Берем 'admin' или 'user' из выпадающего списка
        phone=phone
    )
    
    db.add(new_user)
    db.commit()
    
    print(f">>> РЕГИСТРАЦИЯ: Создан {role}: {email_clean}")
    
    return RedirectResponse(url="/login", status_code=303)



@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})

@app.post("/login")
async def login_action(
    email: str = Form(...), 
    password: str = Form(...), 
    db: Session = Depends(get_db)
):
    # 1. Очищаем email и ищем пользователя
    email_clean = email.strip().lower()
    user = db.query(models.User).filter(models.User.email == email_clean).first()
    
    # 2. Проверяем пароль (сверяем с hashed_password из твоей модели)
    if not user or user.hashed_password != password:
        return HTMLResponse("Неверный логин или пароль", status_code=401)
    
    # 3. ЛОГИКА ПЕРЕНАПРАВЛЕНИЯ ПО РОЛИ
    # Мы смотрим на значение, которое пришло из базы (admin или user)
    if user.role == "admin":
        print(f">>> ВХОД: Админ {email_clean} опознан. Перенаправляем в админку.")
        return RedirectResponse(url="/admin", status_code=303)
    else:
        print(f">>> ВХОД: Пользователь {email_clean} опознан. Перенаправляем в дашборд.")
        return RedirectResponse(url="/user/dashboard", status_code=303)

# --- WEB МАРШРУТЫ (ПОЛЬЗОВАТЕЛЬ) ---

# Убедись, что путь именно такой: "/book_seat/{pc_id}"
@app.post("/book_seat/{pc_id}")
async def book_seat(pc_id: int, db: Session = Depends(get_db)):
    # Ищем компьютер в базе
    pc = db.query(models.Computer).filter(models.Computer.id == pc_id).first()
    
    if not pc:
        return {"status": "error", "message": "Компьютер не найден"}
    
    if pc.status != "free":
        return {"status": "error", "message": "Место уже занято"}

    # Меняем статус
    pc.status = "busy"
    db.commit()
    
    print(f">>> БРОНЬ: Компьютер №{pc.number} теперь занят")
    return {"status": "success", "message": "Забронировано!"}


@app.get("/user/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request, db: Session = Depends(get_db)):
    clubs = db.query(models.Club).all()
    return templates.TemplateResponse("user_dashboard.html", {"request": request, "clubs": clubs})

@app.get("/club/{club_id}", response_class=HTMLResponse)
async def club_detail(club_id: int, request: Request, db: Session = Depends(get_db)):
    club = db.query(models.Club).get(club_id)
    if not club:
        return HTMLResponse("Клуб не найден", status_code=404)

    computers = db.query(models.Computer).filter(models.Computer.club_id == club_id).order_by(models.Computer.number).all()
    products = db.query(models.Product).filter(models.Product.club_id == club_id).all()

    return templates.TemplateResponse("club_detail.html", {
        "request": request, 
        "club": club, 
        "computers": computers, 
        "products": products
    })

# --- АДМИН-ПАНЕЛЬ ---
# --- АДМИН-ПАНЕЛЬ: ГЛАВНАЯ ---
@app.get("/admin", response_class=HTMLResponse)
async def admin_page(request: Request, db: Session = Depends(get_db)):
    clubs = db.query(models.Club).all()
    all_games = db.query(models.Game).all()
    # Добавим заказы, чтобы админ видел, кто что купил
    orders = db.query(models.Order).all() 
    return templates.TemplateResponse("admin.html", {
        "request": request, 
        "clubs": clubs, 
        "all_games": all_games,
        "orders": orders
    })

# --- ДОБАВЛЕНИЕ КЛУБА ---
@app.post("/admin/add_club")
async def add_club(name: str = Form(...), address: str = Form(...), db: Session = Depends(get_db)):
    db.add(models.Club(name=name, address=address))
    db.commit()
    return RedirectResponse(url="/admin", status_code=303)

# --- ДОБАВЛЕНИЕ КОМПЬЮТЕРОВ (С ЦЕНОЙ И КАТЕГОРИЕЙ) ---
@app.post("/admin/add_computers")
async def add_computers(
    club_id: int = Form(...), 
    count: int = Form(...), 
    category: str = Form(...), 
    db: Session = Depends(get_db)
):
    total_existing = db.query(models.Computer).filter(models.Computer.club_id == club_id).count()
    
    # Логика прайса: можно захардкодить или брать из формы
    # Например: VIP - 1500тг, Standard - 800тг
    for i in range(1, count + 1):
        new_pc = models.Computer(
            number=total_existing + i,
            category=category,
            club_id=club_id,
            status="free"
        )
        db.add(new_pc)
    
    db.commit()
    return RedirectResponse(url="/admin", status_code=303)

# --- ДОБАВЛЕНИЕ ТОВАРА (ТЕПЕРЬ С ФОТО) ---
@app.post("/admin/add_product")
async def add_product(
    club_id: int = Form(...), 
    name: str = Form(...), 
    price: int = Form(...), 
    image_url: str = Form(None), # Ссылка на фото
    db: Session = Depends(get_db)
):
    # Убедись, что в models.py у Product есть поле image_url
    db.add(models.Product(name=name, price=price, image_url=image_url, club_id=club_id))
    db.commit()
    return RedirectResponse(url="/admin", status_code=303)

# --- ДОБАВЛЕНИЕ ИГРЫ ---
@app.post("/admin/add_game")
async def add_game(name: str = Form(...), db: Session = Depends(get_db)):
    db.add(models.Game(name=name))
    db.commit()
    return RedirectResponse(url="/admin", status_code=303)

# --- ПОКУПКА ТОВАРА (ДЛЯ ЮЗЕРА) ---
@app.post("/buy_product/{product_id}")
async def buy_product(product_id: int, db: Session = Depends(get_db)):
    # В идеале тут нужен current_user.id из сессии
    # Для теста берем первого попавшегося юзера
    user = db.query(models.User).first()
    if not user:
        return {"status": "error", "message": "Сначала зарегистрируйтесь"}
        
    new_order = models.Order(user_id=user.id, product_id=product_id, status="new")
    db.add(new_order)
    db.commit()
    return {"status": "success", "message": "Заказ принят, ожидайте доставку к компу!"}