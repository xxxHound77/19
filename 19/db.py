import sqlite3
from pathlib import Path
from typing import Optional, Any, Iterable

DB_PATH = Path(__file__).resolve().parent / "store.db"


def connect() -> sqlite3.Connection:
    """Устанавливает соединение с БД, включает доступ по именам столбцов и внешние ключи."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


def init_db() -> None:
    """Создаёт все таблицы БД, если они отсутствуют, и загружает начальные данные."""
    conn = connect()
    try:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS Roles (
                RoleId INTEGER PRIMARY KEY,
                RoleName TEXT NOT NULL UNIQUE
            );

            CREATE TABLE IF NOT EXISTS Users (
                UserId INTEGER PRIMARY KEY AUTOINCREMENT,
                FullName TEXT NOT NULL,
                Login TEXT NOT NULL UNIQUE,
                Password TEXT NOT NULL,
                RoleId INTEGER NOT NULL,
                FOREIGN KEY(RoleId) REFERENCES Roles(RoleId)
            );

            CREATE TABLE IF NOT EXISTS Suppliers (
                SupplierId INTEGER PRIMARY KEY AUTOINCREMENT,
                SupplierName TEXT NOT NULL UNIQUE
            );

            CREATE TABLE IF NOT EXISTS Manufacturers (
                ManufacturerId INTEGER PRIMARY KEY AUTOINCREMENT,
                ManufacturerName TEXT NOT NULL UNIQUE
            );

            CREATE TABLE IF NOT EXISTS Categories (
                CategoryId INTEGER PRIMARY KEY AUTOINCREMENT,
                CategoryName TEXT NOT NULL UNIQUE
            );

            CREATE TABLE IF NOT EXISTS Units (
                UnitId INTEGER PRIMARY KEY AUTOINCREMENT,
                UnitName TEXT NOT NULL UNIQUE
            );

            CREATE TABLE IF NOT EXISTS Products (
                ProductId INTEGER PRIMARY KEY AUTOINCREMENT,
                Article TEXT NOT NULL UNIQUE,
                ProductName TEXT NOT NULL,
                Description TEXT,
                CategoryId INTEGER NOT NULL,
                ManufacturerId INTEGER NOT NULL,
                SupplierId INTEGER NOT NULL,
                UnitId INTEGER NOT NULL,
                Price REAL NOT NULL CHECK(Price >= 0),
                DiscountPercent REAL NOT NULL CHECK(DiscountPercent >= 0),
                StockQty INTEGER NOT NULL CHECK(StockQty >= 0),
                PhotoPath TEXT,
                FOREIGN KEY(CategoryId) REFERENCES Categories(CategoryId),
                FOREIGN KEY(ManufacturerId) REFERENCES Manufacturers(ManufacturerId),
                FOREIGN KEY(SupplierId) REFERENCES Suppliers(SupplierId),
                FOREIGN KEY(UnitId) REFERENCES Units(UnitId)
            );

            CREATE TABLE IF NOT EXISTS PickupPoints (
                PickupPointId INTEGER PRIMARY KEY AUTOINCREMENT,
                Address TEXT NOT NULL UNIQUE
            );

            CREATE TABLE IF NOT EXISTS OrderStatuses (
                StatusId INTEGER PRIMARY KEY AUTOINCREMENT,
                StatusName TEXT NOT NULL UNIQUE
            );

            CREATE TABLE IF NOT EXISTS Orders (
                OrderId INTEGER PRIMARY KEY AUTOINCREMENT,
                OrderNumber INTEGER NOT NULL UNIQUE,
                OrderDate TEXT NOT NULL,
                DeliveryDate TEXT NOT NULL,
                PickupPointId INTEGER NOT NULL,
                CustomerUserId INTEGER,
                ReceiveCode INTEGER NOT NULL,
                StatusId INTEGER NOT NULL,
                FOREIGN KEY(PickupPointId) REFERENCES PickupPoints(PickupPointId),
                FOREIGN KEY(CustomerUserId) REFERENCES Users(UserId),
                FOREIGN KEY(StatusId) REFERENCES OrderStatuses(StatusId)
            );

            CREATE TABLE IF NOT EXISTS OrderItems (
                OrderItemId INTEGER PRIMARY KEY AUTOINCREMENT,
                OrderId INTEGER NOT NULL,
                ProductId INTEGER NOT NULL,
                Quantity INTEGER NOT NULL CHECK(Quantity > 0),
                FOREIGN KEY(OrderId) REFERENCES Orders(OrderId) ON DELETE CASCADE,
                FOREIGN KEY(ProductId) REFERENCES Products(ProductId),
                UNIQUE(OrderId, ProductId)
            );
            """
        )
        conn.commit()
    finally:
        conn.close()


def scalar(conn: sqlite3.Connection, query: str, params: Iterable[Any] = ()) -> Any:
    """Возвращает первое значение первой строки результата запроса или None."""
    cur = conn.execute(query, params)
    row = cur.fetchone()
    return None if row is None else row[0]


def ensure_lookup(conn: sqlite3.Connection, table: str, col: str, value: str) -> int:
    """Возвращает ID существующей записи справочника или создаёт новую и возвращает её ID."""
    id_map = {
        "Roles": "RoleId",
        "Suppliers": "SupplierId",
        "Manufacturers": "ManufacturerId",
        "Categories": "CategoryId",
        "Units": "UnitId",
        "PickupPoints": "PickupPointId",
        "OrderStatuses": "StatusId",
    }
    id_col = id_map.get(table)
    if not id_col:
        id_col = f"{table[:-1]}Id" if table.endswith("s") else f"{table}Id"

    existing = scalar(conn, f"SELECT {id_col} FROM {table} WHERE {col} = ?", (value,))
    if existing is not None:
        return int(existing)
    cur = conn.execute(f"INSERT INTO {table}({col}) VALUES (?)", (value,))
    return int(cur.lastrowid)
