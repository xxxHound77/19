import shutil
from pathlib import Path
import pandas as pd
import calendar
from datetime import datetime

from db import connect, init_db, ensure_lookup, scalar

BASE_DIR = Path(__file__).resolve().parent
IMPORT_DIR = BASE_DIR / "assets" / "import"
IMAGES_DIR = BASE_DIR / "assets" / "images"


def _copy_if_missing(src: Path, dst: Path) -> None:
    """Копирует файл, если назначения ещё не существует; создаёт промежуточные папки."""
    dst.parent.mkdir(parents=True, exist_ok=True)
    if not dst.exists() and src.exists():
        shutil.copy2(src, dst)


def _find_file(patterns):
    """Возвращает первый существующий файл из переданного списка путей."""
    for p in patterns:
        if p.exists():
            return p
    return None


def seed() -> None:
    """Инициализирует БД и импортирует начальные данные из файлов Excel.

    Поиск файлов выполняется по разным вариантам имён (включая Unicode-экранированные),
    чтобы обойти возможные проблемы с кодировкой в файловой системе.
    """
    init_db()
    conn = connect()
    try:
        # Справочник ролей пользователей
        conn.executemany(
            "INSERT OR IGNORE INTO Roles(RoleId, RoleName) VALUES (?,?)",
            [
                (1, "Администратор"),
                (2, "Менеджер"),
                (3, "Авторизированный клиент"),
            ],
        )

        # Справочник статусов заказов
        conn.executemany(
            "INSERT OR IGNORE INTO OrderStatuses(StatusName) VALUES (?)",
            [("Новый",), ("Завершен",), ("В обработке",), ("Отменен",)],
        )

        # Импорт пользователей из user_import.xlsx
        users_file = _find_file([
            IMPORT_DIR / "user_import.xlsx",
        ])
        if users_file and users_file.exists():
            dfu = pd.read_excel(users_file)
            for _, r in dfu.iterrows():
                role = str(r["Роль сотрудника"]).strip()
                role_id = scalar(conn, "SELECT RoleId FROM Roles WHERE RoleName=?", (role,))
                if role_id is None:
                    continue
                conn.execute(
                    """
                    INSERT OR IGNORE INTO Users(FullName, Login, Password, RoleId)
                    VALUES (?,?,?,?)
                    """,
                    (str(r["ФИО"]).strip(), str(r["Логин"]).strip(), str(r["Пароль"]).strip(), int(role_id)),
                )

        # Импорт пунктов выдачи с поддержкой разных вариантов имён файлов
        pp_file = _find_file([
            IMPORT_DIR / "Пункты выдачи_import.xlsx",
            IMPORT_DIR / "#U041f#U0443#U043d#U043a#U0442#U044b #U0432#U044b#U0434#U0430#U0447#U0438_import.xlsx",
        ])
        if pp_file and pp_file.exists():
            try:
                dfpp = pd.read_excel(pp_file, header=None)
            except Exception:
                dfpp = pd.read_excel(pp_file)
            # берем первый столбец
            col = dfpp.columns[0]
            for addr in dfpp[col].dropna().astype(str).map(str.strip).tolist():
                if addr:
                    conn.execute("INSERT OR IGNORE INTO PickupPoints(Address) VALUES (?)", (addr,))

        # Импорт товаров: справочники (поставщик, производитель, категория, ед. изм.) создаются автоматически
        products_file = _find_file([
            IMPORT_DIR / "Tovar.xlsx",
        ])
        if products_file and products_file.exists():
            dfp = pd.read_excel(products_file)
            for _, r in dfp.iterrows():
                supplier_id = ensure_lookup(conn, "Suppliers", "SupplierName", str(r["Поставщик"]).strip())
                manufacturer_id = ensure_lookup(conn, "Manufacturers", "ManufacturerName", str(r["Производитель"]).strip())
                category_id = ensure_lookup(conn, "Categories", "CategoryName", str(r["Категория товара"]).strip())
                unit_id = ensure_lookup(conn, "Units", "UnitName", str(r["Единица измерения"]).strip())

                photo_name = str(r.get("Фото", "") or "").strip()
                photo_rel = None
                if photo_name:
                    # пробуем точное совпадение, иначе с другим регистром расширения
                    src = IMPORT_DIR / photo_name
                    if not src.exists():
                        for cand in IMPORT_DIR.glob(photo_name + "*"):
                            src = cand
                            break
                    dst = IMAGES_DIR / (src.name if src.exists() else photo_name)
                    _copy_if_missing(src, dst)
                    if dst.exists():
                        photo_rel = str(Path("assets/images") / dst.name)

                conn.execute(
                    """
                    INSERT OR IGNORE INTO Products(
                        Article, ProductName, Description, CategoryId, ManufacturerId, SupplierId,
                        UnitId, Price, DiscountPercent, StockQty, PhotoPath
                    )
                    VALUES (?,?,?,?,?,?,?,?,?,?,?)
                    """,
                    (
                        str(r["Артикул"]).strip(),
                        str(r["Наименование товара"]).strip(),
                        str(r.get("Описание товара", "") or "").strip(),
                        category_id,
                        manufacturer_id,
                        supplier_id,
                        unit_id,
                        float(r["Цена"]),
                        float(r["Действующая скидка"]),
                        int(r["Кол-во на складе"]),
                        photo_rel,
                    ),
                )

        # Импорт заказов: данные клиентов и статусы подтягиваются из БД, товары заказа парсятся по артикулам и количествам
        orders_file = _find_file([
            IMPORT_DIR / "Заказ_import.xlsx",
            IMPORT_DIR / "#U0417#U0430#U043a#U0430#U0437_import.xlsx",
        ])
        if orders_file and orders_file.exists():
            dfo = pd.read_excel(orders_file)

            def safe_iso_date(value) -> str:
                try:
                    return pd.to_datetime(value).date().isoformat()
                except Exception:
                    s = str(value).strip()
                    try:
                        d = datetime.strptime(s, "%d.%m.%Y")
                        return d.date().isoformat()
                    except Exception:
                        try:
                            dd, mm, yy = [int(x) for x in s.split(".")]
                            last_day = calendar.monthrange(yy, mm)[1]
                            dd = min(dd, last_day)
                            return datetime(yy, mm, dd).date().isoformat()
                        except Exception:
                            return "1970-01-01"

            for _, r in dfo.iterrows():
                status_name = str(r["Статус заказа"]).strip()
                status_id = scalar(conn, "SELECT StatusId FROM OrderStatuses WHERE StatusName=?", (status_name,))
                if status_id is None:
                    status_id = ensure_lookup(conn, "OrderStatuses", "StatusName", status_name)

                pp_id = int(r["Адрес пункта выдачи"])

                customer_name = str(r["ФИО авторизированного клиента"]).strip()
                customer_id = scalar(conn, "SELECT UserId FROM Users WHERE FullName=?", (customer_name,))

                conn.execute(
                    """
                    INSERT OR IGNORE INTO Orders(
                        OrderNumber, OrderDate, DeliveryDate, PickupPointId,
                        CustomerUserId, ReceiveCode, StatusId
                    ) VALUES (?,?,?,?,?,?,?)
                    """,
                    (
                        int(r["Номер заказа"]),
                        safe_iso_date(r["Дата заказа"]),
                        safe_iso_date(r["Дата доставки"]),
                        pp_id,
                        int(customer_id) if customer_id is not None else None,
                        int(r["Код для получения"]),
                        int(status_id),
                    ),
                )

                items = str(r["Артикул заказа"]).split(",")
                items = [x.strip() for x in items if str(x).strip()]
                pairs = []
                for i in range(0, len(items) - 1, 2):
                    art = items[i]
                    try:
                        qty = int(items[i + 1])
                    except ValueError:
                        continue
                    pairs.append((art, qty))

                order_id = scalar(conn, "SELECT OrderId FROM Orders WHERE OrderNumber=?", (int(r["Номер заказа"]),))
                if order_id is None:
                    continue
                for art, qty in pairs:
                    product_id = scalar(conn, "SELECT ProductId FROM Products WHERE Article=?", (art,))
                    if product_id is None:
                        continue
                    conn.execute(
                        "INSERT OR IGNORE INTO OrderItems(OrderId, ProductId, Quantity) VALUES (?,?,?)",
                        (int(order_id), int(product_id), int(qty)),
                    )

        conn.commit()
    finally:
        conn.close()


if __name__ == "__main__":
    seed()
    print("DB ready:", BASE_DIR / "store.db")
